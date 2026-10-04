import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from .models import Business, BusinessIntegration, KnowledgeItem
from .openrouter import CompletionResult, OpenRouterError, complete_answer
from .rag import answer_question, publish_item


class _Response:
    def __init__(self, content, reasoning=None):
        self.content = content
        self.reasoning = reasoning

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self.content, "reasoning_details": self.reasoning}}]}).encode()


class StructuredCompletionTests(TestCase):
    sources: list[dict[str, str | bool]] = [{"id": "src-1", "type": "qa", "question": "Hours?", "answer": "Nine to five", "authoritative": False}]

    @override_settings(OPENROUTER_API_KEY="test-key")
    def test_request_uses_strict_schema_and_excludes_reasoning(self):
        content = json.dumps({"status": "answer", "answer": "Nine to five", "source_ids": ["src-1"]})
        with patch("urllib.request.urlopen", return_value=_Response(content)) as send:
            result = complete_answer("Hours?", self.sources)

        self.assertEqual(result, CompletionResult("answer", "Nine to five", ("src-1",)))
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(body["response_format"]["json_schema"]["schema"]["required"], ["status", "answer", "source_ids"])
        self.assertEqual(body["provider"], {"require_parameters": True})
        self.assertEqual(body["reasoning"], {"effort": "none", "exclude": True})
        self.assertEqual(json.loads(body["messages"][1]["content"])["sources"], self.sources)

    @override_settings(OPENROUTER_API_KEY="test-key")
    def test_invalid_or_untrusted_completions_fail_closed(self):
        bad = [
            "not json",
            json.dumps({"status": "answer", "answer": "Nine", "source_ids": ["made-up"]}),
            json.dumps({"status": "answer", "answer": "Nine", "source_ids": []}),
            json.dumps({"status": "answer", "answer": "", "source_ids": ["src-1"]}),
            json.dumps({"status": "other", "answer": "Nine", "source_ids": ["src-1"]}),
            json.dumps({"status": "answer", "answer": "Nine", "source_ids": ["src-1"], "extra": 1}),
            json.dumps({"status": "answer", "answer": "Nine", "source_ids": ["src-1", "src-1"]}),
            None,
        ]
        for content in bad:
            with self.subTest(content=content), patch("urllib.request.urlopen", return_value=_Response(content)):
                with self.assertRaises(OpenRouterError):
                    complete_answer("Hours?", self.sources)

    @override_settings(OPENROUTER_API_KEY="test-key")
    def test_reasoning_details_are_never_returned_as_an_answer(self):
        content = json.dumps({"status": "answer", "answer": "Nine to five", "source_ids": ["src-1"]})
        with patch("urllib.request.urlopen", return_value=_Response(content, "Hidden reasoning")):
            result = complete_answer("Hours?", self.sources)
        self.assertEqual(result.answer, "Nine to five")
        self.assertNotIn("Hidden reasoning", repr(result))


class SafeQaAuthorityTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Coffee")
        self.item = KnowledgeItem.objects.create(business=self.business, question="Router X500 speed?", answer="2.5 Gbps")
        publish_item(self.item, embed_document=lambda text: [1.0], upsert_vector=lambda *args: None)

    def test_exact_match_uses_authoritative_qa_before_embedding(self):
        def complete(question, sources):
            self.assertEqual(len(sources), 1)
            self.assertTrue(sources[0]["authoritative"])
            self.assertEqual(sources[0]["answer"], "2.5 Gbps")
            return CompletionResult("answer", "2.5 Gbps", (sources[0]["id"],))

        result = answer_question(
            self.business,
            "  ROUTER   X500\tspeed?  ",
            embed_query=lambda text: self.fail("Exact match should skip embedding"),
            search_vectors=lambda *args: self.fail("Exact match should skip search"),
            complete=complete,
        )
        self.assertEqual(result.sources, ({"type": "qa", "label": "Verified answer"},))

    def test_semantic_match_is_evidence_without_authority(self):
        def complete(question, sources):
            self.assertFalse(sources[0]["authoritative"])
            return CompletionResult("needs_clarification", "Which router model?", ())

        result = answer_question(
            self.business,
            "What is this router's speed?",
            embed_query=lambda text: [1.0],
            search_vectors=lambda *args: [(self.item.vector_id, 0.99)],
            complete=complete,
        )
        self.assertEqual(result.kind, "needs_clarification")
        self.assertEqual(result.sources, ())

    def test_conflicting_product_sources_prompt_for_the_missing_model(self):
        other = KnowledgeItem.objects.create(business=self.business, question="Router X600 speed?", answer="5 Gbps")
        publish_item(other, embed_document=lambda text: [1.0], upsert_vector=lambda *args: None)

        def complete(question, sources):
            self.assertEqual(question, "What is the router speed?")
            self.assertEqual([source["answer"] for source in sources], ["2.5 Gbps", "5 Gbps"])
            self.assertEqual([source["authoritative"] for source in sources], [False, False])
            return CompletionResult("needs_clarification", "Which router model, X500 or X600?", ())

        result = answer_question(
            self.business,
            "What is the router speed?",
            embed_query=lambda text: [1.0],
            search_vectors=lambda *args: [(self.item.vector_id, 0.93), (other.vector_id, 0.91)],
            complete=complete,
        )
        self.assertEqual(result.kind, "needs_clarification")
        self.assertIn("X500 or X600", result.text)
        self.assertEqual(result.sources, ())

    def test_publish_rejects_normalized_duplicate_without_changing_live_answer(self):
        draft = KnowledgeItem.objects.create(business=self.business, question="ROUTER  X500 SPEED?", answer="9 Gbps")
        with self.assertRaisesRegex(ValueError, "same normalized question"):
            publish_item(draft, embed_document=lambda text: self.fail("Should not embed duplicate"))
        draft.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(draft.index_status, KnowledgeItem.IndexStatus.FAILED)
        self.assertEqual(self.item.answer, "2.5 Gbps")

    def test_replacement_conflict_keeps_original_published(self):
        other = KnowledgeItem.objects.create(business=self.business, question="Router X600 speed?", answer="5 Gbps")
        publish_item(other, embed_document=lambda text: [1.0], upsert_vector=lambda *args: None)
        replacement = KnowledgeItem.objects.create(
            business=self.business, question="ROUTER X600 SPEED?", answer="7 Gbps", replacement_for=self.item
        )
        with self.assertRaisesRegex(ValueError, "same normalized question"):
            publish_item(replacement, embed_document=lambda text: self.fail("Should not embed duplicate"))
        self.item.refresh_from_db()
        self.assertEqual(self.item.answer, "2.5 Gbps")

    def test_insufficient_uses_local_message_and_discards_model_text(self):
        result = answer_question(
            self.business,
            "How fast is it?",
            embed_query=lambda text: [1.0],
            search_vectors=lambda *args: [(self.item.vector_id, 0.8)],
            complete=lambda question, sources: CompletionResult("insufficient_knowledge", "Guess: 10 Gbps", ()),
        )
        self.assertEqual(result.kind, "insufficient_knowledge")
        self.assertNotIn("10 Gbps", result.text)
        self.assertEqual(result.sources, ())

    def test_only_cited_semantic_sources_are_public(self):
        second = KnowledgeItem.objects.create(business=self.business, question="Router X600 speed?", answer="5 Gbps")
        publish_item(second, embed_document=lambda text: [1.0], upsert_vector=lambda *args: None)
        result = answer_question(
            self.business,
            "How fast are the routers?",
            embed_query=lambda text: [1.0],
            search_vectors=lambda *args: [(self.item.vector_id, 0.93), (second.vector_id, 0.91)],
            complete=lambda question, sources: CompletionResult("answer", "X600 is 5 Gbps", ("src-2",)),
        )
        self.assertEqual(result.sources, ({"type": "qa", "label": "Verified answer"},))

    def test_web_widget_and_api_show_only_public_citations(self):
        integration = BusinessIntegration.objects.create(
            business=self.business, allowed_origins=["http://localhost:3000"]
        )
        _, secret = integration.create_api_key()
        with patch(
            "businesses.openrouter.complete_answer",
            return_value=CompletionResult("answer", "2.5 Gbps", ("src-1",)),
        ):
            web = self.client.post(self.business.get_absolute_url(), {"question": "Router X500 speed?"})
            widget = self.client.post(f"/embed/{integration.embed_token}/", {"question": "Router X500 speed?"})
            api = self.client.post(
                "/api/v1/chat",
                data=json.dumps({"question": "Router X500 speed?"}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {secret}"},
            )

        for response in (web, widget):
            self.assertContains(response, "Verified answer")
            self.assertNotContains(response, "src-1")
        self.assertEqual(api.json()["sources"], [{"type": "qa", "label": "Verified answer"}])
        self.assertNotIn("Router X500 speed?", json.dumps(api.json()))
        self.assertNotIn("src-1", json.dumps(api.json()))
