import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


class OpenRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompletionResult:
    status: str
    answer: str
    source_ids: tuple[str, ...]


SYSTEM_PROMPT = """Answer the customer's question using only the supplied sources.
An authoritative source controls the answer when another source disagrees; other sources may add only consistent details.
Semantic similarity is for retrieval, not a measure of certainty. If sources conflict without an authoritative match,
or a product/version is ambiguous, ask one concise clarifying question. If the sources cannot support an answer,
return insufficient_knowledge. Use the customer's language when possible. Cite only sources you used."""


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answer", "needs_clarification", "insufficient_knowledge"]},
        "answer": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "answer", "source_ids"],
    "additionalProperties": False,
}


def _parse_completion(content: object, allowed_ids: set[str]) -> CompletionResult:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Empty completion")
    result = json.loads(content)
    if not isinstance(result, dict) or set(result) != {"status", "answer", "source_ids"}:
        raise ValueError("Invalid completion fields")
    status, answer, source_ids = result["status"], result["answer"], result["source_ids"]
    if status not in {"answer", "needs_clarification", "insufficient_knowledge"}:
        raise ValueError("Invalid completion status")
    if not isinstance(answer, str) or (status != "insufficient_knowledge" and not answer.strip()):
        raise ValueError("Empty answer")
    if (
        not isinstance(source_ids, list)
        or any(not isinstance(source_id, str) or source_id not in allowed_ids for source_id in source_ids)
        or len(set(source_ids)) != len(source_ids)
        or (status == "answer" and not source_ids)
    ):
        raise ValueError("Invalid source IDs")
    return CompletionResult(status, answer.strip(), tuple(source_ids))


def complete_answer(question: str, sources: list[dict[str, str | bool]]) -> CompletionResult:
    if not settings.OPENROUTER_API_KEY:
        raise OpenRouterError("OpenRouter is not configured. Set OPENROUTER_API_KEY.")

    content = json.dumps({"customer_question": question, "sources": sources}, ensure_ascii=False)
    body = json.dumps(
        {
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "customer_support_answer", "strict": True, "schema": ANSWER_SCHEMA},
            },
            "provider": {"require_parameters": True},
            "reasoning": {"effort": "none", "exclude": True},
            "temperature": 0.1,
            "max_tokens": 400,
        }
    ).encode()
    request = urllib.request.Request(
        settings.OPENROUTER_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "Self-hosted Customer Service Bot",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.OPENROUTER_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
        return _parse_completion(
            payload["choices"][0]["message"]["content"],
            {str(source["id"]) for source in sources},
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError, IndexError) as error:
        raise OpenRouterError("OpenRouter could not produce an answer.") from error
