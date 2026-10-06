import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from django.conf import settings
from django.db import connection, transaction

from .document_knowledge import preview_document_chunks
from .models import Business, DocumentChunk, DocumentRevision, KnowledgeItem
from .vector_store import embedding_model_details, reset_clients, upsert_vector

SIGNATURE_FILENAME = "knowledge_index_signature.json"
PENDING_FILENAME = "knowledge_index_rebuild_pending.json"


def current_signature() -> dict[str, str | int]:
    return {
        **embedding_model_details(),
        "chunker_version": settings.DOCUMENT_CHUNKER_VERSION,
        "chunk_target_tokens": settings.DOCUMENT_CHUNK_TARGET_TOKENS,
        "chunk_max_tokens": settings.DOCUMENT_CHUNK_MAX_TOKENS,
    }


def _signature_path() -> Path:
    return Path(settings.DATA_DIR) / SIGNATURE_FILENAME


def _pending_path() -> Path:
    return Path(settings.DATA_DIR) / PENDING_FILENAME


def pending_backup_dir() -> Path | None:
    pending = _read_json(_pending_path())
    if not pending or not pending.get("backup_dir"):
        return None
    backup_dir = Path(str(pending["backup_dir"]))
    return backup_dir if (backup_dir / "manifest.json").is_file() else None


