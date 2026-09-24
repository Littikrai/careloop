from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.http import HttpRequest
from django.utils.html import format_html

from .models import Business, KnowledgeItem
from .rag import publish_item

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
    fields = ["business", "question", "answer", "status", "index_status", "index_error"]
    readonly_fields = ["status", "index_status", "index_error"]
    actions = ["publish_selected"]

    @admin.action(description="Publish selected Q&A")
    def publish_selected(self, request: HttpRequest, queryset) -> None:
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
        skipped = queryset.count() - published - failed
        if skipped:
            self.message_user(request, f"Skipped {skipped} published Q&A item(s).", messages.INFO)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == KnowledgeItem.Status.PUBLISHED:
            return ["business", "question", "answer", "status", "index_status", "index_error"]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
