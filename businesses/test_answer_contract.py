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
        prompt = " ".join(body["messages"][0]["content"].split())
        self.assertIn("Use the customer's language for every response", prompt)
        self.assertIn("answer the supported facts", prompt)
        self.assertIn("Apply a test-only or sample disclaimer in any chunk", prompt)
        self.assertIn("answer that the sample states 12 months", prompt)
        self.assertIn("does not erase them", prompt)
        self.assertIn("Never claim the entire warranty is void, ends, expires, or is cancelled", prompt)
        self.assertIn("do not refuse because the real product is unknown", prompt)
        self.assertIn("Mention warranty terms only when the customer explicitly asks about warranty or coverage", prompt)
        self.assertIn("saltwater is about product compatibility, not warranty", prompt)
        self.assertIn("omit warranty exclusions, even if a source contains them", prompt)
        self.assertIn("answer what the sample says even if the real-world product", prompt)
        self.assertIn("never include internal IDs", prompt)
        self.assertIn("If no sources are supplied", prompt)
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

    @override_settings(OPENROUTER_API_KEY="test-key")
    def test_internal_source_ids_are_removed_from_customer_facing_answer(self):
        sources: list[dict[str, str | bool]] = [*self.sources, {
            "id": "src-2", "type": "qa", "question": "Holiday hours?", "answer": "Closed", "authoritative": False,
        }]
        content = json.dumps({
            "status": "answer",
            "answer": "Nine to five [src-1], holiday hours are closed (src-2).",
            "source_ids": ["src-1", "src-2"],
        })
        with patch("urllib.request.urlopen", return_value=_Response(content)):
            result = complete_answer("Hours?", sources)
        self.assertEqual(result.answer, "Nine to five, holiday hours are closed.")


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

    def test_insufficient_uses_the_model_localized_refusal(self):
        refusal = "ขออภัย ยังยืนยันอัตราการไหลจากข้อมูลที่พบไม่ได้"
        result = answer_question(
            self.business,
            "How fast is it?",
            embed_query=lambda text: [1.0],
            search_vectors=lambda *args: [(self.item.vector_id, 0.8)],
            complete=lambda question, sources: CompletionResult("insufficient_knowledge", refusal, ()),
        )
        self.assertEqual(result.kind, "insufficient_knowledge")
        self.assertEqual(result.text, refusal)
        self.assertEqual(result.sources, ())

    def test_no_retrieved_knowledge_generates_a_language_matched_refusal_without_sources(self):
        business = Business.objects.create(name="Empty business")
        calls = []

        def complete(question, sources):
            calls.append((question, sources))
            if "สี" in question:
                refusal = "ขออภัย ยังไม่มีข้อมูลเผยแพร่ที่ตอบคำถามนี้ได้"
            else:
                refusal = "I couldn't find published information for that question."
            return CompletionResult("insufficient_knowledge", refusal, ())

        thai = answer_question(
            business,
            "มีสีอะไรบ้าง?",
            complete=complete,
        )
        english = answer_question(
            business,
            "What is the sound level?",
            complete=complete,
        )

        self.assertEqual(calls, [("มีสีอะไรบ้าง?", []), ("What is the sound level?", [])])
        self.assertEqual(thai.kind, "insufficient_knowledge")
        self.assertEqual(thai.text, "ขออภัย ยังไม่มีข้อมูลเผยแพร่ที่ตอบคำถามนี้ได้")
        self.assertEqual(english.kind, "insufficient_knowledge")
        self.assertEqual(english.text, "I couldn't find published information for that question.")

    def test_no_retrieved_knowledge_does_not_return_an_unsupported_model_answer(self):
        business = Business.objects.create(name="Empty business")

        result = answer_question(
            business,
            "มีสีอะไรบ้าง?",
            complete=lambda question, sources: CompletionResult("answer", "มีสามสี", ()),
        )

        self.assertEqual(result.kind, "insufficient_knowledge")
        self.assertNotIn("สามสี", result.text)

    def test_openrouter_failure_uses_localized_fallback(self):
        business = Business.objects.create(name="Empty business")

        def unavailable(question, sources):
            raise OpenRouterError("offline")

        thai = answer_question(business, "เปิดกี่โมง?", complete=unavailable)
        english = answer_question(business, "When does it open?", complete=unavailable)

        self.assertEqual(thai.kind, "insufficient_knowledge")
        self.assertIn("เปิดกี่โมง?", thai.text)
        self.assertIn("ไม่พบข้อมูลที่เผยแพร่", thai.text)
        self.assertEqual(
            english.text,
            "I couldn't find published information to answer “When does it open?” yet.",
        )

    def test_localized_fallback_limits_reflected_question_length(self):
        business = Business.objects.create(name="Empty business")

        def unavailable(question, sources):
            raise OpenRouterError("offline")

        result = answer_question(business, "x" * 300, complete=unavailable)

        self.assertEqual(len(result.text), len("I couldn't find published information to answer “” yet.") + 200)

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