def _signature_hash(signature: dict[str, str | int]) -> str:
    encoded = json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read index state file {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Index state file {path} must contain a JSON object.")
    return value


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _make_backup(target_hash: str) -> Path:
    data_dir = Path(settings.DATA_DIR)
    database_path = Path(connection.settings_dict["NAME"])
    if connection.settings_dict["ENGINE"] != "django.db.backends.sqlite3":
        raise RuntimeError("Offline index rebuild backup currently supports the SQLite database configured by this app.")
    qdrant_path = Path(settings.QDRANT_PATH)
    data_root = data_dir.resolve()
    qdrant_root = qdrant_path.resolve()
    if qdrant_root == data_root or data_root.is_relative_to(qdrant_root):
        raise RuntimeError("QDRANT_PATH cannot contain DATA_DIR because backups are stored under DATA_DIR.")
    if not database_path.is_file() and "mode=memory" not in str(connection.settings_dict["NAME"]):
        raise RuntimeError(f"Cannot back up missing SQLite database: {database_path}")

    pending = _read_json(_pending_path())
    if pending and pending.get("target_hash") == target_hash:
        existing = Path(str(pending.get("backup_dir", "")))
        if (existing / "manifest.json").is_file() and (existing / "db.sqlite3").is_file():
            return existing

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = data_dir / "backups" / "knowledge-index" / f"{timestamp}-{target_hash}-{uuid4().hex[:6]}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_database = backup_dir / "db.sqlite3"
    connection.ensure_connection()
    raw_connection = connection.connection
    if not isinstance(raw_connection, sqlite3.Connection):
        raise RuntimeError("The configured database connection is not SQLite.")
    with sqlite3.connect(backup_database) as destination:
        raw_connection.backup(destination)

    signature = _read_json(_signature_path())
    if signature is not None:
        shutil.copy2(_signature_path(), backup_dir / SIGNATURE_FILENAME)

    backup_qdrant = backup_dir / "qdrant"
    if qdrant_path.exists():
        shutil.copytree(qdrant_path, backup_qdrant)
        qdrant_present = True
    else:
        qdrant_present = False

    _write_json(
        backup_dir / "manifest.json",
        {
            "target_signature_hash": target_hash,
            "created_at": timestamp,
            "database": "db.sqlite3",
            "qdrant": "qdrant" if qdrant_present else None,
            "index_signature": SIGNATURE_FILENAME if signature is not None else None,
        },
    )
    _write_json(_pending_path(), {"target_hash": target_hash, "backup_dir": str(backup_dir)})
    return backup_dir


def rebuild_index_if_needed(
    *,
    embed_documents=None,
    vector_upsert=None,
) -> tuple[bool, Path | None]:
    from .vector_store import embed_documents as default_embed_documents

    embed_documents = embed_documents or default_embed_documents
    vector_upsert = vector_upsert or upsert_vector
    signature = current_signature()
    target_hash = _signature_hash(signature)
    if _read_json(_signature_path()) == signature:
        _pending_path().unlink(missing_ok=True)
        return False, None

    knowledge_items = list(
        KnowledgeItem.objects.filter(status=KnowledgeItem.Status.PUBLISHED).select_related("business")
    )
    revisions = list(
        DocumentRevision.objects.filter(status=DocumentRevision.Status.PUBLISHED)
        .select_related("document__business")
        .order_by("document_id", "revision_number", "id")
    )
    candidates: list[tuple[Business, UUID, str]] = []
    chunks: list[DocumentChunk] = []
    for item in knowledge_items:
        candidates.append((item.business, item.vector_id or item.pk, item.question))
    for revision in revisions:
        previews = preview_document_chunks(revision)
        for preview in previews:
            vector_id = uuid5(revision.pk, f"{target_hash}:{preview.order}")
            candidates.append((revision.document.business, vector_id, preview.embedding_text))
            chunks.append(
                DocumentChunk(
                    revision=revision,
                    order=preview.order,
                    heading=preview.heading,
                    text=preview.text,
                    vector_id=vector_id,
                    index_status=DocumentChunk.IndexStatus.READY,
                )
            )

    if not candidates:
        _write_json(_signature_path(), signature)
        _pending_path().unlink(missing_ok=True)
        return True, None

    backup_dir = _make_backup(target_hash)
    batch_size = max(1, settings.DOCUMENT_EMBED_BATCH_SIZE)
    expected_dimensions = int(signature["dimensions"])
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        vectors = embed_documents([text for _business, _vector_id, text in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding model returned a different number of vectors than input records.")
        for (business, vector_id, _text), vector in zip(batch, vectors, strict=True):
            if len(vector) != expected_dimensions:
                raise RuntimeError(
                    f"Embedding model returned {len(vector)} dimensions; expected {expected_dimensions}."
                )
            vector_upsert(business, vector_id, vector)

    with transaction.atomic():
        for item in knowledge_items:
            item.vector_id = item.vector_id or item.pk
            item.index_status = KnowledgeItem.IndexStatus.READY
            item.index_error = ""
        KnowledgeItem.objects.bulk_update(knowledge_items, ["vector_id", "index_status", "index_error"])
        DocumentChunk.objects.all().delete()
        DocumentChunk.objects.bulk_create(chunks)
        for revision in revisions:
            revision.index_status = DocumentRevision.IndexStatus.READY
            revision.index_error = ""
        DocumentRevision.objects.bulk_update(revisions, ["index_status", "index_error"])

    _write_json(_signature_path(), signature)
    _pending_path().unlink(missing_ok=True)
    return True, backup_dir


def restore_index_backup(backup_dir: str | Path) -> None:
    source = Path(backup_dir).resolve()
    manifest = _read_json(source / "manifest.json")
    database_backup = source / "db.sqlite3"
    if manifest is None or not database_backup.is_file():
        raise ValueError("Backup must contain manifest.json and db.sqlite3.")

    database_path = Path(connection.settings_dict["NAME"])
    qdrant_path = Path(settings.QDRANT_PATH)
    qdrant_backup = source / "qdrant"
    restore_suffix = uuid4().hex
    staged_database = database_path.with_name(f".{database_path.name}.{restore_suffix}.restore")
    staged_qdrant = qdrant_path.with_name(f".{qdrant_path.name}.{restore_suffix}.restore")
    previous_database = database_path.with_name(f".{database_path.name}.{restore_suffix}.previous")
    previous_qdrant = qdrant_path.with_name(f".{qdrant_path.name}.{restore_suffix}.previous")
    staged_signature = _signature_path().with_name(f".{SIGNATURE_FILENAME}.{restore_suffix}.restore")
    previous_signature = _signature_path().with_name(f".{SIGNATURE_FILENAME}.{restore_suffix}.previous")
    had_database = database_path.exists()
    had_qdrant = qdrant_path.exists()
    had_signature = _signature_path().exists()

    shutil.copy2(database_backup, staged_database)
    if manifest.get("qdrant"):
        if not qdrant_backup.is_dir():
            staged_database.unlink(missing_ok=True)
            raise ValueError("Backup manifest references a missing Qdrant directory.")
        shutil.copytree(qdrant_backup, staged_qdrant)
    signature_backup = source / SIGNATURE_FILENAME
    if signature_backup.is_file():
        shutil.copy2(signature_backup, staged_signature)

    reset_clients()
    connection.close()
    try:
        if had_database:
            os.replace(database_path, previous_database)
        if had_qdrant:
            os.replace(qdrant_path, previous_qdrant)
        if staged_qdrant.exists():
            qdrant_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_qdrant, qdrant_path)
        os.replace(staged_database, database_path)
        if had_signature:
            os.replace(_signature_path(), previous_signature)
        if staged_signature.exists():
            os.replace(staged_signature, _signature_path())
        else:
            _signature_path().unlink(missing_ok=True)
    except Exception:
        if database_path.exists() and (previous_database.exists() or not had_database):
            database_path.unlink()
        if previous_database.exists():
            os.replace(previous_database, database_path)
        if qdrant_path.exists() and (previous_qdrant.exists() or not had_qdrant):
            shutil.rmtree(qdrant_path)
        if previous_qdrant.exists():
            os.replace(previous_qdrant, qdrant_path)
        if _signature_path().exists() and (previous_signature.exists() or not had_signature):
            _signature_path().unlink()
        if previous_signature.exists():
            os.replace(previous_signature, _signature_path())
        raise
    else:
        previous_database.unlink(missing_ok=True)
        if previous_qdrant.exists():
            shutil.rmtree(previous_qdrant)
        previous_signature.unlink(missing_ok=True)
        _pending_path().unlink(missing_ok=True)
    finally:
        staged_database.unlink(missing_ok=True)
        if staged_qdrant.exists():
            shutil.rmtree(staged_qdrant)
        staged_signature.unlink(missing_ok=True)
