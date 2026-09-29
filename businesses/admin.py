from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django import forms
from django.conf import settings
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils import timezone

from .models import Business, BusinessApiKey, BusinessIntegration, KnowledgeItem
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

    @admin.display(description="Public chat")
    def chat_link(self, business: Business) -> str:
        return format_html('<a href="{}">Open chat</a>', business.get_absolute_url())

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


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
