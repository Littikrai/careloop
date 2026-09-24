from tempfile import TemporaryDirectory
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from .models import Business, KnowledgeItem
from .rag import answer_question, publish_item


class KnowledgeJourneyTests(TestCase):
    def test_admin_creates_drafts_and_publishes_selected_items(self):
        business = Business.objects.create(name="Coffee House")
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        for question, answer in [("Hours?", "Nine to five"), ("Location?", "Main Street")]:
            response = self.client.post(
                "/admin/businesses/knowledgeitem/add/",
                {"business": business.id, "question": question, "answer": answer, "_save": "Save"},
            )
            self.assertEqual(response.status_code, 302)

        items = list(KnowledgeItem.objects.all())
        self.assertEqual({item.status for item in items}, {KnowledgeItem.Status.DRAFT})
        with (
            patch("businesses.vector_store.embed_document", return_value=[1.0, 0.0]),
            patch("businesses.vector_store.upsert_vector"),
        ):
            response = self.client.post(
                "/admin/businesses/knowledgeitem/",
                {
                    "action": "publish_selected",
                    "_selected_action": [str(item.id) for item in items],
                    "index": "0",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(KnowledgeItem.objects.values_list("status", flat=True)),
            {KnowledgeItem.Status.PUBLISHED},
        )

    def test_failed_embedding_keeps_the_item_as_a_draft(self):
        business = Business.objects.create(name="Coffee House")
        item = KnowledgeItem.objects.create(business=business, question="Hours?", answer="Nine to five")

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            publish_item(
                item,
                embed_document=lambda text: (_ for _ in ()).throw(RuntimeError("model unavailable")),
                upsert_vector=lambda business, item_id, vector: None,
            )

        item.refresh_from_db()
        self.assertEqual(item.status, KnowledgeItem.Status.DRAFT)
        self.assertEqual(item.index_status, KnowledgeItem.IndexStatus.FAILED)
        self.assertIn("model unavailable", item.index_error)

    def test_publishing_an_existing_item_does_not_remove_it_from_chat(self):
        business = Business.objects.create(name="Coffee House")
        item = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")

        with patch("businesses.admin.publish_item") as publish:
            response = self.client.post(
                "/admin/businesses/knowledgeitem/",
                {"action": "publish_selected", "_selected_action": [str(item.id)], "index": "0"},
            )

        self.assertEqual(response.status_code, 302)
        publish.assert_not_called()
        item.refresh_from_db()
        self.assertEqual(item.status, KnowledgeItem.Status.PUBLISHED)
        self.assertEqual(item.index_status, KnowledgeItem.IndexStatus.READY)

    def test_published_qa_can_answer_only_its_business(self):
        coffee = Business.objects.create(name="Coffee House")
        books = Business.objects.create(name="Book Store")
        item = KnowledgeItem.objects.create(
            business=coffee,
            question="ร้านเปิดกี่โมง?",
            answer="เปิดทุกวัน เวลา 09:00–18:00 น.",
        )
        indexed: dict[str, list[float]] = {}

        publish_item(
            item,
            embed_document=lambda text: [1.0, 0.0],
            upsert_vector=lambda business, item_id, vector: indexed.update({str(item_id): vector}),
        )
        item.refresh_from_db()
        self.assertEqual(item.status, KnowledgeItem.Status.PUBLISHED)

        def search(business, vector, limit, threshold, active_vector_ids):
            if business == coffee and indexed:
                return [(item.id, 0.91)]
            return []

        def complete(question, knowledge):
            self.assertEqual(question, "เปิดวันไหน?")
            self.assertEqual(knowledge, [(item.question, item.answer)])
            return "ร้านเปิดทุกวัน เวลา 09:00–18:00 น."

        answer = answer_question(
            coffee,
            "เปิดวันไหน?",
            embed_query=lambda text: [1.0, 0.0],
            search_vectors=search,
            complete=complete,
        )
        self.assertEqual(answer.kind, "answer")
        self.assertIn("09:00", answer.text)

        missing = answer_question(
            books,
            "เปิดวันไหน?",
            embed_query=lambda text: [1.0, 0.0],
            search_vectors=search,
            complete=complete,
        )
        self.assertEqual(missing.kind, "insufficient_knowledge")

    def test_published_qa_retrieves_from_local_qdrant_before_completion(self):
        from . import vector_store

        coffee = Business.objects.create(name="Coffee House")
        books = Business.objects.create(name="Book Store")
        coffee_item = KnowledgeItem.objects.create(
            business=coffee,
            question="Coffee hours?",
            answer="Nine to five",
        )
        books_item = KnowledgeItem.objects.create(
            business=books,
            question="Book hours?",
            answer="Ten to six",
        )
        KnowledgeItem.objects.create(
            business=coffee,
            question="Coffee draft?",
            answer="Do not use",
        )

        with TemporaryDirectory() as path, override_settings(QDRANT_PATH=path):
            vector_store.reset_clients()
            publish_item(
                coffee_item,
                embed_document=lambda text: [1.0, 0.0],
                upsert_vector=vector_store.upsert_vector,
            )
            publish_item(
                books_item,
                embed_document=lambda text: [1.0, 0.0],
                upsert_vector=vector_store.upsert_vector,
            )
            answer = answer_question(
                coffee,
                "When do you open?",
                embed_query=lambda text: [1.0, 0.0],
                search_vectors=vector_store.search_vectors,
                complete=lambda question, knowledge: knowledge[0][1],
            )
            vector_store.reset_clients()

        self.assertEqual(answer.kind, "answer")
        self.assertEqual(answer.text, "Nine to five")

    def test_publishing_a_replacement_updates_the_existing_vector_and_answer(self):
        coffee = Business.objects.create(name="Coffee House")
        books = Business.objects.create(name="Book Store")
        original = KnowledgeItem.objects.create(
            business=coffee,
            question="Coffee hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        other_business_item = KnowledgeItem.objects.create(
            business=books,
            question="Book hours?",
            answer="Ten to six",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        replacement = KnowledgeItem.objects.create(
            business=coffee,
            question="Coffee hours?",
            answer="Eight to four",
            replacement_for=original,
        )
        replacement_id = replacement.id
        indexed: dict[str, list[float]] = {}

        publish_item(
            replacement,
            embed_document=lambda text: [1.0, 0.0],
            upsert_vector=lambda business, item_id, vector: indexed.update({str(item_id): vector}),
        )

        self.assertEqual(indexed, {str(replacement_id): [1.0, 0.0]})
        original.refresh_from_db()
        other_business_item.refresh_from_db()
        self.assertEqual(original.answer, "Eight to four")
        self.assertEqual(original.vector_id, replacement_id)
        self.assertEqual(original.status, KnowledgeItem.Status.PUBLISHED)
        self.assertFalse(KnowledgeItem.objects.filter(pk=replacement.pk).exists())
        self.assertEqual(other_business_item.answer, "Ten to six")

    def test_failed_replacement_keeps_the_existing_answer_published(self):
        business = Business.objects.create(name="Coffee House")
        original = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        replacement = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Eight to four",
            replacement_for=original,
        )

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            publish_item(
                replacement,
                embed_document=lambda text: (_ for _ in ()).throw(RuntimeError("model unavailable")),
                upsert_vector=lambda business, item_id, vector: None,
            )

        original.refresh_from_db()
        replacement.refresh_from_db()
        self.assertEqual(original.answer, "Nine to five")
        self.assertEqual(original.status, KnowledgeItem.Status.PUBLISHED)
        self.assertEqual(replacement.status, KnowledgeItem.Status.DRAFT)
        self.assertEqual(replacement.index_status, KnowledgeItem.IndexStatus.FAILED)

    def test_failed_vector_write_keeps_the_existing_vector_and_answer(self):
        business = Business.objects.create(name="Coffee House")
        original = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        replacement = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Eight to four",
            replacement_for=original,
        )
        written_ids: list[str] = []

        def write_then_fail(business, item_id, vector):
            written_ids.append(str(item_id))
            raise RuntimeError("connection dropped after write")

        with self.assertRaisesRegex(RuntimeError, "connection dropped"):
            publish_item(
                replacement,
                embed_document=lambda text: [1.0, 0.0],
                upsert_vector=write_then_fail,
            )

        original.refresh_from_db()
        replacement.refresh_from_db()
        self.assertEqual(written_ids, [str(replacement.id)])
        self.assertEqual(original.answer, "Nine to five")
        self.assertEqual(original.vector_id, original.id)
        self.assertEqual(replacement.index_status, KnowledgeItem.IndexStatus.FAILED)

    @override_settings(RAG_TOP_K=1, RAG_SCORE_THRESHOLD=0.5)
    def test_failed_replacement_vector_cannot_displace_the_published_vector(self):
        from . import vector_store

        business = Business.objects.create(name="Coffee House")
        original = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
        )
        replacement = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Eight to four",
            replacement_for=original,
        )

        with TemporaryDirectory() as path, override_settings(QDRANT_PATH=path):
            vector_store.reset_clients()
            publish_item(
                original,
                embed_document=lambda text: [0.9, 0.435],
                upsert_vector=vector_store.upsert_vector,
            )

            def write_then_fail(business, item_id, vector):
                vector_store.upsert_vector(business, item_id, vector)
                raise RuntimeError("connection dropped after write")

            with self.assertRaisesRegex(RuntimeError, "connection dropped"):
                publish_item(
                    replacement,
                    embed_document=lambda text: [1.0, 0.0],
                    upsert_vector=write_then_fail,
                )
            answer = answer_question(
                business,
                "Hours?",
                embed_query=lambda text: [1.0, 0.0],
                search_vectors=vector_store.search_vectors,
                complete=lambda question, knowledge: knowledge[0][1],
            )
            vector_store.reset_clients()

        self.assertEqual(answer.text, "Nine to five")


