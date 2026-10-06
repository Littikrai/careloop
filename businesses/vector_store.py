import hashlib
import json
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

from django.conf import settings
from qdrant_client import QdrantClient, models

from .models import Business

_clients: dict[str, QdrantClient] = {}
_embedding_models: dict[str, object] = {}
_qdrant_lock = threading.RLock()
_embedding_lock = threading.RLock()


class _LockedTokenizer:
    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        with _embedding_lock:
            return self._tokenizer(*args, **kwargs)

    def encode(self, *args: Any, **kwargs: Any) -> Any:
        with _embedding_lock:
            return self._tokenizer.encode(*args, **kwargs)

    def num_special_tokens_to_add(self, *args: Any, **kwargs: Any) -> int:
        with _embedding_lock:
            return int(self._tokenizer.num_special_tokens_to_add(*args, **kwargs))


def _client() -> QdrantClient:
    with _qdrant_lock:
        path = str(settings.QDRANT_PATH)
        if path not in _clients:
            Path(path).mkdir(parents=True, exist_ok=True)
            _clients[path] = QdrantClient(path=path)
        return _clients[path]


def reset_clients() -> None:
    with _qdrant_lock:
        for client in _clients.values():
            client.close()
        _clients.clear()
    with _embedding_lock:
        _embedding_models.clear()


def _collection_name(business: Business) -> str:
    model_signature = embedding_model_details()
    signature = {
        "model": model_signature["model"],
        "dimensions": model_signature["dimensions"],
        "max_seq_length": model_signature["max_seq_length"],
        "chunker_version": settings.DOCUMENT_CHUNKER_VERSION,
        "chunk_target_tokens": settings.DOCUMENT_CHUNK_TARGET_TOKENS,
        "chunk_max_tokens": settings.DOCUMENT_CHUNK_MAX_TOKENS,
        "prefix_strategy": model_signature["prefix_strategy"],
    }
    encoded = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()
    index_hash = hashlib.sha256(encoded).hexdigest()[:12]
    return f"business_{business.id.hex}_{index_hash}"


def _prefix_strategy() -> str:
    return "e5-passage-query-v1" if settings.EMBEDDING_MODEL.lower().startswith("intfloat/multilingual-e5-") else "none"


def document_embedding_prefix() -> str:
    return "passage: " if _prefix_strategy() == "e5-passage-query-v1" else ""


def _embedding_dimension(model: Any) -> int:
    getter = getattr(model, "get_embedding_dimension", None) or getattr(
        model, "get_sentence_embedding_dimension"
    )
    return int(getter())


def _model():
    with _embedding_lock:
        model_name = settings.EMBEDDING_MODEL
        if model_name not in _embedding_models:
            from sentence_transformers import SentenceTransformer

            _embedding_models[model_name] = SentenceTransformer(model_name, device="cpu")
        return _embedding_models[model_name]


def embedding_tokenizer():
    with _embedding_lock:
        model = _model()
        return _LockedTokenizer(model.tokenizer), int(model.max_seq_length)


def embedding_model_details() -> dict[str, str | int]:
    model = _model()
    return {
        "model": settings.EMBEDDING_MODEL,
        "dimensions": _embedding_dimension(model),
        "max_seq_length": int(model.max_seq_length),
        "prefix_strategy": _prefix_strategy(),
    }


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with _embedding_lock:
        prefix = document_embedding_prefix()
        vectors = _model().encode([f"{prefix}{text}" for text in texts], normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]


def embed_document(text: str) -> list[float]:
    return embed_documents([text])[0]


def embed_query(text: str) -> list[float]:
    with _embedding_lock:
        prefix = "query: " if _prefix_strategy() == "e5-passage-query-v1" else ""
        vector = _model().encode(f"{prefix}{text}", normalize_embeddings=True)
        return [float(value) for value in vector]


def upsert_vector(business: Business, item_id: UUID, vector: list[float]) -> None:
    with _qdrant_lock:
        client = _client()
        collection = _collection_name(business)
        if not client.collection_exists(collection):
            client.create_collection(
                collection,
                vectors_config=models.VectorParams(size=len(vector), distance=models.Distance.COSINE),
            )
        client.upsert(
            collection,
            points=[models.PointStruct(id=str(item_id), vector=vector)],
            wait=True,
        )


def delete_vector(business: Business, item_id: UUID) -> None:
    with _qdrant_lock:
        client = _client()
        collection = _collection_name(business)
        if client.collection_exists(collection):
            client.delete(
                collection,
                points_selector=models.PointIdsList(points=[str(item_id)]),
                wait=True,
            )


def search_vectors(
    business: Business,
    vector: list[float],
    limit: int,
    threshold: float,
    active_vector_ids: list[UUID] | None = None,
) -> list[tuple[UUID, float]]:
    with _qdrant_lock:
        client = _client()
        collection = _collection_name(business)
        if not client.collection_exists(collection):
            return []
        result = client.query_points(
            collection,
            query=vector,
            limit=limit,
            score_threshold=threshold,
            query_filter=(
                models.Filter(
                    must=[models.HasIdCondition(has_id=[str(item_id) for item_id in active_vector_ids])]
                )
                if active_vector_ids is not None
                else None
            )
        )
        return [(UUID(str(point.id)), float(point.score)) for point in result.points]
