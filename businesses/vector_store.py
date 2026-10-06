import hashlib
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
    model_hash = hashlib.sha256(settings.EMBEDDING_MODEL.encode()).hexdigest()[:12]
    return f"business_{business.id.hex}_{model_hash}"


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


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with _embedding_lock:
        vectors = _model().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]


def embed_document(text: str) -> list[float]:
    return embed_documents([text])[0]


def embed_query(text: str) -> list[float]:
    return embed_document(text)


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
