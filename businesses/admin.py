from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils import timezone

from .document_chunks import preview_chunks
from .document_importer import DocumentImportError, import_document_json
from .document_knowledge import publish_document, test_document_retrieval
from .forms import ChatQuestionForm, DocumentDraftForm, DocumentImportForm, KnowledgeImportForm
from .importer import KnowledgeImportError, import_qa_json
from .models import Business, BusinessApiKey, BusinessIntegration, Document, DocumentRevision, KnowledgeItem
from .rag import publish_item
from .vector_store import delete_vector

# Accounts are provisioned through the operator CLI; there are no per-business roles.
admin.site.unregister([User, Group])
admin.site.site_header = "Customer Service"
admin.site.site_title = "Customer Service Admin"
admin.site.index_title = "Your businesses"


class BusinessIntegrationForm(forms.ModelForm):
    allowed_origins = forms.CharField(
        help_text="One exact origin per line, such as https://shop.example or http://localhost:3000.",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    class Meta:
        model = BusinessIntegration
        fields = ["business", "allowed_origins"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["allowed_origins"] = "\n".join(self.instance.allowed_origins)

    def clean_allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cleaned_data["allowed_origins"].splitlines() if origin.strip()]


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ["name", "chat_link", "created_at"]
    fields = ["name"]
    search_fields = ["name"]
    change_list_template = "admin/businesses/business/change_list.html"

    @admin.display(description="Public chat")
    def chat_link(self, business: Business) -> str:
        return format_html('<a href="{}">Open chat</a>', business.get_absolute_url())

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_urls(self):
        return [
            path("import-qa/", self.admin_site.admin_view(self.import_qa), name="businesses_business_import_qa"),
            *super().get_urls(),
        ]

    def import_qa(self, request: HttpRequest):
        form = KnowledgeImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                result = import_qa_json(form.cleaned_data["business"], form.cleaned_data["file"].read())
            except KnowledgeImportError as error:
                form.add_error("file", str(error))
            else:
                self.message_user(
                    request,
                    f"Created {result.created} draft Q&A item(s); skipped {result.skipped} duplicate item(s).",
                    messages.SUCCESS,
                )
                return redirect("admin:businesses_knowledgeitem_changelist")
        return render(
            request,
            "admin/businesses/business/import_qa.html",
            {**self.admin_site.each_context(request), "form": form, "title": "Import Q&A from JSON"},
        )


@admin.register(BusinessIntegration)
class BusinessIntegrationAdmin(admin.ModelAdmin):
    form = BusinessIntegrationForm
    list_display = ["business", "allowed_origin_count", "updated_at"]
    search_fields = ["business__name"]
    actions = ("create_api_key", "rotate_embed_token")
    readonly_fields = ["widget_details", "embed_url"]

    def get_fields(self, request, obj=None):
        if obj:
            return ["business", "allowed_origins", "embed_url", "widget_details"]
        return ["business", "allowed_origins"]

    @admin.display(description="Allowed origins")
    def allowed_origin_count(self, integration: BusinessIntegration) -> int:
        return len(integration.allowed_origins)

    @admin.display(description="Direct iframe URL")
    def embed_url(self, integration: BusinessIntegration) -> str:
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/embed/{integration.embed_token}/"

    @admin.display(description="Widget installation")
    def widget_details(self, integration: BusinessIntegration) -> str:
        script_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/static/businesses/widget.js"
        tag = f'<script async src="{script_url}" data-token="{integration.embed_token}"></script>'
        return format_html(
            "<p>Copy this into the business website. The button opens the iframe URL above.</p>"
            '<textarea readonly rows="3" style="width:100%">{}</textarea>',
            tag,
        )

    @admin.action(description="Create or rotate API key (shows the new key once)")
    def create_api_key(self, request: HttpRequest, queryset) -> None:
        for integration in queryset:
            _, secret = integration.create_api_key()
            self.message_user(
                request,
                format_html("Copy this API key now; it will not be shown again: <code>{}</code>", secret),
                messages.SUCCESS,
            )

    @admin.action(description="Rotate embed token (old widget stops immediately)")
    def rotate_embed_token(self, request: HttpRequest, queryset) -> None:
        for integration in queryset:
            integration.rotate_embed_token()
        self.message_user(request, f"Rotated {queryset.count()} embed token(s).", messages.SUCCESS)


@admin.register(BusinessApiKey)
class BusinessApiKeyAdmin(admin.ModelAdmin):
    list_display = ["integration", "created_at", "expires_at", "revoked_at"]
    list_filter = ["integration__business"]
    readonly_fields = ("integration", "created_at", "expires_at", "revoked_at")
    fields = ("integration", "created_at", "expires_at", "revoked_at")
    actions = ("revoke_selected",)

    def has_add_permission(self, request) -> bool:
        return False

    @admin.action(description="Revoke selected API key(s)")
    def revoke_selected(self, request: HttpRequest, queryset) -> None:
        queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, "Selected API key(s) were revoked.", messages.SUCCESS)


