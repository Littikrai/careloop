from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.utils.html import format_html
from .models import Business

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