class ChatJourneyTests(TestCase):
    def test_customer_asks_and_receives_an_answer_from_that_business(self):
        coffee = Business.objects.create(name="Coffee House")
        books = Business.objects.create(name="Book Store")
        coffee_item = KnowledgeItem.objects.create(
            business=coffee,
            question="ร้านเปิดกี่โมง?",
            answer="เปิดเวลา 09:00 น.",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        KnowledgeItem.objects.create(
            business=books,
            question="ร้านเปิดกี่โมง?",
            answer="เปิดเวลา 10:00 น.",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )

        with (
            patch("businesses.vector_store.embed_query", return_value=[1.0, 0.0]),
            patch("businesses.vector_store.search_vectors", return_value=[(coffee_item.id, 0.91)]),
            patch("businesses.openrouter.complete_answer", return_value="เราเปิดเวลา 09:00 น."),
        ):
            response = self.client.post(coffee.get_absolute_url(), {"question": "เปิดกี่โมง?"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "เราเปิดเวลา 09:00 น.")
        self.assertNotContains(response, "10:00")

    @override_settings(CHAT_RATE_LIMIT_PER_MINUTE=1)
    def test_public_chat_rate_limit_is_per_business_and_client(self):
        from django.core.cache import cache

        cache.clear()
        coffee = Business.objects.create(name="Coffee House")
        first = self.client.post(coffee.get_absolute_url(), {"question": "First question"})
        second = self.client.post(coffee.get_absolute_url(), {"question": "Second question"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertContains(second, "Too many questions", status_code=429)

    def test_drafts_are_not_used_and_chat_post_requires_csrf(self):
        from django.test import Client

        business = Business.objects.create(name="Coffee House")
        KnowledgeItem.objects.create(business=business, question="Secret draft", answer="Do not use")
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(
            browser.post(business.get_absolute_url(), {"question": "Tell me the secret"}).status_code,
            403,
        )
        with patch("businesses.vector_store.embed_query") as embed_query:
            response = self.client.post(business.get_absolute_url(), {"question": "Tell me the secret"})
        self.assertContains(response, "enough published information")
        embed_query.assert_not_called()

    def test_chat_reports_a_llm_failure_after_retrieval(self):
        from .openrouter import OpenRouterError

        business = Business.objects.create(name="Coffee House")
        item = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        with (
            patch("businesses.vector_store.embed_query", return_value=[1.0, 0.0]),
            patch("businesses.vector_store.search_vectors", return_value=[(item.id, 0.91)]),
            patch("businesses.openrouter.complete_answer", side_effect=OpenRouterError("timeout")),
        ):
            response = self.client.post(business.get_absolute_url(), {"question": "Hours?"})
        self.assertContains(response, "answer service is temporarily unavailable")

    def test_admin_creates_a_replacement_draft_without_changing_the_published_item(self):
        business = Business.objects.create(name="Coffee House")
        original = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")

        response = self.client.post(
            "/admin/businesses/knowledgeitem/",
            {"action": "create_replacement_drafts", "_selected_action": [str(original.id)], "index": "0"},
        )

        self.assertEqual(response.status_code, 302)
        original.refresh_from_db()
        replacement = KnowledgeItem.objects.get(replacement_for=original)
        self.assertEqual(original.answer, "Nine to five")
        self.assertEqual(replacement.answer, "Nine to five")
        self.assertEqual(replacement.status, KnowledgeItem.Status.DRAFT)

    def test_admin_delete_removes_knowledge_even_when_vector_deletion_fails(self):
        business = Business.objects.create(name="Coffee House")
        item = KnowledgeItem.objects.create(
            business=business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")

        with patch("businesses.admin.delete_vector", side_effect=RuntimeError("Qdrant offline")) as delete_vector:
            response = self.client.post(f"/admin/businesses/knowledgeitem/{item.id}/delete/", {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        delete_vector.assert_called_once_with(business, item.id)
        self.assertFalse(KnowledgeItem.objects.filter(pk=item.id).exists())


class QdrantVectorStoreTests(TestCase):
    def test_vectors_are_persisted_in_separate_business_collections(self):
        from . import vector_store

        coffee = Business.objects.create(name="Coffee House")
        books = Business.objects.create(name="Book Store")
        coffee_item = KnowledgeItem.objects.create(business=coffee, question="Hours?", answer="Nine to five")
        books_item = KnowledgeItem.objects.create(business=books, question="Hours?", answer="Ten to six")

        with TemporaryDirectory() as path, override_settings(QDRANT_PATH=path):
            vector_store.reset_clients()
            vector_store.upsert_vector(coffee, coffee_item.id, [1.0, 0.0])
            vector_store.upsert_vector(books, books_item.id, [0.0, 1.0])
            self.assertEqual(
                vector_store.search_vectors(coffee, [1.0, 0.0], 3, 0.5),
                [(coffee_item.id, 1.0)],
            )
            self.assertEqual(
                vector_store.search_vectors(books, [1.0, 0.0], 3, 0.5),
                [],
            )
            vector_store.delete_vector(coffee, coffee_item.id)
            self.assertEqual(vector_store.search_vectors(coffee, [1.0, 0.0], 3, 0.5), [])
            self.assertEqual(
                vector_store.search_vectors(books, [0.0, 1.0], 3, 0.5),
                [(books_item.id, 1.0)],
            )
            vector_store.reset_clients()


class OpenRouterTests(TestCase):
    @override_settings(OPENROUTER_API_KEY="")
    def test_missing_api_key_is_reported_without_a_network_request(self):
        from .openrouter import OpenRouterError, complete_answer

        with patch("urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(OpenRouterError, "OPENROUTER_API_KEY"):
                complete_answer("When do you open?", [("Opening time?", "Nine o'clock")])
        urlopen.assert_not_called()

    @override_settings(OPENROUTER_API_KEY="test-key", OPENROUTER_MODEL="openrouter/free")
    def test_completion_sends_only_the_question_and_retrieved_knowledge(self):
        from .openrouter import complete_answer

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "We open at nine."}}]}).encode()

        with patch("urllib.request.urlopen", return_value=Response()) as urlopen:
            answer = complete_answer("When do you open?", [("Opening time?", "Nine o'clock")])

        self.assertEqual(answer, "We open at nine.")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "openrouter/free")
        self.assertIn("When do you open?", payload["messages"][1]["content"])
        self.assertIn("Nine o'clock", payload["messages"][1]["content"])
        self.assertEqual(request.headers["Authorization"], "Bearer test-key")

    @override_settings(OPENROUTER_API_KEY="test-key")
    def test_transport_error_becomes_a_service_error(self):
        import urllib.error

        from .openrouter import OpenRouterError, complete_answer

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaisesRegex(OpenRouterError, "could not produce"):
                complete_answer("When do you open?", [("Opening time?", "Nine o'clock")])