@admin.register(KnowledgeItem)
class KnowledgeItemAdmin(admin.ModelAdmin):
    list_display = ["question", "business", "status", "index_status", "updated_at"]
    list_filter = ["business", "status", "index_status"]
    search_fields = ["question", "answer"]
    fields = ["business", "question", "answer", "replacement_for", "status", "index_status", "index_error"]
    readonly_fields = ["replacement_for", "status", "index_status", "index_error"]
    actions = ["publish_selected", "create_replacement_drafts"]

    @admin.action(description="Publish selected Q&A")
    def publish_selected(self, request: HttpRequest, queryset) -> None:
        selected = queryset.count()
        published = 0
        failed = 0
        drafts = queryset.filter(status=KnowledgeItem.Status.DRAFT).select_related("business")
        for item in drafts:
            try:
                publish_item(item)
                published += 1
            except Exception:
                failed += 1
        if published:
            self.message_user(request, f"Published {published} Q&A item(s).", messages.SUCCESS)
        if failed:
            self.message_user(
                request,
                f"Could not publish {failed} item(s). Open each item to see the indexing error.",
                messages.ERROR,
            )
        skipped = selected - published - failed
        if skipped:
            self.message_user(request, f"Skipped {skipped} published Q&A item(s).", messages.INFO)

    @admin.action(description="Create replacement drafts for selected Q&A")
    def create_replacement_drafts(self, request: HttpRequest, queryset) -> None:
        created = 0
        for item in queryset.filter(status=KnowledgeItem.Status.PUBLISHED).select_related("business"):
            if item.replacement_drafts.filter(status=KnowledgeItem.Status.DRAFT).exists():
                continue
            KnowledgeItem.objects.create(
                business=item.business,
                question=item.question,
                answer=item.answer,
                replacement_for=item,
            )
            created += 1
        self.message_user(request, f"Created {created} replacement draft(s).", messages.SUCCESS)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == KnowledgeItem.Status.PUBLISHED:
            return ["business", "question", "answer", "replacement_for", "status", "index_status", "index_error"]
        if obj and obj.replacement_for_id:
            return ["business", "replacement_for", "status", "index_status", "index_error"]
        return self.readonly_fields

    def delete_model(self, request: HttpRequest, obj: KnowledgeItem) -> None:
        self._delete_item(request, obj)

    def delete_queryset(self, request: HttpRequest, queryset) -> None:
        for item in queryset.select_related("business"):
            self._delete_item(request, item)

    def _delete_item(self, request: HttpRequest, item: KnowledgeItem) -> None:
        business, vector_id = item.business, item.vector_id or item.id
        item.delete()
        try:
            delete_vector(business, vector_id)
        except Exception:
            self.message_user(
                request,
                "The Q&A was deleted. Its stale search vector will be ignored and can be cleaned up later.",
                messages.WARNING,
            )


