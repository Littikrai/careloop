from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from businesses.views import chat

urlpatterns = [path("chat/<uuid:business_id>/", chat, name="business-chat"), path("", RedirectView.as_view(url="/admin/", permanent=False)), path("admin/", admin.site.urls)]
