import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .document_chunks import PreviewChunk
from .document_knowledge import (
    active_document_chunks,
    publish_document,
    preview_document_chunks,
    recover_document_index_attempts,
)
from .models import Business, Document, DocumentChunk, DocumentIndexAttempt, DocumentRevision
from .openrouter import CompletionResult
from .rag import answer_question
from . import vector_store


class ResponsiveDocumentIndexingTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.business = Business.objects.create(name="Indexing shop")
        self.document = Document.objects.create(business=self.business)
        self.published = DocumentRevision.objects.create(
            document=self.document,
            revision_number=1,
            title="Published manual",
            content="Old published information",
            status=DocumentRevision.Status.PUBLISHED,
            index_status=DocumentRevision.IndexStatus.READY,
        )
        self.published_chunk = DocumentChunk.objects.create(
            revision=self.published,
            order=1,
            text="Old published information",
            index_status=DocumentChunk.IndexStatus.READY,
        )
        self.draft = DocumentRevision.objects.create(
            document=self.document,
            revision_number=2,
            title="Updated manual",
            content="New information",
        )
        self.preview = [PreviewChunk(1, "Updated", "New information", "New information", 2)]

    def test_chat_can_retrieve_previous_published_revision_during_indexing(self):
        previews = [
            *self.preview,
            PreviewChunk(2, "Updated", "More information", "More information", 2),
        ]
        second_batch_started = threading.Event()
        continue_indexing = threading.Event()
        candidate_vector_ids = []
        publish_errors = []
        batch_count = 0

        def embed_documents(texts):
            nonlocal batch_count
            batch_count += 1
            if batch_count == 2:
                second_batch_started.set()
                if not continue_indexing.wait(timeout=5):
                    raise TimeoutError("Test did not resume indexing")
            return [[1.0] for _text in texts]

        def publish_in_thread():
            try:
                publish_document(
                    self.draft,
                    embed_documents=embed_documents,
                    upsert_vector=lambda _business, vector_id, _vector: candidate_vector_ids.append(vector_id),
                    delete_vector=lambda *args: None,
                )
            except Exception as error:
                publish_errors.append(error)

        with patch("businesses.document_knowledge.preview_chunks", return_value=previews), override_settings(
            DOCUMENT_EMBED_BATCH_SIZE=1
        ):
            thread = threading.Thread(target=publish_in_thread)
            thread.start()
            self.assertTrue(second_batch_started.wait(timeout=5))
            try:
                candidate = DocumentChunk.objects.get(vector_id=candidate_vector_ids[0])
                self.assertEqual(candidate.index_status, DocumentChunk.IndexStatus.PENDING)

                def search(_business, _vector, _limit, _threshold, active_vector_ids):
                    self.assertEqual(active_vector_ids, [self.published_chunk.vector_id])
                    return [(candidate.vector_id, 0.99), (self.published_chunk.vector_id, 0.85)]

                result = answer_question(
                    self.business,
                    "What information is available?",
                    embed_query=lambda _question: [1.0],
                    search_vectors=search,
                    complete=lambda _question, sources: CompletionResult(
                        "answer", "Old published information", (str(sources[0]["id"]),)
                    ),
                )
                self.assertEqual(result.text, "Old published information")
                self.assertEqual(len(result.sources), 1)
                self.assertEqual(result.sources[0]["title"], "Published manual")
            finally:
                continue_indexing.set()
                thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(publish_errors, [])

        self.published.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.ARCHIVED)
        self.assertEqual(self.draft.status, DocumentRevision.Status.PUBLISHED)

    def test_overlapping_publish_is_rejected_immediately(self):
        embedding_started = threading.Event()
        continue_embedding = threading.Event()
        failure = []

        def slow_embedding(texts):
            embedding_started.set()
            if not continue_embedding.wait(timeout=5):
                raise TimeoutError("Test did not release embedding")
            return [[1.0] for _text in texts]

        def publish_in_thread():
            try:
                publish_document(
                    self.draft,
                    embed_documents=slow_embedding,
                    upsert_vector=lambda *args: None,
                    delete_vector=lambda *args: None,
                )
            except Exception as error:  # captured for assertion in the main thread
                failure.append(error)

        with patch("businesses.document_knowledge.preview_chunks", return_value=self.preview):
            thread = threading.Thread(target=publish_in_thread)
            thread.start()
            self.assertTrue(embedding_started.wait(timeout=5))
            other_draft = DocumentRevision.objects.create(
                document=Document.objects.create(business=self.business),
                revision_number=1,
                title="Other manual",
                content="Other information",
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "Another Document is being indexed"):
                    publish_document(other_draft, embed_documents=lambda texts: [[1.0] for _ in texts])
            finally:
                continue_embedding.set()
                thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(failure, [])
        self.assertEqual(DocumentIndexAttempt.objects.filter(status=DocumentIndexAttempt.Status.SUCCEEDED).count(), 1)

    @override_settings(DOCUMENT_INDEX_BUDGET_SECONDS=0)
    def test_timeout_marks_attempt_failed_and_keeps_published_revision_retrievable(self):
        with patch("businesses.document_knowledge.preview_chunks", return_value=self.preview):
            with self.assertRaisesRegex(TimeoutError, "time budget"):
                publish_document(self.draft, embed_documents=lambda texts: [[1.0] for _ in texts])

        self.published.refresh_from_db()
        self.draft.refresh_from_db()
        attempt = DocumentIndexAttempt.objects.get(revision=self.draft)
        self.assertEqual(attempt.status, DocumentIndexAttempt.Status.FAILED)
        self.assertEqual(self.published.status, DocumentRevision.Status.PUBLISHED)
        self.assertEqual(self.draft.index_status, DocumentRevision.IndexStatus.FAILED)
        self.assertEqual(list(active_document_chunks(self.business)), [self.published_chunk])

    @override_settings(DOCUMENT_MAX_CHUNKS=1)
    def test_oversized_preview_is_rejected_and_attempt_is_recorded_as_failed(self):
        two_chunks = [*self.preview, PreviewChunk(2, "Extra", "More", "More", 1)]
        with patch("businesses.document_knowledge.preview_chunks", return_value=two_chunks):
            with self.assertRaisesRegex(ValueError, "exceeds the maximum of 1 chunks"):
                publish_document(self.draft, embed_documents=lambda texts: [[1.0] for _ in texts])

        attempt = DocumentIndexAttempt.objects.get(revision=self.draft)
        self.assertEqual(attempt.status, DocumentIndexAttempt.Status.FAILED)
        self.assertEqual(DocumentChunk.objects.filter(revision=self.draft).count(), 0)
        self.assertEqual(self.published.status, DocumentRevision.Status.PUBLISHED)

    def test_expired_attempt_is_interrupted_and_retry_gets_a_new_attempt(self):
        interrupted = DocumentIndexAttempt.objects.create(
            revision=self.draft,
            owner_id="old-process",
            chunks_total=1,
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertEqual(recover_document_index_attempts(), 1)
        interrupted.refresh_from_db()
        self.assertEqual(interrupted.status, DocumentIndexAttempt.Status.INTERRUPTED)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.index_status, DocumentRevision.IndexStatus.INTERRUPTED)

        with patch("businesses.document_knowledge.preview_chunks", return_value=self.preview):
            publish_document(
                self.draft,
                embed_documents=lambda texts: [[1.0] for _ in texts],
                upsert_vector=lambda *args: None,
                delete_vector=lambda *args: None,
            )

        attempts = list(DocumentIndexAttempt.objects.filter(revision=self.draft).order_by("started_at"))
        self.assertEqual(len(attempts), 2)
        self.assertNotEqual(attempts[0].pk, attempts[1].pk)
        self.assertEqual(attempts[1].status, DocumentIndexAttempt.Status.SUCCEEDED)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.ARCHIVED)

    def test_startup_interrupts_a_running_attempt_even_before_its_lease_expires(self):
        attempt = DocumentIndexAttempt.objects.create(
            revision=self.draft,
            owner_id="previous-server-process",
            chunks_total=1,
            lease_expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.assertEqual(recover_document_index_attempts(at_startup=True), 1)
        attempt.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertEqual(attempt.status, DocumentIndexAttempt.Status.INTERRUPTED)
        self.assertEqual(self.draft.index_status, DocumentRevision.IndexStatus.INTERRUPTED)

    @override_settings(DOCUMENT_EMBED_BATCH_SIZE=2)
    def test_publish_embeds_in_batches_and_persists_progress_after_each_batch(self):
        previews = [
            PreviewChunk(i, "Details", f"Detail {i}", f"Detail {i}", 2)
            for i in range(1, 6)
        ]
        batch_sizes = []

        def embed_documents(texts):
            batch_sizes.append(len(texts))
            attempt = DocumentIndexAttempt.objects.filter(revision=self.draft).first()
            assert attempt is not None
            expected_completed = sum(batch_sizes[:-1])
            self.assertEqual(attempt.chunks_completed, expected_completed)
            return [[float(index)] for index, _text in enumerate(texts)]

        with patch("businesses.document_knowledge.preview_chunks", return_value=previews):
            publish_document(
                self.draft,
                embed_documents=embed_documents,
                upsert_vector=lambda *args: None,
                delete_vector=lambda *args: None,
            )

        self.assertEqual(batch_sizes, [2, 2, 1])
        attempt = DocumentIndexAttempt.objects.get(revision=self.draft)
        self.assertEqual(attempt.chunks_completed, 5)
        self.assertEqual(attempt.chunks_total, 5)


class VectorStoreThreadSafetyTests(TransactionTestCase):
    def test_embedding_model_is_serialized_and_accepts_batches(self):
        @dataclass
        class State:
            active: int = 0
            maximum: int = 0
            batches: list[list[str]] = field(default_factory=list)

        state = State()
        state_lock = threading.Lock()

        class FakeModel:
            tokenizer = object()
            max_seq_length = 128

            def encode(self, texts, normalize_embeddings=True):
                with state_lock:
                    state.active += 1
                    state.maximum = max(state.maximum, state.active)
                    state.batches.append(list(texts) if isinstance(texts, list) else [texts])
                time.sleep(0.01)
                with state_lock:
                    state.active -= 1
                return [[1.0, 0.0] for _text in texts] if isinstance(texts, list) else [1.0, 0.0]

        with override_settings(EMBEDDING_MODEL="test-model"), patch.dict(
            vector_store._embedding_models, {"test-model": FakeModel()}
        ):
            with ThreadPoolExecutor(max_workers=6) as workers:
                results = list(workers.map(lambda i: vector_store.embed_documents([f"doc {i}"]), range(6)))

        self.assertEqual(state.maximum, 1)
        self.assertEqual(len(state.batches), 6)
        self.assertEqual(results, [[[1.0, 0.0]]] * 6)

    def test_preview_tokenization_does_not_overlap_model_encoding(self):
        encoding_started = threading.Event()
        finish_encoding = threading.Event()
        tokenization_started = threading.Event()

        class FakeTokenizer:
            def __call__(self, text, *, add_special_tokens=False, return_offsets_mapping=False, verbose=True):
                tokenization_started.set()
                offsets = [(index, index + 1) for index, char in enumerate(text) if not char.isspace()]
                return {"input_ids": list(range(len(offsets))), "offset_mapping": offsets}

            def encode(self, text, *, add_special_tokens=False):
                tokens = self(text)["input_ids"]
                return [0, *tokens, 1] if add_special_tokens else tokens

            def num_special_tokens_to_add(self, *, pair=False):
                return 2

        class FakeModel:
            tokenizer = FakeTokenizer()
            max_seq_length = 128

            def encode(self, texts, normalize_embeddings=True):
                encoding_started.set()
                if not finish_encoding.wait(timeout=5):
                    raise TimeoutError("Test did not release model encoding")
                return [[1.0] for _text in texts]

        from .models import DocumentRevision

        revision = DocumentRevision(title="Manual", content="Product speed is 5 Gbps.")
        with override_settings(EMBEDDING_MODEL="test-preview-lock"), patch.dict(
            vector_store._embedding_models, {"test-preview-lock": FakeModel()}
        ):
            embedding_thread = threading.Thread(target=vector_store.embed_documents, args=(["query"],))
            embedding_thread.start()
            self.assertTrue(encoding_started.wait(timeout=5))
            preview_result = []
            preview_thread = threading.Thread(target=lambda: preview_result.extend(preview_document_chunks(revision)))
            preview_thread.start()
            try:
                self.assertFalse(tokenization_started.wait(timeout=0.05))
            finally:
                finish_encoding.set()
                embedding_thread.join(timeout=5)
                preview_thread.join(timeout=5)

        self.assertFalse(embedding_thread.is_alive())
        self.assertFalse(preview_thread.is_alive())
        self.assertTrue(tokenization_started.is_set())
        self.assertTrue(preview_result)

    def test_qdrant_calls_are_serialized_across_threads(self):
        @dataclass
        class State:
            active: int = 0
            maximum: int = 0

        state = State()
        state_lock = threading.Lock()

        class FakeClient:
            def _call(self):
                with state_lock:
                    state.active += 1
                    state.maximum = max(state.maximum, state.active)
                time.sleep(0.005)
                with state_lock:
                    state.active -= 1

            def collection_exists(self, _collection):
                self._call()
                return False

            def create_collection(self, *_args, **_kwargs):
                self._call()

            def upsert(self, *_args, **_kwargs):
                self._call()

        business = Business.objects.create(name="Qdrant thread test")
        fake_client = FakeClient()
        with patch("businesses.vector_store._client", return_value=fake_client):
            with ThreadPoolExecutor(max_workers=6) as workers:
                list(workers.map(lambda _i: vector_store.upsert_vector(business, uuid4(), [1.0]), range(12)))

        self.assertEqual(state.maximum, 1)
