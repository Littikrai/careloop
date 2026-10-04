from uuid import UUID
import hashlib
import json
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import ChatQuestionForm
from .document_knowledge import active_document_chunks
from .models import Business, BusinessApiKey, BusinessIntegration, KnowledgeItem
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


def _within_api_rate_limit(key: BusinessApiKey) -> bool:
    # ponytail: per-process counter; use a shared cache before adding workers or replicas.
    limit = settings.API_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return True
    cache_key = f"api:{key.pk}:{int(time.time() // 60)}"
    if cache.add(cache_key, 1, timeout=70):
        return True
    return cache.incr(cache_key) <= limit


def _api_error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@require_http_methods(["GET", "POST"])
def chat(request: HttpRequest, business_id: UUID) -> HttpResponse:
    business = get_object_or_404(Business, pk=business_id)
    return _render_chat(request, business)


@csrf_exempt
@xframe_options_exempt
@require_http_methods(["GET", "POST"])
def embed_chat(request: HttpRequest, token: str) -> HttpResponse:
    integration = get_object_or_404(BusinessIntegration.objects.select_related("business"), embed_token=token)
    response = _render_chat(request, integration.business, embedded=True)
    response["Content-Security-Policy"] = f"frame-ancestors {' '.join(integration.allowed_origins)}"
    return response


@require_http_methods(["GET"])
def widget_test(request: HttpRequest) -> HttpResponse:
    value = request.GET.get("token", "").strip()
    path = urlsplit(value).path
    token = path.removeprefix("/embed/").strip("/") if path.startswith("/embed/") else value.strip("/")
    return render(request, "businesses/widget_test.html", {"token": token})


@csrf_exempt
@require_http_methods(["POST"])
def api_chat(request: HttpRequest) -> JsonResponse:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, secret = authorization.partition(" ")
    if scheme != "Bearer" or not separator or not secret:
        return _api_error(401, "unauthorized", "Invalid API key.")

    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    key = (
        BusinessApiKey.objects.select_related("integration__business")
        .filter(secret_hash=secret_hash, revoked_at__isnull=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .first()
    )
    if key is None:
        return _api_error(401, "unauthorized", "Invalid API key.")

    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return _api_error(422, "invalid_request", "Body must be valid JSON with a question.")
    question = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(question, str):
        return _api_error(422, "invalid_request", "Question must be a nonempty string.")
    form = ChatQuestionForm({"question": question})
    if not form.is_valid():
        return _api_error(422, "invalid_request", "Question must be a nonempty string.")

    if not _within_api_rate_limit(key):
        return _api_error(429, "rate_limited", "Too many questions. Please try again in a minute.")
    try:
        result = answer_question(key.integration.business, form.cleaned_data["question"])
    except Exception:
        return _api_error(503, "service_unavailable", "Chat is temporarily unavailable.")
    return JsonResponse({"answer": result.text, "status": result.kind, "sources": result.sources})


def _render_chat(request: HttpRequest, business: Business, *, embedded: bool = False) -> HttpResponse:
    result: AnswerResult | None = None
    asked_question: str | None = None
    form = ChatQuestionForm(request.POST or None)
    has_knowledge = KnowledgeItem.objects.filter(
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    ).exists() or active_document_chunks(business).exists()
    if request.method == "POST" and form.is_valid():
        asked_question = form.cleaned_data["question"]
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
        {
            "business": business,
            "form": form,
            "result": result,
            "asked_question": asked_question,
            "has_knowledge": has_knowledge,
            "embedded": embedded,
        },
    )
    if result and result.kind == "rate_limited":
        response.status_code = 429
    return response
