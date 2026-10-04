import hashlib
from pathlib import Path
from uuid import UUID

from django.conf import settings
from qdrant_client import QdrantClient, models

from .models import Business

_clients: dict[str, QdrantClient] = {}
_embedding_models: dict[str, object] = {}


def _client() -> QdrantClient:
    path = str(settings.QDRANT_PATH)
    if path not in _clients:
        Path(path).mkdir(parents=True, exist_ok=True)
        _clients[path] = QdrantClient(path=path)
    return _clients[path]


def reset_clients() -> None:
    for client in _clients.values():
        client.close()
    _clients.clear()
    _embedding_models.clear()


def _collection_name(business: Business) -> str:
    model_hash = hashlib.sha256(settings.EMBEDDING_MODEL.encode()).hexdigest()[:12]
    return f"business_{business.id.hex}_{model_hash}"


def _model():
    model_name = settings.EMBEDDING_MODEL
    if model_name not in _embedding_models:
        from sentence_transformers import SentenceTransformer

        _embedding_models[model_name] = SentenceTransformer(model_name, device="cpu")
    return _embedding_models[model_name]


def embedding_tokenizer():
    model = _model()
    return model.tokenizer, int(model.max_seq_length)


def _embed(text: str) -> list[float]:
    vector = _model().encode(text, normalize_embeddings=True)
    return [float(value) for value in vector]


def embed_document(text: str) -> list[float]:
    return _embed(text)


def embed_query(text: str) -> list[float]:
    return _embed(text)


def upsert_vector(business: Business, item_id: UUID, vector: list[float]) -> None:
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
        ),
    )
    return [(UUID(str(point.id)), float(point.score)) for point in result.points]
