import json
import re
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
Semantic similarity is for retrieval, not a measure of certainty.
For a broad question about a named product, such as "what is it like" or "เป็นยังไง", give a short factual
overview when a coherent source describes its type or intended use. Do not require reviews, opinions, or a
complete specification. Use only facts stated in coherent sources; never infer details from incomplete fragments.
If sources conflict without an authoritative match, or a product/version is ambiguous, ask one concise
clarifying question. Return insufficient_knowledge only when no source supports a factual answer to the
question. If sources support any part of a multi-part question, answer the supported facts and say briefly
which requested detail is not documented; do not refuse the whole question because one detail is missing.
Chunks with the same title, product, and version belong to the same document unless they directly conflict on a
fact. Apply a test-only or sample disclaimer in any chunk to that document's other chunks. The disclaimer
qualifies the facts but does not erase them, create a conflict, or make supported details unavailable. If asked
about sample data, answer what the document says and identify it as test data; do not present its values as
real specifications or guarantees. Do not refuse just because you cannot verify whether the real-world product
has those values. For example, if a test-only source states "12-month warranty" and says it is not a real
guarantee, answer that the sample states 12 months and clearly say it is not an actual guarantee. Return
insufficient_knowledge only when the requested fact is absent from all relevant sources.
When a sample source explicitly states a product fact, answer what the sample says even if the real-world product
cannot be verified. For example, if a sample says "do not use with saltwater" and the customer asks about
saltwater, say the sample does not allow saltwater use and identify it as simulated data; do not refuse because
the real product is unknown.
Report limitations and exclusions only within the scope the source states. If a warranty excludes damage caused
by dry operation or saltwater, say only that damage caused by that use is not covered. Never claim the entire
warranty is void, ends, expires, or is cancelled unless a source explicitly says so. Do not infer damage,
coverage, or other consequences from a restriction unless the source states them. Mention warranty terms only
when the customer asks about warranty; otherwise answer the requested product question without adding them.
Put citations only in source_ids; never include internal IDs such as [src-1] in the customer-facing answer.
Use the customer's language for every response. For insufficient_knowledge, write a brief
customer-facing explanation in that language in the answer field. State only that the supplied published
information does not establish the requested fact; do not guess, add unrelated facts, or use a fixed English
message for a non-English question. If no sources are supplied, do not answer factually; say in the customer's
language that no relevant published information was found. Cite only sources you used."""


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
    answer = re.sub(
        r"\s*(?:\[\s*src-\d+\s*\]|\(\s*src-\d+\s*\)|\bsrc-\d+\b)\s*",
        " ",
        answer,
        flags=re.IGNORECASE,
    )
    answer = re.sub(r"\s+([,.;:!?])", r"\1", answer).strip()
    if status != "insufficient_knowledge" and not answer:
        raise ValueError("Empty answer after removing source IDs")
    return CompletionResult(status, answer, tuple(source_ids))


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
