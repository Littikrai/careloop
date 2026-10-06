import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

from django.test import TestCase, TransactionTestCase, override_settings

from . import vector_store
from .document_chunks import PreviewChunk, preview_chunks
from .document_knowledge import search_document_chunks
from .index_rebuild import PENDING_FILENAME, SIGNATURE_FILENAME, rebuild_index_if_needed, restore_index_backup
from .models import Business, Document, DocumentChunk, DocumentRevision, KnowledgeItem


class EmbeddingPrefixTests(TestCase):
    def test_e5_encodes_documents_as_passages_and_questions_as_queries(self):
        calls = []

        class FakeModel:
            def encode(self, values, normalize_embeddings=True):
                calls.append(values)
                return [[0.25, 0.75] for _value in values] if isinstance(values, list) else [0.25, 0.75]

        model_name = "intfloat/multilingual-e5-small"
        with override_settings(EMBEDDING_MODEL=model_name), patch.dict(
            vector_store._embedding_models, {model_name: FakeModel()}
        ):
            self.assertEqual(vector_store.embed_documents(["A product manual"]), [[0.25, 0.75]])
            self.assertEqual(vector_store.embed_query("How fast is it?"), [0.25, 0.75])

        self.assertEqual(calls, [["passage: A product manual"], "query: How fast is it?"])

    def test_collection_changes_with_model_and_chunker_signature(self):
        business = Business(id=UUID("a7a11c84-0711-4df3-b674-9a9dd726a0dc"), name="Shop")
        details = {
            "model": "intfloat/multilingual-e5-small",
            "dimensions": 384,
            "max_seq_length": 512,
            "prefix_strategy": "e5-passage-query-v1",
        }
        with override_settings(EMBEDDING_MODEL="intfloat/multilingual-e5-small"), patch(
            "businesses.vector_store.embedding_model_details", return_value=details,
        ):
            original = vector_store._collection_name(business)
            with override_settings(DOCUMENT_CHUNK_TARGET_TOKENS=192):
                target_changed = vector_store._collection_name(business)
        self.assertNotEqual(original, target_changed)

    def test_delete_before_embedding_uses_the_loaded_model_collection_namespace(self):
        business = Business(id=UUID("a7a11c84-0711-4df3-b674-9a9dd726a0dc"), name="Shop")
        model_name = "intfloat/multilingual-e5-small"
        deleted_from = []

        class FakeModel:
            max_seq_length = 512

            def get_sentence_embedding_dimension(self):
                return 3

        class FakeClient:
            def collection_exists(self, collection):
                return True

            def delete(self, collection, *, points_selector, wait):
                deleted_from.append(collection)

        with (
            override_settings(EMBEDDING_MODEL=model_name),
            patch.dict(vector_store._embedding_models, {}, clear=True),
            patch("sentence_transformers.SentenceTransformer", return_value=FakeModel()),
            patch("businesses.vector_store._client", return_value=FakeClient()),
        ):
            self.assertNotIn(model_name, vector_store._embedding_models)
            vector_store.delete_vector(business, UUID("e0f0a807-8fba-455a-a32a-a8ca10b4d463"))
            collection_after_model_load = vector_store._collection_name(business)

        self.assertEqual(deleted_from, [collection_after_model_load])


