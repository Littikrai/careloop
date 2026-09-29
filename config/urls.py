from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from businesses.views import chat, embed_chat, widget_test

urlpatterns = [
    path("chat/<uuid:business_id>/", chat, name="business-chat"),
    path("embed/<str:token>/", embed_chat, name="embed-chat"),
    path("widget-test/", widget_test, name="widget-test"),
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),
]
