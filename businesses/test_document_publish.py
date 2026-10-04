import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .document_chunks import PreviewChunk
from .document_knowledge import publish_document, test_document_retrieval
from .models import Business, BusinessIntegration, Document, DocumentChunk, DocumentRevision, KnowledgeItem
from .openrouter import CompletionResult
from .rag import answer_question
from . import vector_store


class DocumentPublishTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Router shop")
        self.document = Document.objects.create(business=self.business)
        self.revision = DocumentRevision.objects.create(
            document=self.document, title="X500 specifications", product="X500", version="2026",
            content="# Speed\nWAN throughput 2.5 Gbps\n\n# Ports\nOne WAN port",
        )
        self.preview = [
            PreviewChunk(1, "Speed", "WAN throughput 2.5 Gbps", "product: X500\nWAN throughput 2.5 Gbps", 24),
            PreviewChunk(2, "Ports", "One WAN port", "product: X500\nOne WAN port", 17),
        ]

    def test_publish_indexes_all_chunks_before_making_revision_live(self):
        embedded = []

        def embed(text):
            self.assertEqual(self.revision.status, DocumentRevision.Status.DRAFT)
            embedded.append(text)
            return [1.0, 0.0]

        def upsert(business, vector_id, vector):
            self.assertEqual(business, self.business)
            self.assertEqual(vector, [1.0, 0.0])
            self.assertNotEqual(vector_id, self.revision.pk)
            self.assertEqual(DocumentRevision.objects.get(pk=self.revision.pk).status, DocumentRevision.Status.DRAFT)

        with patch("businesses.document_knowledge.preview_chunks", return_value=self.preview):
            count = publish_document(self.revision, embed_document=embed, upsert_vector=upsert)

        self.revision.refresh_from_db()
        self.assertEqual(count, 2)
        self.assertEqual(embedded, [chunk.embedding_text for chunk in self.preview])
        self.assertEqual(self.revision.status, DocumentRevision.Status.PUBLISHED)
        self.assertEqual(self.revision.index_status, DocumentRevision.IndexStatus.READY)
        chunks = list(DocumentChunk.objects.filter(revision=self.revision).order_by("order"))
        self.assertEqual([chunk.heading for chunk in chunks], ["Speed", "Ports"])
        self.assertEqual([chunk.text for chunk in chunks], [chunk.text for chunk in self.preview])
        self.assertEqual([chunk.index_status for chunk in chunks], [DocumentChunk.IndexStatus.READY] * 2)
        self.assertEqual(len({chunk.vector_id for chunk in chunks}), 2)

    def test_publish_failure_keeps_draft_and_no_chunk_is_retrievable(self):
        calls = 0

        def upsert(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Qdrant unavailable")

        with patch("businesses.document_knowledge.preview_chunks", return_value=self.preview):
            with self.assertRaisesRegex(RuntimeError, "Qdrant unavailable"):
                publish_document(
                    self.revision, embed_document=lambda text: [1.0], upsert_vector=upsert
                )
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, DocumentRevision.Status.DRAFT)
        self.assertEqual(self.revision.index_status, DocumentRevision.IndexStatus.FAILED)
        self.assertIn("Qdrant unavailable", self.revision.index_error)
        self.assertFalse(DocumentChunk.objects.filter(revision=self.revision, index_status=DocumentChunk.IndexStatus.READY).exists())

        with patch("businesses.document_knowledge.preview_chunks", return_value=self.preview):
            retried = publish_document(
                self.revision, embed_document=lambda text: [1.0], upsert_vector=lambda *args: None
            )
        self.revision.refresh_from_db()
        self.assertEqual(retried, 2)
        self.assertEqual(self.revision.status, DocumentRevision.Status.PUBLISHED)
        self.assertEqual(DocumentChunk.objects.filter(revision=self.revision).count(), 2)

    def test_admin_publish_confirms_business_title_and_chunks(self):
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        url = f"/admin/businesses/documentrevision/{self.revision.pk}/publish/"
        with patch("businesses.admin.preview_chunks", return_value=self.preview):
            response = self.client.get(url)
        self.assertContains(response, "Router shop")
        self.assertContains(response, "X500 specifications")
        self.assertContains(response, "2 chunks")
        with patch("businesses.admin.publish_document", return_value=2) as publish:
            response = self.client.post(url, {"confirm": "yes"})
        self.assertEqual(response.status_code, 302)
        publish.assert_called_once()


class DocumentRetrievalTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Router shop")
        self.other = Business.objects.create(name="Other shop")
        document = Document.objects.create(business=self.business)
        self.revision = DocumentRevision.objects.create(
            document=document, title="X500 specifications", product="X500", version="2026",
            content="WAN throughput 2.5 Gbps", status=DocumentRevision.Status.PUBLISHED,
            index_status=DocumentRevision.IndexStatus.READY,
        )
        self.chunk = DocumentChunk.objects.create(
            revision=self.revision, order=1, heading="Performance", text="WAN throughput 2.5 Gbps",
            index_status=DocumentChunk.IndexStatus.READY,
        )

    def test_document_only_answer_cites_public_metadata_and_embeds_once(self):
        calls = []

        def search(business, vector, limit, threshold, active_vector_ids):
            calls.append((limit, active_vector_ids))
            return [(self.chunk.vector_id, 0.92)]

        def complete(question, sources):
            return CompletionResult("answer", "2.5 Gbps", (str(sources[0]["id"]),))

        result = answer_question(
            self.business, "How fast is the X500?", embed_query=lambda text: [1.0],
            search_vectors=search, complete=complete,
        )
        self.assertEqual(result.text, "2.5 Gbps")
        self.assertEqual(calls, [(6, [self.chunk.vector_id])])
        self.assertEqual(result.sources[0]["type"], "document")
        self.assertEqual(result.sources[0]["title"], "X500 specifications")
        self.assertEqual(result.sources[0]["heading"], "Performance")
        self.assertEqual(result.sources[0]["product"], "X500")
        self.assertEqual(result.sources[0]["version"], "2026")
        self.assertNotIn("text", result.sources[0])
        self.assertNotIn("source_name", result.sources[0])

    def test_exact_qa_stays_authoritative_with_document_context(self):
        qa = KnowledgeItem.objects.create(
            business=self.business, question="X500 speed?", answer="2.5 Gbps",
            status=KnowledgeItem.Status.PUBLISHED, index_status=KnowledgeItem.IndexStatus.READY,
        )
        embedded = []

        def complete(question, sources):
            self.assertEqual(sources[0]["type"], "qa")
            self.assertTrue(sources[0]["authoritative"])
            self.assertEqual(sources[1]["type"], "document")
            return CompletionResult("answer", "2.5 Gbps", (str(sources[0]["id"]),))

        def embed(text):
            embedded.append(text)
            return [1.0]

        result = answer_question(
            self.business, " X500   SPEED? ",
            embed_query=embed,
            search_vectors=lambda business, vector, limit, threshold, ids: [(self.chunk.vector_id, 0.8)],
            complete=complete,
        )
        self.assertEqual(len(embedded), 1)
        self.assertEqual(result.sources, ({"type": "qa", "label": "Verified answer"},))
        self.assertEqual(qa.status, KnowledgeItem.Status.PUBLISHED)

    def test_no_matching_chunk_skips_openrouter_and_other_business(self):
        result = answer_question(
            self.other, "X500 speed?",
            embed_query=lambda text: self.fail("Other business has no knowledge"),
            complete=lambda *args: self.fail("No OpenRouter call"),
        )
        self.assertEqual(result.kind, "insufficient_knowledge")
        result = answer_question(
            self.business, "X500 speed?", embed_query=lambda text: [1.0],
            search_vectors=lambda *args: [], complete=lambda *args: self.fail("No OpenRouter call"),
        )
        self.assertEqual(result.kind, "insufficient_knowledge")

    def test_web_widget_and_api_show_document_citation(self):
        integration = BusinessIntegration.objects.create(business=self.business, allowed_origins=["http://localhost:3000"])
        _, secret = integration.create_api_key()
        with (
            patch("businesses.vector_store.embed_query", return_value=[1.0]),
            patch("businesses.vector_store.search_vectors", return_value=[(self.chunk.vector_id, 0.92)]),
            patch("businesses.openrouter.complete_answer", side_effect=lambda q, sources: CompletionResult("answer", "2.5 Gbps", (sources[0]["id"],))),
        ):
            web = self.client.post(self.business.get_absolute_url(), {"question": "X500 speed?"})
            widget = self.client.post(f"/embed/{integration.embed_token}/", {"question": "X500 speed?"})
            api = self.client.post(
                "/api/v1/chat", data=json.dumps({"question": "X500 speed?"}), content_type="application/json",
                headers={"Authorization": f"Bearer {secret}"},
            )
        for response in (web, widget):
            self.assertContains(response, "X500 specifications")
            self.assertContains(response, "Performance")
            self.assertNotContains(response, "WAN throughput")
        self.assertEqual(api.json()["sources"][0]["title"], "X500 specifications")
        self.assertNotIn("WAN throughput", json.dumps(api.json()))

    def test_test_retrieval_page_shows_revision_chunk_and_score_without_llm(self):
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        url = f"/admin/businesses/documentrevision/{self.revision.pk}/test-retrieval/"
        with (
            patch("businesses.admin.test_document_retrieval", return_value=[(self.chunk, 0.923)]) as retrieve,
            patch("businesses.openrouter.complete_answer", side_effect=AssertionError("Test retrieval must not call LLM")),
        ):
            response = self.client.post(url, {"question": "X500 speed?"})
        self.assertContains(response, "X500 specifications")
        self.assertContains(response, "revision 1")
        self.assertContains(response, "WAN throughput 2.5 Gbps")
        self.assertContains(response, "0.923")
        retrieve.assert_called_once()

    def test_retrieval_limits_and_duplicate_document_text(self):
        duplicate_revision = DocumentRevision.objects.create(
            document=Document.objects.create(business=self.business), title="X500 duplicate",
            product="X500", version="2026", content="WAN throughput 2.5 Gbps",
            status=DocumentRevision.Status.PUBLISHED, index_status=DocumentRevision.IndexStatus.READY,
        )
        duplicate = DocumentChunk.objects.create(
            revision=duplicate_revision, order=1, heading="Repeated", text="WAN throughput 2.5 Gbps",
            index_status=DocumentChunk.IndexStatus.READY,
        )
        extra_chunks = [
            DocumentChunk.objects.create(
                revision=self.revision, order=index + 2, heading="Other", text=f"Different detail {index}",
                index_status=DocumentChunk.IndexStatus.READY,
            ) for index in range(6)
        ]
        for index in range(4):
            KnowledgeItem.objects.create(
                business=self.business, question=f"Question {index}", answer=f"Answer {index}",
                status=KnowledgeItem.Status.PUBLISHED, index_status=KnowledgeItem.IndexStatus.READY,
            )
        embedded = []
        calls = []

        def embed(text):
            embedded.append(text)
            return [1.0]

        def search(business, vector, limit, threshold, ids):
            calls.append((limit, len(ids)))
            if limit == 3:
                return [(item.vector_id, 0.7) for item in KnowledgeItem.objects.filter(business=self.business)[:3]]
            return [(chunk.vector_id, 0.9 - index * 0.01) for index, chunk in enumerate([self.chunk, duplicate, *extra_chunks])][:limit]

        def complete(question, sources):
            self.assertLessEqual(len(sources), 6)
            self.assertEqual(len([source for source in sources if source["type"] == "document" and source["text"] == self.chunk.text]), 1)
            self.assertLessEqual(len(json.dumps(sources, ensure_ascii=False)), 8000)
            return CompletionResult("answer", "2.5 Gbps", (str(sources[0]["id"]),))

        answer_question(self.business, "What does this router support?", embed_query=embed, search_vectors=search, complete=complete)
        self.assertEqual(len(embedded), 1)
        self.assertEqual(calls, [(3, 4), (6, 8)])

    def test_conflicting_document_versions_can_request_clarification(self):
        other_revision = DocumentRevision.objects.create(
            document=Document.objects.create(business=self.business), title="X500 old specs",
            content="WAN throughput 1 Gbps", version="2025",
            status=DocumentRevision.Status.PUBLISHED, index_status=DocumentRevision.IndexStatus.READY,
        )
        other_chunk = DocumentChunk.objects.create(
            revision=other_revision, order=1, text="WAN throughput 1 Gbps",
            index_status=DocumentChunk.IndexStatus.READY,
        )

        def complete(question, sources):
            self.assertEqual({source["version"] for source in sources}, {"2025", "2026"})
            return CompletionResult("needs_clarification", "Which version do you mean?", ())

        result = answer_question(
            self.business, "What speed does the X500 support?", embed_query=lambda text: [1.0],
            search_vectors=lambda business, vector, limit, threshold, ids: [
                (self.chunk.vector_id, 0.9), (other_chunk.vector_id, 0.8)
            ], complete=complete,
        )
        self.assertEqual(result.kind, "needs_clarification")
        self.assertEqual(result.sources, ())

    def test_overlapping_chunks_send_only_new_text_from_lower_ranked_chunk(self):
        self.chunk.text = "The router supports Wi-Fi 6 and 2.5 Gbps WAN."
        self.chunk.save(update_fields=["text"])
        second = DocumentChunk.objects.create(
            revision=self.revision, order=2,
            text="Wi-Fi 6 and 2.5 Gbps WAN. It has four LAN ports.",
            index_status=DocumentChunk.IndexStatus.READY,
        )

        def complete(question, sources):
            self.assertEqual(sources[0]["text"], self.chunk.text)
            self.assertEqual(sources[1]["text"], "It has four LAN ports.")
            return CompletionResult("answer", "Four LAN ports", (str(sources[1]["id"]),))

        result = answer_question(
            self.business, "How many LAN ports?", embed_query=lambda text: [1.0],
            search_vectors=lambda business, vector, limit, threshold, ids: [
                (self.chunk.vector_id, 0.9), (second.vector_id, 0.8)
            ], complete=complete,
        )
        self.assertEqual(result.text, "Four LAN ports")

    def test_oversized_context_is_not_sent_to_openrouter(self):
        qa = KnowledgeItem.objects.create(
            business=self.other, question="Long policy?", answer="x" * 9000,
            status=KnowledgeItem.Status.PUBLISHED, index_status=KnowledgeItem.IndexStatus.READY,
        )
        result = answer_question(
            self.other, "Long policy?", embed_query=lambda text: self.fail("Exact match does not embed"),
            complete=lambda *args: self.fail("Oversized source must not be sent"),
        )
        self.assertEqual(result.kind, "insufficient_knowledge")
        self.assertEqual(qa.status, KnowledgeItem.Status.PUBLISHED)

    def test_qdrant_document_search_uses_only_ready_vectors_from_selected_business(self):
        other_document = Document.objects.create(business=self.other)
        other_revision = DocumentRevision.objects.create(
            document=other_document, title="Other specs", content="Secret other business content",
            status=DocumentRevision.Status.PUBLISHED, index_status=DocumentRevision.IndexStatus.READY,
        )
        other_chunk = DocumentChunk.objects.create(
            revision=other_revision, order=1, text="Secret other business content",
            index_status=DocumentChunk.IndexStatus.READY,
        )
        failed_chunk = DocumentChunk.objects.create(
            revision=self.revision, order=2, text="Stale failed content",
            index_status=DocumentChunk.IndexStatus.FAILED,
        )
        with TemporaryDirectory() as path, override_settings(QDRANT_PATH=path):
            vector_store.reset_clients()
            for chunk in (self.chunk, other_chunk, failed_chunk):
                vector_store.upsert_vector(chunk.revision.document.business, chunk.vector_id, [1.0, 0.0])
            result = answer_question(
                self.business, "X500 speed?", embed_query=lambda text: [1.0, 0.0],
                search_vectors=vector_store.search_vectors,
                complete=lambda question, sources: CompletionResult("answer", "2.5 Gbps", (str(sources[0]["id"]),)),
            )
            with patch("businesses.document_knowledge.default_embed_query", return_value=[1.0, 0.0]):
                matches = test_document_retrieval(self.revision, "X500 speed?")
            vector_store.reset_clients()
        self.assertEqual(result.kind, "answer")
        self.assertEqual(result.sources[0]["title"], "X500 specifications")
        self.assertEqual(len(result.sources), 1)
        self.assertEqual([chunk.pk for chunk, _score in matches], [self.chunk.pk])
