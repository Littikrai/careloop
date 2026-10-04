import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.db import transaction

from .models import Business, KnowledgeItem
from .openrouter import CompletionResult

Embedding = list[float]
Embed = Callable[[str], Embedding]
UpsertVector = Callable[[Business, UUID, Embedding], None]
SearchVectors = Callable[[Business, Embedding, int, float, list[UUID]], list[tuple[UUID, float]]]
Complete = Callable[[str, list[dict[str, str | bool]]], CompletionResult]

_publish_lock = threading.Lock()


@dataclass(frozen=True)
class AnswerResult:
    kind: str
    text: str
    sources: tuple[dict[str, str], ...] = ()


def normalise_question(question: str) -> str:
    return unicodedata.normalize("NFC", " ".join(unicodedata.normalize("NFC", question).casefold().split()))


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

    # ponytail: one process lock matches local Qdrant; use a DB constraint before adding web processes.
    with _publish_lock:
        source = item.replacement_for or item
        try:
            normalized = normalise_question(item.question)
            published = KnowledgeItem.objects.filter(
                business=item.business,
                status=KnowledgeItem.Status.PUBLISHED,
                index_status=KnowledgeItem.IndexStatus.READY,
            ).exclude(pk=source.pk)
            if any(normalise_question(question) == normalized for question in published.values_list("question", flat=True)):
                raise ValueError("Another published Q&A for this business has the same normalized question.")
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
    published = list(KnowledgeItem.objects.filter(
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    ))
    if not published:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    if complete is None:
        from .openrouter import complete_answer

        complete = complete_answer

    normalized = normalise_question(question)
    exact = [item for item in published if normalise_question(item.question) == normalized]
    if len(exact) > 1:
        return AnswerResult("needs_clarification", "Could you clarify which product or version you mean?")
    if exact:
        matches = exact
    else:
        if embed_query is None or search_vectors is None:
            from .vector_store import embed_query as default_embed, search_vectors as default_search

            embed_query = embed_query or default_embed
            search_vectors = search_vectors or default_search
        vector = embed_query(question)
        active_vector_ids = [item.vector_id for item in published if item.vector_id is not None]
        search_results = search_vectors(
            business, vector, settings.RAG_TOP_K, settings.RAG_SCORE_THRESHOLD, active_vector_ids
        )
        by_vector_id = {item.vector_id: item for item in published}
        matches = [by_vector_id[item_id] for item_id, _score in search_results if item_id in by_vector_id]

    if not matches:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    sources: list[dict[str, str | bool]] = [
        {
            "id": f"src-{index}", "type": "qa", "question": item.question,
            "answer": item.answer, "authoritative": bool(exact),
        }
        for index, item in enumerate(matches[:settings.RAG_TOP_K], start=1)
    ]
    completion = complete(question, sources)
    if completion.status == "insufficient_knowledge":
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)
    cited = tuple(
        {"type": "qa", "label": "Verified answer"}
        for source in sources if source["id"] in completion.source_ids
    )
    return AnswerResult(completion.status, completion.answer, cited)
