from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.http import HttpRequest
from django.utils.html import format_html

from .models import Business, KnowledgeItem
from .rag import publish_item
from .vector_store import delete_vector

# Accounts are provisioned through the operator CLI; there are no per-business roles.
admin.site.unregister([User, Group])
admin.site.site_header = "Customer Service"
admin.site.site_title = "Customer Service Admin"
admin.site.index_title = "Your businesses"


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
