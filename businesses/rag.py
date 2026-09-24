from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.db import transaction

from .models import Business, KnowledgeItem

Embedding = list[float]
Embed = Callable[[str], Embedding]
UpsertVector = Callable[[Business, UUID, Embedding], None]
SearchVectors = Callable[[Business, Embedding, int, float, list[UUID]], list[tuple[UUID, float]]]
Complete = Callable[[str, list[tuple[str, str]]], str]


@dataclass(frozen=True)
class AnswerResult:
    kind: str
    text: str


def publish_item(
    item: KnowledgeItem,
    *,
    embed_document: Embed | None = None,
    upsert_vector: UpsertVector | None = None,
) -> None:
    if embed_document is None or upsert_vector is None:
        from .vector_store import embed_document as default_embed, upsert_vector as default_upsert

        embed_document = embed_document or default_embed
        upsert_vector = upsert_vector or default_upsert

    source = item.replacement_for or item
    if item.replacement_for and KnowledgeItem.objects.filter(
        business=item.business,
        question=item.question,
        answer=item.answer,
        replacement_for__isnull=True,
    ).exclude(pk=source.pk).exists():
        error = ValueError("Another Q&A for this business already has the same question and answer.")
        item.index_status = KnowledgeItem.IndexStatus.FAILED
        item.index_error = str(error)
        item.save(update_fields=["index_status", "index_error", "updated_at"])
        raise error

    try:
        vector = embed_document(item.question)
        upsert_vector(item.business, item.id, vector)
        if item.replacement_for:
            old_vector_id = source.vector_id
            with transaction.atomic():
                source.question = item.question
                source.answer = item.answer
                source.vector_id = item.id
                source.index_status = KnowledgeItem.IndexStatus.READY
                source.index_error = ""
                source.save(
                    update_fields=["question", "answer", "vector_id", "index_status", "index_error", "updated_at"]
                )
                item.delete()
            if old_vector_id and old_vector_id != source.vector_id:
                try:
                    from .vector_store import delete_vector

                    delete_vector(source.business, old_vector_id)
                except Exception:
                    pass
            return
    except Exception as error:
        item.status = KnowledgeItem.Status.DRAFT
        item.index_status = KnowledgeItem.IndexStatus.FAILED
        item.index_error = str(error)[:2000]
        item.save(update_fields=["status", "index_status", "index_error", "updated_at"])
        raise

    item.status = KnowledgeItem.Status.PUBLISHED
    item.vector_id = item.id
    item.index_status = KnowledgeItem.IndexStatus.READY
    item.index_error = ""
    item.save(update_fields=["status", "vector_id", "index_status", "index_error", "updated_at"])


def answer_question(
    business: Business,
    question: str,
    *,
    embed_query: Embed | None = None,
    search_vectors: SearchVectors | None = None,
    complete: Complete | None = None,
) -> AnswerResult:
    if not KnowledgeItem.objects.filter(
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    ).exists():
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    if embed_query is None or search_vectors is None:
        from .vector_store import embed_query as default_embed, search_vectors as default_search

        embed_query = embed_query or default_embed
        search_vectors = search_vectors or default_search
    if complete is None:
        from .openrouter import complete_answer

        complete = complete_answer

    vector = embed_query(question)
    active_vector_ids = [
        vector_id
        for vector_id in KnowledgeItem.objects.filter(
            business=business,
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
            vector_id__isnull=False,
        ).values_list("vector_id", flat=True)
        if vector_id is not None
    ]
    matches = search_vectors(
        business,
        vector,
        settings.RAG_TOP_K,
        settings.RAG_SCORE_THRESHOLD,
        active_vector_ids,
    )
    ordered_ids = [item_id for item_id, _score in matches]
    if not ordered_ids:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    rows = KnowledgeItem.objects.filter(
        vector_id__in=ordered_ids,
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    )
    by_vector_id = {row.vector_id: row for row in rows}
    knowledge = [
        (by_vector_id[item_id].question, by_vector_id[item_id].answer)
        for item_id in ordered_ids
        if item_id in by_vector_id
    ]
    if not knowledge:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    return AnswerResult("answer", complete(question, knowledge))