@admin.register(DocumentRevision)
class DocumentRevisionAdmin(admin.ModelAdmin):
    form = DocumentDraftForm
    change_list_template = "admin/businesses/documentrevision/change_list.html"
    change_form_template = "admin/businesses/documentrevision/change_form.html"
    list_display = ["title", "business_name", "product", "version", "revision_number", "status", "index_status", "updated_at"]
    list_filter = ["document__business", "status", "index_status"]
    search_fields = ["title", "product", "content"]

    def get_urls(self):
        return [
            path("import-json/", self.admin_site.admin_view(self.import_json), name="businesses_documentrevision_import_json"),
            path("<path:object_id>/publish/", self.admin_site.admin_view(self.publish_view), name="businesses_documentrevision_publish"),
            path("<path:object_id>/test-retrieval/", self.admin_site.admin_view(self.test_retrieval_view), name="businesses_documentrevision_test_retrieval"),
            *super().get_urls(),
        ]

    def publish_view(self, request: HttpRequest, object_id: str):
        revision = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, revision):
            raise PermissionDenied
        if revision.status != DocumentRevision.Status.DRAFT:
            raise Http404
        url = reverse("admin:businesses_documentrevision_change", args=[revision.pk])
        if request.method == "POST" and request.POST.get("confirm") == "yes":
            try:
                count = publish_document(revision)
            except Exception as error:
                self.message_user(request, f"Could not publish Document: {error}", messages.ERROR)
            else:
                self.message_user(request, f"Published {count} chunk(s) at {revision.updated_at:%Y-%m-%d %H:%M}.", messages.SUCCESS)
            return redirect(url)
        try:
            chunk_count = len(preview_chunks(revision))
            preview_error = ""
        except Exception as error:
            chunk_count = 0
            preview_error = str(error)
        return render(request, "admin/businesses/documentrevision/publish.html", {
            **self.admin_site.each_context(request), "title": "Publish Document", "revision": revision,
            "chunk_count": chunk_count, "preview_error": preview_error,
        })

    def test_retrieval_view(self, request: HttpRequest, object_id: str):
        revision = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_view_permission(request, revision):
            raise PermissionDenied
        if revision.status != DocumentRevision.Status.PUBLISHED:
            raise Http404
        form = ChatQuestionForm(request.POST or None)
        matches = None
        error = ""
        if request.method == "POST" and form.is_valid():
            try:
                matches = test_document_retrieval(revision, form.cleaned_data["question"])
            except Exception as cause:
                error = str(cause)
        return render(request, "admin/businesses/documentrevision/test_retrieval.html", {
            **self.admin_site.each_context(request), "title": "Test retrieval", "revision": revision,
            "form": form, "matches": matches, "error": error,
        })

    def import_json(self, request: HttpRequest):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = DocumentImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            upload = form.cleaned_data["file"]
            business = form.cleaned_data["business"]
            try:
                result = import_document_json(business, upload.read(), source_name=upload.name)
            except DocumentImportError as error:
                form.add_error("file", str(error))
            else:
                self.message_user(
                    request,
                    f"Created {result.created} document draft(s); skipped {result.skipped} duplicate(s).",
                    messages.SUCCESS,
                )
                query = urlencode({"document__business__id__exact": business.pk, "status__exact": "draft"})
                return redirect(f"{reverse('admin:businesses_documentrevision_changelist')}?{query}")
        return render(
            request,
            "admin/businesses/documentrevision/import_json.html",
            {**self.admin_site.each_context(request), "form": form, "title": "Import Documents from JSON"},
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("document__business")

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["business", "title", "content", "upload", "product", "version"]
        return [
            "business_name", "title", "content", "product", "version", "source_name",
            "revision_number", "status", "index_status", "index_error", "character_count", "chunk_preview",
        ]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        fields = [
            "business_name", "source_name", "revision_number", "status", "index_status",
            "index_error", "character_count", "chunk_preview",
        ]
        if obj.status != DocumentRevision.Status.DRAFT:
            fields += ["title", "content", "product", "version"]
        return fields

    def has_change_permission(self, request, obj=None) -> bool:
        return obj is None or obj.status == DocumentRevision.Status.DRAFT

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def save_model(self, request, obj: DocumentRevision, form, change: bool) -> None:
        if not change:
            obj.document = Document.objects.create(business=form.cleaned_data["business"])
            obj.revision_number = 1
        if form.cleaned_data.get("upload"):
            obj.source_name = form.cleaned_data["upload"].name
        obj.save()

    @admin.display(description="Business")
    def business_name(self, obj: DocumentRevision) -> str:
        return obj.document.business.name

    @admin.display(description="Character count")
    def character_count(self, obj: DocumentRevision) -> str:
        return f"{len(obj.content)} characters"

    @admin.display(description="Chunk preview")
    def chunk_preview(self, obj: DocumentRevision):
        try:
            chunks = preview_chunks(obj)
        except ValueError as error:
            return f"Preview unavailable: {error}"
        except Exception:
            return "Preview unavailable. Check the embedding model configuration."
        rows = ((chunk.order, chunk.heading or "No heading", chunk.token_count, chunk.text) for chunk in chunks)
        return format_html(
            "<ol>{}</ol>",
            format_html_join("", '<li><strong>Chunk {} · {} · {} tokens</strong><pre style="white-space:pre-wrap">{}</pre></li>', rows),
        )
