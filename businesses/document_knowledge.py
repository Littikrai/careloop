import logging
import threading
from collections.abc import Callable
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Max, QuerySet

from .document_chunks import preview_chunks
from .models import Business, Document, DocumentChunk, DocumentRevision
from .vector_store import delete_vector as default_delete_vector
from .vector_store import embed_document as default_embed_document
from .vector_store import embed_query as default_embed_query
from .vector_store import search_vectors as default_search_vectors
from .vector_store import upsert_vector as default_upsert_vector

_publish_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _delete_vectors_best_effort(
    business: Business,
    vector_ids: list[UUID],
    delete_vector: Callable[[Business, UUID], None],
) -> bool:
    cleaned = True
    for vector_id in vector_ids:
        try:
            delete_vector(business, vector_id)
        except Exception as error:
            cleaned = False
            logger.warning(
                "Could not delete stale Document vector %s; active revision filtering will ignore it: %s",
                vector_id,
                error,
            )
    return cleaned


def create_document_draft(source: DocumentRevision) -> DocumentRevision | None:
    with transaction.atomic():
        document = Document.objects.select_for_update().get(pk=source.document_id)
        source = DocumentRevision.objects.select_for_update().get(pk=source.pk)
        if source.status not in {DocumentRevision.Status.PUBLISHED, DocumentRevision.Status.ARCHIVED}:
            raise ValueError("A draft can only be created from a published or archived Document revision.")
        if document.revisions.filter(status=DocumentRevision.Status.DRAFT).exists():
            return None
        latest_revision = document.revisions.aggregate(number=Max("revision_number"))["number"] or 0
        return DocumentRevision.objects.create(
            document=document,
            revision_number=latest_revision + 1,
            title=source.title,
            content=source.content,
            product=source.product,
            version=source.version,
            source_name=source.source_name,
        )


def archive_document(
    revision: DocumentRevision,
    *,
    delete_vector: Callable[[Business, UUID], None] = default_delete_vector,
) -> bool:
    with _publish_lock, transaction.atomic():
        revision = DocumentRevision.objects.select_for_update().select_related("document__business").get(
            pk=revision.pk
        )
        if revision.status != DocumentRevision.Status.PUBLISHED:
            raise ValueError("Only a published Document can be archived.")
        vector_ids = list(revision.chunks.values_list("vector_id", flat=True))
        business = revision.document.business
        revision.status = DocumentRevision.Status.ARCHIVED
        revision.save(update_fields=["status", "updated_at"])
    return _delete_vectors_best_effort(business, vector_ids, delete_vector)


def delete_document_revision(
    revision: DocumentRevision,
    *,
    delete_vector: Callable[[Business, UUID], None] = default_delete_vector,
) -> bool:
    with _publish_lock, transaction.atomic():
        document = Document.objects.select_for_update().get(pk=revision.document_id)
        revision = DocumentRevision.objects.select_for_update().select_related("document__business").get(
            pk=revision.pk
        )
        if revision.status not in {DocumentRevision.Status.DRAFT, DocumentRevision.Status.ARCHIVED}:
            raise ValueError("Only a draft or archived Document revision can be deleted.")
        business = revision.document.business
        vector_ids = list(revision.chunks.values_list("vector_id", flat=True))
        revision.delete()
        if not document.revisions.exists():
            document.delete()
    return _delete_vectors_best_effort(business, vector_ids, delete_vector)


def active_document_chunks(business: Business) -> QuerySet[DocumentChunk]:
    return DocumentChunk.objects.select_related("revision").filter(
        revision__document__business=business,
        revision__status=DocumentRevision.Status.PUBLISHED,
        revision__index_status=DocumentRevision.IndexStatus.READY,
        index_status=DocumentChunk.IndexStatus.READY,
    )


def publish_document(
    revision: DocumentRevision,
    *,
    embed_document: Callable[[str], list[float]] = default_embed_document,
    upsert_vector: Callable[[Business, UUID, list[float]], None] = default_upsert_vector,
    delete_vector: Callable[[Business, UUID], None] = default_delete_vector,
) -> int:
    with _publish_lock:
        revision.refresh_from_db()
        if revision.status != DocumentRevision.Status.DRAFT:
            raise ValueError("Only a draft Document can be published.")
        try:
            previews = preview_chunks(revision)
            DocumentChunk.objects.filter(revision=revision).delete()
            revision.index_status = DocumentRevision.IndexStatus.PENDING
            revision.index_error = ""
            revision.save(update_fields=["index_status", "index_error", "updated_at"])
            chunks = [
                DocumentChunk.objects.create(
                    revision=revision, order=preview.order, heading=preview.heading, text=preview.text,
                )
                for preview in previews
            ]
            for chunk, preview in zip(chunks, previews, strict=True):
                vector = embed_document(preview.embedding_text)
                upsert_vector(revision.document.business, chunk.vector_id, vector)
            with transaction.atomic():
                previous = list(
                    DocumentRevision.objects.select_for_update().filter(
                        document=revision.document, status=DocumentRevision.Status.PUBLISHED,
                    ).exclude(pk=revision.pk)
                )
                previous_ids = [item.pk for item in previous]
                previous_vector_ids = list(
                    DocumentChunk.objects.filter(revision_id__in=previous_ids).values_list("vector_id", flat=True)
                )
                for previous_revision in previous:
                    previous_revision.status = DocumentRevision.Status.ARCHIVED
                    previous_revision.save(update_fields=["status", "updated_at"])
                DocumentChunk.objects.filter(revision=revision).update(index_status=DocumentChunk.IndexStatus.READY)
                revision.status = DocumentRevision.Status.PUBLISHED
                revision.index_status = DocumentRevision.IndexStatus.READY
                revision.index_error = ""
                revision.save(update_fields=["status", "index_status", "index_error", "updated_at"])
            _delete_vectors_best_effort(revision.document.business, previous_vector_ids, delete_vector)
            return len(chunks)
        except Exception as error:
            DocumentChunk.objects.filter(revision=revision).update(index_status=DocumentChunk.IndexStatus.FAILED)
            revision.status = DocumentRevision.Status.DRAFT
            revision.index_status = DocumentRevision.IndexStatus.FAILED
            revision.index_error = str(error)[:2000]
            revision.save(update_fields=["status", "index_status", "index_error", "updated_at"])
            raise


def search_document_chunks(
    business: Business,
    vector: list[float],
    *,
    revision: DocumentRevision | None = None,
    search_vectors: Callable[[Business, list[float], int, float, list[UUID]], list[tuple[UUID, float]]] = default_search_vectors,
) -> list[tuple[DocumentChunk, float]]:
    queryset = active_document_chunks(business)
    if revision is not None:
        queryset = queryset.filter(revision=revision)
    chunks = {chunk.vector_id: chunk for chunk in queryset}
    if not chunks:
        return []
    matches = search_vectors(business, vector, 6, settings.RAG_SCORE_THRESHOLD, list(chunks))
    return [(chunks[vector_id], score) for vector_id, score in matches if vector_id in chunks]


def test_document_retrieval(revision: DocumentRevision, question: str) -> list[tuple[DocumentChunk, float]]:
    vector = default_embed_query(question)
    return search_document_chunks(revision.document.business, vector, revision=revision)
