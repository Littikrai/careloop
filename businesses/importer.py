import json
import unicodedata
from dataclasses import dataclass

from django.db import transaction

from .models import Business, KnowledgeItem


class KnowledgeImportError(ValueError):
    pass


@dataclass(frozen=True)
class KnowledgeImportResult:
    created: int
    skipped: int


def _normalise_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def import_qa_json(business: Business, content: bytes) -> KnowledgeImportResult:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise KnowledgeImportError("File must be a UTF-8 JSON array.") from None
    if not isinstance(payload, list) or not payload:
        raise KnowledgeImportError("File must contain a nonempty JSON array.")

    errors: list[str] = []
    skipped = 0
    imported: dict[str, str] = {}
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict) or set(item) != {"question", "answer"}:
            errors.append(f"Item {index} must contain only question and answer.")
            continue
        question, answer = item["question"], item["answer"]
        if not isinstance(question, str) or not isinstance(answer, str):
            errors.append(f"Item {index} question and answer must be strings.")
            continue
        question, answer = _normalise_text(question), _normalise_text(answer)
        if not question or not answer:
            errors.append(f"Item {index} question and answer cannot be empty.")
            continue
        try:
            question.encode("utf-8")
            answer.encode("utf-8")
        except UnicodeEncodeError:
            errors.append(f"Item {index} question and answer must be valid Unicode text.")
            continue
        existing_answer = imported.get(question)
        if existing_answer is None:
            imported[question] = answer
        elif existing_answer == answer:
            skipped += 1
        else:
            errors.append(f"Item {index} conflicts with another answer for the same question.")
    if errors:
        raise KnowledgeImportError(" ".join(errors))

    existing_answers: dict[str, set[str]] = {}
    for question, answer in KnowledgeItem.objects.filter(business=business).values_list("question", "answer"):
        existing_answers.setdefault(question, set()).add(answer)

    to_create: list[tuple[str, str]] = []
    for question, answer in imported.items():
        answers = existing_answers.get(question, set())
        if answer in answers:
            skipped += 1
        elif answers:
            errors.append(f"Question '{question}' conflicts with an existing answer.")
        else:
            to_create.append((question, answer))
    if errors:
        raise KnowledgeImportError(" ".join(errors))

    with transaction.atomic():
        for question, answer in to_create:
            KnowledgeItem.objects.create(business=business, question=question, answer=answer)
    return KnowledgeImportResult(created=len(to_create), skipped=skipped)
