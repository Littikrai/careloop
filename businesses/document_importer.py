import json
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Business, Document, DocumentRevision

MAX_DOCUMENT_IMPORT_BYTES = 5 * 1024 * 1024


class DocumentImportError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentImportResult:
    created: int
    skipped: int


def import_document_json(business: Business, content: bytes, *, source_name: str = "") -> DocumentImportResult:
    if len(content) > MAX_DOCUMENT_IMPORT_BYTES:
        raise DocumentImportError("JSON file cannot exceed 5 MiB.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentImportError(f"Invalid UTF-8 at byte {error.start + 1}: {error.reason}.") from None
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as error:
        raise DocumentImportError(
            f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}."
        ) from None
    except (ValueError, RecursionError):
        raise DocumentImportError("File must be a UTF-8 JSON array.") from None
    if not isinstance(payload, list) or not payload:
        raise DocumentImportError("File must contain a nonempty JSON array.")
    try:
        source_name.encode("utf-8")
    except UnicodeEncodeError:
        raise DocumentImportError("File name must be valid Unicode text.") from None
    if len(source_name) > 255:
        raise DocumentImportError("File name cannot exceed 255 characters.")

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
        for field, value in item.items():
            if not isinstance(value, str):
                raise DocumentImportError(f"Item {index} {field} must be a string.")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise DocumentImportError(f"Item {index} {field} must be valid Unicode text.") from None
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
