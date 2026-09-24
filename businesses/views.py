from uuid import UUID
import hashlib
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .forms import ChatQuestionForm
from .models import Business, KnowledgeItem
from .openrouter import OpenRouterError
from .rag import AnswerResult, answer_question


def _within_rate_limit(request: HttpRequest, business: Business) -> bool:
    # ponytail: per-process counter; use a shared cache before adding workers or replicas.
    limit = settings.CHAT_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return True
    address = request.META.get("REMOTE_ADDR", "unknown")
    client_hash = hashlib.sha256(address.encode()).hexdigest()[:16]
    key = f"chat:{business.id}:{client_hash}:{int(time.time() // 60)}"
    if cache.add(key, 1, timeout=70):
        return True
    return cache.incr(key) <= limit


@require_http_methods(["GET", "POST"])
def chat(request: HttpRequest, business_id: UUID) -> HttpResponse:
    business = get_object_or_404(Business, pk=business_id)
    result: AnswerResult | None = None
    form = ChatQuestionForm(request.POST or None)
    has_knowledge = KnowledgeItem.objects.filter(
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    ).exists()
    if request.method == "POST" and form.is_valid():
        if not _within_rate_limit(request, business):
            result = AnswerResult("rate_limited", "Too many questions. Please try again in a minute.")
        else:
            try:
                result = answer_question(business, form.cleaned_data["question"])
            except OpenRouterError:
                result = AnswerResult(
                    "service_error",
                    "The answer service is temporarily unavailable. Please try again.",
                )
            except Exception:
                result = AnswerResult(
                    "service_error",
                    "The knowledge search is temporarily unavailable. Please try again.",
                )
    response = render(
        request,
        "businesses/chat.html",
        {"business": business, "form": form, "result": result, "has_knowledge": has_knowledge},
    )
    if result and result.kind == "rate_limited":
        response.status_code = 429
    return response