class KnowledgeIndexRebuildTests(TransactionTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "data"
        self.qdrant_dir = self.data_dir / "qdrant"
        self.qdrant_dir.mkdir(parents=True)
        (self.qdrant_dir / "old-index.txt").write_text("existing vectors", encoding="utf-8")
        self.override = override_settings(
            DATA_DIR=self.data_dir,
            QDRANT_PATH=str(self.qdrant_dir),
            DOCUMENT_EMBED_BATCH_SIZE=2,
        )
        self.override.enable()
        self.business = Business.objects.create(name="Fish shop")
        self.document = Document.objects.create(business=self.business)
        self.revision = DocumentRevision.objects.create(
            document=self.document,
            revision_number=1,
            title="Pump specs",
            product="AquaFlow P200",
            content="Source of truth",
            status=DocumentRevision.Status.PUBLISHED,
            index_status=DocumentRevision.IndexStatus.READY,
        )
        self.old_chunk = DocumentChunk.objects.create(
            revision=self.revision,
            order=1,
            text="Old indexed chunk",
            index_status=DocumentChunk.IndexStatus.READY,
        )
        self.qa = KnowledgeItem.objects.create(
            business=self.business,
            question="How fast is AquaFlow?",
            answer="1,200 L/h",
            status=KnowledgeItem.Status.PUBLISHED,
        )
        self.signature = {
            "model": "intfloat/multilingual-e5-small",
            "dimensions": 3,
            "max_seq_length": 512,
            "prefix_strategy": "e5-passage-query-v1",
            "chunker_version": 3,
            "chunk_target_tokens": 224,
            "chunk_max_tokens": 256,
        }

    def tearDown(self):
        self.override.disable()
        self.temp.cleanup()

    def _preview(self):
        return [
            PreviewChunk(1, "Specs", "Weight: 620 g", "heading: Specs\nWeight: 620 g", 28),
            PreviewChunk(2, "Specs", "Power: 18 W", "heading: Specs\nPower: 18 W", 26),
        ]

    def _patches(self, upsert, embed=None):
        return (
            patch("businesses.index_rebuild.current_signature", return_value=self.signature),
            patch("businesses.index_rebuild.preview_document_chunks", return_value=self._preview()),
            patch(
                "businesses.index_rebuild.upsert_vector",
                side_effect=upsert,
            ),
            patch(
                "businesses.vector_store.embed_documents",
                side_effect=embed or (lambda texts: [[0.1, 0.2, 0.3] for _text in texts]),
            ),
        )

    def test_rebuild_indexes_published_qa_and_documents_before_switching_rows(self):
        embedded = []
        upserted = []

        def upsert(business, vector_id, vector):
            upserted.append((business.pk, vector_id, vector))
            self.assertEqual(list(DocumentChunk.objects.values_list("text", flat=True)), ["Old indexed chunk"])

        def embed(texts):
            embedded.extend(texts)
            return [[0.1, 0.2, 0.3] for _text in texts]

        patches = self._patches(upsert, embed)
        with patches[0], patches[1], patches[2], patches[3]:
            rebuilt, backup = rebuild_index_if_needed()

        self.assertTrue(rebuilt)
        assert backup is not None
        self.assertTrue((backup / "db.sqlite3").is_file())
        self.assertTrue((backup / "qdrant" / "old-index.txt").is_file())
        self.assertEqual(embedded[0], self.qa.question)
        self.assertIn("Weight: 620 g", " ".join(embedded))
        self.assertEqual(len(upserted), 3)
        self.assertNotEqual(upserted[-2][1], self.old_chunk.vector_id)
        self.assertEqual(list(DocumentChunk.objects.filter(revision=self.revision).values_list("text", flat=True)), [
            "Weight: 620 g", "Power: 18 W",
        ])
        self.assertTrue(all(chunk.index_status == DocumentChunk.IndexStatus.READY for chunk in DocumentChunk.objects.all()))
        self.qa.refresh_from_db()
        self.assertEqual(self.qa.index_status, KnowledgeItem.IndexStatus.READY)
        self.assertEqual(json.loads((self.data_dir / SIGNATURE_FILENAME).read_text()), self.signature)
        self.assertFalse((self.data_dir / PENDING_FILENAME).exists())

    def test_rebuilt_thai_markdown_is_readable_through_document_retrieval(self):
        content = (
            "# ภาพรวมสินค้า\n"
            "AquaFlow P200 เป็นปั๊มน้ำหมุนเวียนสำหรับตู้ปลาน้ำจืด\n\n"
            "## ข้อมูลจำเพาะ\n"
            "- น้ำหนักตัวเครื่อง: 620 กรัม\n"
            "  รวมน้ำหนักสายไฟและข้อต่อ\n"
            "- กำลังไฟสูงสุด: 18 วัตต์\n\n"
            "| รายการ | ค่า |\n"
            "| --- | --- |\n"
            "| อัตราการไหล | 1,200 ลิตร/ชั่วโมง |\n"
            "| ขนาด | 8 × 11 × 9 เซนติเมตร |\n\n"
            "## วิธีดูแลรักษา\n"
            "ตรวจฟองน้ำ ใบพัด และท่อเป็นประจำ "
            "เพื่อให้ปั๊มน้ำหมุนเวียนทำงานได้ตามปกติและช่วยดูแลคุณภาพน้ำในตู้ปลา "
            "ควรถอดปลั๊กก่อนทำความสะอาดทุกครั้ง และห้ามให้เครื่องทำงานโดยไม่มีน้ำ "
            "หากอัตราการไหลลดลงให้ตรวจดูการอุดตันก่อนใช้งานต่อ"
        )
        DocumentRevision.objects.filter(pk=self.revision.pk).update(content=content)
        self.revision.refresh_from_db()
        embedded_texts = []

        class CharacterTokenizer:
            def __call__(self, text, *, add_special_tokens=False, return_offsets_mapping=False, verbose=True):
                offsets = [(index, index + 1) for index, character in enumerate(text) if not character.isspace()]
                return {"input_ids": [ord(text[start]) for start, _end in offsets], "offset_mapping": offsets}

            def encode(self, text, *, add_special_tokens=False):
                tokens = self(text)["input_ids"]
                return [1, *tokens, 2] if add_special_tokens else tokens

            def num_special_tokens_to_add(self, *, pair=False):
                return 2

        def embed(texts):
            embedded_texts.extend(texts)
            return [[0.1, 0.2, 0.3] for _text in texts]

        with (
            patch("businesses.index_rebuild.current_signature", return_value=self.signature),
            patch("businesses.index_rebuild.upsert_vector"),
            patch("businesses.vector_store.embed_documents", side_effect=embed),
            patch("businesses.document_chunks.embedding_tokenizer", return_value=(CharacterTokenizer(), 512)),
        ):
            rebuilt, backup = rebuild_index_if_needed()

        self.assertTrue(rebuilt)
        self.assertIsNotNone(backup)
        self.assertTrue(any("passage:" not in text and "น้ำหนักตัวเครื่อง" in text for text in embedded_texts))
        self.assertTrue(any(chunk.token_count <= 256 for chunk in preview_chunks(
            self.revision, tokenizer=CharacterTokenizer(), max_seq_length=512,
        )))

        def search(_business, _vector, _limit, _threshold, active_ids):
            return [(vector_id, 0.95) for vector_id in active_ids]

        results = search_document_chunks(self.business, [0.1, 0.2, 0.3], revision=self.revision, search_vectors=search)
        self.assertTrue(results)
        retrieved_text = "\n".join(chunk.text for chunk, _score in results)
        self.assertIn("น้ำหนักตัวเครื่อง: 620 กรัม", retrieved_text)
        self.assertIn("รวมน้ำหนักสายไฟและข้อต่อ", retrieved_text)
        self.assertIn("| อัตราการไหล | 1,200 ลิตร/ชั่วโมง |", retrieved_text)
        self.assertIn("| ขนาด | 8 × 11 × 9 เซนติเมตร |", retrieved_text)
        self.assertTrue(any(chunk.heading == "ข้อมูลจำเพาะ" for chunk, _score in results))

    def test_failed_rebuild_keeps_current_rows_and_retries_from_same_backup(self):
        upsert_calls = 0

        def fail_on_second_vector(*_args):
            nonlocal upsert_calls
            upsert_calls += 1
            if upsert_calls == 2:
                raise RuntimeError("Qdrant write failed")

        patches = self._patches(fail_on_second_vector)
        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertRaisesRegex(RuntimeError, "Qdrant write failed"):
                rebuild_index_if_needed()

        self.assertEqual(list(DocumentChunk.objects.values_list("text", flat=True)), ["Old indexed chunk"])
        self.assertFalse((self.data_dir / SIGNATURE_FILENAME).exists())
        pending = json.loads((self.data_dir / PENDING_FILENAME).read_text())
        original_backup = Path(pending["backup_dir"])

        patches = self._patches(lambda *_args: None)
        with patches[0], patches[1], patches[2], patches[3]:
            rebuilt, backup = rebuild_index_if_needed()

        self.assertTrue(rebuilt)
        self.assertEqual(backup, original_backup)
        self.assertEqual(DocumentChunk.objects.filter(revision=self.revision).count(), 2)

    def test_restore_replaces_sqlite_qdrant_and_signature_files(self):
        database = self.data_dir / "current.sqlite3"
        database.write_text("current database", encoding="utf-8")
        current_qdrant = self.data_dir / "current-qdrant"
        current_qdrant.mkdir()
        (current_qdrant / "state.txt").write_text("current vectors", encoding="utf-8")
        backup = self.data_dir / "backup"
        (backup / "qdrant").mkdir(parents=True)
        (backup / "db.sqlite3").write_text("previous database", encoding="utf-8")
        (backup / "qdrant" / "state.txt").write_text("previous vectors", encoding="utf-8")
        (backup / "manifest.json").write_text(json.dumps({"qdrant": "qdrant"}), encoding="utf-8")
        (backup / SIGNATURE_FILENAME).write_text('{"model":"previous"}', encoding="utf-8")
        (self.data_dir / SIGNATURE_FILENAME).write_text('{"model":"current"}', encoding="utf-8")

        with override_settings(DATA_DIR=self.data_dir, QDRANT_PATH=str(current_qdrant)):
            with patch(
                "businesses.index_rebuild.connection",
                type("ConnectionStub", (), {"settings_dict": {"NAME": str(database)}, "close": lambda _self: None})(),
            ), patch("businesses.index_rebuild.reset_clients"):
                restore_index_backup(backup)

        self.assertEqual(database.read_text(encoding="utf-8"), "previous database")
        self.assertEqual((current_qdrant / "state.txt").read_text(encoding="utf-8"), "previous vectors")
        self.assertEqual(json.loads((self.data_dir / SIGNATURE_FILENAME).read_text()), {"model": "previous"})
