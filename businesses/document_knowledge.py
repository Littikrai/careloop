import logging
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID, uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Max, QuerySet
from django.utils import timezone

from .document_chunks import preview_chunks
from .models import Business, Document, DocumentChunk, DocumentIndexAttempt, DocumentRevision
from .vector_store import delete_vector as default_delete_vector
from .vector_store import embed_documents as default_embed_documents
from .vector_store import embed_query as default_embed_query
from .vector_store import embedding_model_access
from .vector_store import search_vectors as default_search_vectors
from .vector_store import upsert_vector as default_upsert_vector

_document_lifecycle_lock = threading.Lock()
_publish_lock = threading.Lock()
_process_id = uuid4().hex
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
    with _document_lifecycle_lock, transaction.atomic():
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
    with _document_lifecycle_lock, transaction.atomic():
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


def preview_document_chunks(revision: DocumentRevision):
    with embedding_model_access():
        chunks = preview_chunks(revision)
    maximum = settings.DOCUMENT_MAX_CHUNKS
    if len(chunks) > maximum:
        raise ValueError(f"Document preview has {len(chunks)} chunks; it exceeds the maximum of {maximum} chunks.")
    return chunks


def recover_document_index_attempts(*, at_startup: bool = False) -> int:
    """Mark abandoned attempts interrupted; startup knows all old processes are gone."""
    now = timezone.now()
    attempts = DocumentIndexAttempt.objects.filter(status=DocumentIndexAttempt.Status.RUNNING)
    if not at_startup:
        attempts = attempts.filter(lease_expires_at__lte=now)
    recovered = 0
    with transaction.atomic():
        for attempt in attempts.select_related("revision").select_for_update():
            attempt.status = DocumentIndexAttempt.Status.INTERRUPTED
            attempt.finished_at = now
            attempt.heartbeat_at = now
            attempt.error = "Indexing was interrupted by a process restart or expired lease."
            attempt.save(update_fields=["status", "finished_at", "heartbeat_at", "error"])
            revision = attempt.revision
            if revision.status == DocumentRevision.Status.DRAFT:
                revision.index_status = DocumentRevision.IndexStatus.INTERRUPTED
                revision.index_error = attempt.error
                revision.save(update_fields=["index_status", "index_error", "updated_at"])
            recovered += 1
    return recovered


def publish_document(
    revision: DocumentRevision,
    *,
    embed_documents: Callable[[list[str]], list[list[float]]] = default_embed_documents,
    upsert_vector: Callable[[Business, UUID, list[float]], None] = default_upsert_vector,
    delete_vector: Callable[[Business, UUID], None] = default_delete_vector,
) -> int:
    if not _publish_lock.acquire(blocking=False):
        raise RuntimeError("Another Document is being indexed. Try again after it finishes.")
    try:
        with _document_lifecycle_lock:
            return _publish_document_locked(
                revision,
                embed_documents=embed_documents,
                upsert_vector=upsert_vector,
                delete_vector=delete_vector,
            )
    finally:
        _publish_lock.release()


def _publish_document_locked(
    revision: DocumentRevision,
    *,
    embed_documents: Callable[[list[str]], list[list[float]]],
    upsert_vector: Callable[[Business, UUID, list[float]], None],
    delete_vector: Callable[[Business, UUID], None],
) -> int:
    revision.refresh_from_db()
    if revision.status != DocumentRevision.Status.DRAFT:
        raise ValueError("Only a draft Document can be published.")
    recover_document_index_attempts()
    started_at = time.monotonic()
    budget = settings.DOCUMENT_INDEX_BUDGET_SECONDS
    lease_seconds = settings.DOCUMENT_INDEX_LEASE_SECONDS
    now = timezone.now()
    attempt = DocumentIndexAttempt.objects.create(
        revision=revision,
        owner_id=_process_id,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
        heartbeat_at=now,
    )

    def check_budget() -> None:
        if time.monotonic() - started_at >= budget:
            raise TimeoutError(f"Document indexing exceeded its {budget}-second time budget.")

    try:
        check_budget()
        previews = preview_document_chunks(revision)
        check_budget()
        attempt.chunks_total = len(previews)
        attempt.heartbeat_at = timezone.now()
        attempt.lease_expires_at = attempt.heartbeat_at + timedelta(seconds=lease_seconds)
        attempt.save(update_fields=["chunks_total", "heartbeat_at", "lease_expires_at"])

        stale_vector_ids = list(DocumentChunk.objects.filter(revision=revision).values_list("vector_id", flat=True))
        DocumentChunk.objects.filter(revision=revision).delete()
        _delete_vectors_best_effort(revision.document.business, stale_vector_ids, delete_vector)
        revision.index_status = DocumentRevision.IndexStatus.PENDING
        revision.index_error = ""
        revision.save(update_fields=["index_status", "index_error", "updated_at"])
        chunks = DocumentChunk.objects.bulk_create([
            DocumentChunk(
                revision=revision, order=preview.order, heading=preview.heading, text=preview.text,
            )
            for preview in previews
        ])
        batch_size = max(1, settings.DOCUMENT_EMBED_BATCH_SIZE)
        completed = 0
        for offset in range(0, len(chunks), batch_size):
            check_budget()
            batch = chunks[offset : offset + batch_size]
            texts = [preview.embedding_text for preview in previews[offset : offset + batch_size]]
            vectors = embed_documents(texts)
            if len(vectors) != len(batch):
                raise ValueError("Embedding model returned a different number of vectors than input chunks.")
            check_budget()
            for chunk, vector in zip(batch, vectors, strict=True):
                upsert_vector(revision.document.business, chunk.vector_id, vector)
                check_budget()
            completed += len(batch)
            heartbeat = timezone.now()
            DocumentIndexAttempt.objects.filter(pk=attempt.pk).update(
                chunks_completed=completed,
                heartbeat_at=heartbeat,
                lease_expires_at=heartbeat + timedelta(seconds=lease_seconds),
            )
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
            attempt.status = DocumentIndexAttempt.Status.SUCCEEDED
            attempt.finished_at = timezone.now()
            attempt.heartbeat_at = attempt.finished_at
            attempt.chunks_completed = len(chunks)
            attempt.save(update_fields=["status", "finished_at", "heartbeat_at", "chunks_completed"])
        _delete_vectors_best_effort(revision.document.business, previous_vector_ids, delete_vector)
        return len(chunks)
    except Exception as error:
        candidate_vector_ids = list(DocumentChunk.objects.filter(revision=revision).values_list("vector_id", flat=True))
        DocumentChunk.objects.filter(revision=revision).update(index_status=DocumentChunk.IndexStatus.FAILED)
        revision.status = DocumentRevision.Status.DRAFT
        revision.index_status = DocumentRevision.IndexStatus.FAILED
        revision.index_error = str(error)[:2000]
        revision.save(update_fields=["status", "index_status", "index_error", "updated_at"])
        finished = timezone.now()
        DocumentIndexAttempt.objects.filter(pk=attempt.pk).update(
            status=DocumentIndexAttempt.Status.FAILED,
            finished_at=finished,
            heartbeat_at=finished,
            error=str(error)[:2000],
        )
        _delete_vectors_best_effort(revision.document.business, candidate_vector_ids, delete_vector)
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
