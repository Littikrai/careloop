from uuid import UUID
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe
from .models import Business


@require_safe
def chat(request: HttpRequest, business_id: UUID) -> HttpResponse:
    business = get_object_or_404(Business, pk=business_id)
    return render(request, "businesses/chat.html", {"business": business})
