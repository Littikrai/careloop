import json
import urllib.error
import urllib.request

from django.conf import settings


class OpenRouterError(RuntimeError):
    pass


SYSTEM_PROMPT = """You answer customer questions using only the supplied published Q&A.
Do not use outside knowledge or invent facts.
If the supplied entries conflict or the question is ambiguous, ask one concise clarifying question.
Answer in the language used by the customer when possible."""


def complete_answer(question: str, knowledge: list[tuple[str, str]]) -> str:
    if not settings.OPENROUTER_API_KEY:
        raise OpenRouterError("OpenRouter is not configured. Set OPENROUTER_API_KEY.")

    content = json.dumps(
        {
            "customer_question": question,
            "published_qa": [
                {"question": source_question, "answer": answer}
                for source_question, answer in knowledge
            ],
        },
        ensure_ascii=False,
    )
    body = json.dumps(
        {
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
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
        answer = payload["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise KeyError("empty completion")
        return answer.strip()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as error:
        raise OpenRouterError("OpenRouter could not produce an answer.") from error
