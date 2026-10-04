import json
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.db import transaction

from .document_knowledge import active_document_chunks, search_document_chunks
from .models import Business, DocumentChunk, KnowledgeItem
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


def _without_repeated_document_text(text: str, earlier_texts: list[str]) -> str:
    for earlier in earlier_texts:
        if text in earlier:
            return ""
        for length in range(min(len(text), len(earlier)), 15, -1):
            if text.startswith(earlier[-length:]):
                text = text[length:].lstrip()
                break
            if text.endswith(earlier[:length]):
                text = text[:-length].rstrip()
                break
    return text


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
    # ponytail: scans published Q&A for exact Unicode matches; persist/index normalized questions if this grows large.
    published = list(KnowledgeItem.objects.filter(
        business=business,
        status=KnowledgeItem.Status.PUBLISHED,
        index_status=KnowledgeItem.IndexStatus.READY,
    ))
    has_documents = active_document_chunks(business).exists()
    if not published and not has_documents:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    if complete is None:
        from .openrouter import complete_answer

        complete = complete_answer

    normalized = normalise_question(question)
    exact = [item for item in published if normalise_question(item.question) == normalized]
    if len(exact) > 1:
        return AnswerResult("needs_clarification", "Could you clarify which product or version you mean?")
    ranked: list[tuple[float, str, KnowledgeItem | DocumentChunk]] = [
        (float("inf"), "qa", item) for item in exact
    ]
    if not exact or has_documents:
        if embed_query is None or search_vectors is None:
            from .vector_store import embed_query as default_embed, search_vectors as default_search

            embed_query = embed_query or default_embed
            search_vectors = search_vectors or default_search
        vector = embed_query(question)
        if published:
            by_vector_id = {item.vector_id: item for item in published}
            active_vector_ids = [item.vector_id for item in published if item.vector_id is not None]
            search_results = search_vectors(
                business, vector, min(settings.RAG_TOP_K, 3), settings.RAG_SCORE_THRESHOLD, active_vector_ids
            )
            ranked.extend(
                (score, "qa", by_vector_id[item_id]) for item_id, score in search_results
                if item_id in by_vector_id and by_vector_id[item_id] not in exact
            )
        if has_documents:
            ranked.extend(
                (score, "document", chunk)
                for chunk, score in search_document_chunks(business, vector, search_vectors=search_vectors)
            )

    if not ranked:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)

    sources: list[dict[str, str | bool]] = []
    public_sources: dict[str, dict[str, str]] = {}
    seen_texts: set[str] = set()
    selected_document_texts: dict[UUID, list[str]] = {}
    for score, kind, item in sorted(ranked, key=lambda match: match[0], reverse=True):
        if len(sources) >= 6:
            break
        source_id = f"src-{len(sources) + 1}"
        if kind == "qa":
            assert isinstance(item, KnowledgeItem)
            text_key = f"qa:{item.question}:{item.answer}"
            source: dict[str, str | bool] = {
                "id": source_id, "type": "qa", "question": item.question,
                "answer": item.answer, "authoritative": bool(exact and item.pk == exact[0].pk),
            }
            public = {"type": "qa", "label": "Verified answer"}
        else:
            assert isinstance(item, DocumentChunk)
            revision = item.revision
            document_group = revision.id
            document_text = _without_repeated_document_text(
                item.text, selected_document_texts.get(document_group, [])
            )
            if not document_text:
                continue
            text_key = f"document:{normalise_question(revision.product)}:{normalise_question(revision.version)}:{normalise_question(item.text)}"
            source = {
                "id": source_id, "type": "document", "title": revision.title,
                "heading": item.heading, "product": revision.product, "version": revision.version,
                "text": document_text, "authoritative": False,
            }
            label = " · ".join(value for value in (revision.title, item.heading, revision.product, revision.version) if value)
            public = {"type": "document", "label": label, "title": revision.title}
            if item.heading:
                public["heading"] = item.heading
            if revision.product:
                public["product"] = revision.product
            if revision.version:
                public["version"] = revision.version
        if text_key in seen_texts:
            continue
        if len(json.dumps([*sources, source], ensure_ascii=False)) > 8000:
            continue
        seen_texts.add(text_key)
        sources.append(source)
        public_sources[source_id] = public
        if kind == "document":
            assert isinstance(item, DocumentChunk)
            selected_document_texts.setdefault(document_group, []).append(item.text)

    if not sources:
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)
    completion = complete(question, sources)
    if completion.status == "insufficient_knowledge":
        return AnswerResult("insufficient_knowledge", settings.RAG_INSUFFICIENT_MESSAGE)
    cited = tuple(public_sources[source_id] for source_id in completion.source_ids)
    return AnswerResult(completion.status, completion.answer, cited)
