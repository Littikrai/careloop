import threading
from collections.abc import Callable
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from .document_chunks import preview_chunks
from .models import Business, DocumentChunk, DocumentRevision
from .vector_store import embed_document as default_embed_document
from .vector_store import embed_query as default_embed_query
from .vector_store import search_vectors as default_search_vectors
from .vector_store import upsert_vector as default_upsert_vector

_publish_lock = threading.Lock()


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
                DocumentChunk.objects.filter(revision=revision).update(index_status=DocumentChunk.IndexStatus.READY)
                revision.status = DocumentRevision.Status.PUBLISHED
                revision.index_status = DocumentRevision.IndexStatus.READY
                revision.index_error = ""
                revision.save(update_fields=["status", "index_status", "index_error", "updated_at"])
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
