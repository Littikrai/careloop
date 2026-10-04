import json
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Business, Document, DocumentRevision


class DocumentImportError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentImportResult:
    created: int
    skipped: int


def import_document_json(business: Business, content: bytes, *, source_name: str = "") -> DocumentImportResult:
    if len(content) > 5 * 1024 * 1024:
        raise DocumentImportError("JSON file cannot exceed 5 MiB.")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise DocumentImportError("File must be a UTF-8 JSON array.") from None
    if not isinstance(payload, list) or not payload:
        raise DocumentImportError("File must contain a nonempty JSON array.")

    normalized: list[tuple[str, str, str, str]] = []
    allowed = {"title", "content", "product", "version"}
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise DocumentImportError(f"Item {index} must be an object with title and content.")
        missing = {"title", "content"} - item.keys()
        extra = item.keys() - allowed
        if missing or extra:
            details = ", ".join(sorted(missing | extra))
            raise DocumentImportError(f"Item {index} has missing or unsupported field(s): {details}.")
        if any(not isinstance(value, str) for value in item.values()):
            field = next(name for name, value in item.items() if not isinstance(value, str))
            raise DocumentImportError(f"Item {index} {field} must be a string.")
        revision = DocumentRevision(
            title=item["title"], content=item["content"],
            product=item.get("product", ""), version=item.get("version", ""),
        )
        try:
            revision.full_clean(exclude={"document"})
        except ValidationError as error:
            field, messages = next(iter(error.message_dict.items()))
            raise DocumentImportError(f"Item {index} {field}: {messages[0]}") from None
        normalized.append((revision.title, revision.content, revision.product, revision.version))

    skipped = 0
    with transaction.atomic():
        existing = set(
            DocumentRevision.objects.filter(
                document__business=business, title__in={title for title, _, _, _ in normalized}
            ).values_list(
                "title", "content", "product", "version"
            )
        )
        created = 0
        for title, text, product, version in normalized:
            key = (title, text, product, version)
            if key in existing:
                skipped += 1
                continue
            document = Document.objects.create(business=business)
            DocumentRevision.objects.create(
                document=document, title=title, content=text, product=product,
                version=version, source_name=source_name,
            )
            existing.add(key)
            created += 1
    return DocumentImportResult(created=created, skipped=skipped)
