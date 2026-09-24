from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings

from .models import Business, KnowledgeItem

Embedding = list[float]
Embed = Callable[[str], Embedding]
UpsertVector = Callable[[Business, UUID, Embedding], None]
SearchVectors = Callable[[Business, Embedding, int, float], list[tuple[UUID, float]]]
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

    try:
        vector = embed_document(item.question)
        upsert_vector(item.business, item.id, vector)
    except Exception as error:
        item.status = KnowledgeItem.Status.DRAFT
        item.index_status = KnowledgeItem.IndexStatus.FAILED
        item.index_error = str(error)[:2000]
        item.save(update_fields=["status", "index_status", "index_error", "updated_at"])
        raise

    item.status = KnowledgeItem.Status.PUBLISHED
    item.index_status = KnowledgeItem.IndexStatus.READY
    item.index_error = ""
    item.save(update_fields=["status", "index_status", "index_error", "updated_at"])


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
    matches = search_vectors(
        business,
        vector,
        settings.RAG_TOP_K,
        settings.RAG_SCORE_THRESHOLD,
    )
    ordered_ids = [item_id for item_id, _score in matches]
    if not ordered_ids:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    rows = KnowledgeItem.objects.filter(
        id__in=ordered_ids,
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    )
    by_id = {row.id: row for row in rows}
    knowledge = [(by_id[item_id].question, by_id[item_id].answer) for item_id in ordered_ids if item_id in by_id]
    if not knowledge:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    return AnswerResult("answer", complete(question, knowledge))
