import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth import get_user_model

from .importer import KnowledgeImportError, import_qa_json
from .models import Business, KnowledgeItem
from .rag import answer_question, publish_item
from .openrouter import CompletionResult


class KnowledgeImportTests(TestCase):
    def test_import_creates_drafts_and_skips_normalized_duplicates(self):
        business = Business.objects.create(name="Coffee House")
        KnowledgeItem.objects.create(business=business, question="Hours?", answer="Nine to five")

        result = import_qa_json(
            business,
            json.dumps(
                [
                    {"question": " Hours? ", "answer": "Nine to five"},
                    {"question": "Location?", "answer": "Main Street"},
                    {"question": "Location?", "answer": "Main Street"},
                ]
            ).encode(),
        )

        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped, 2)
        self.assertEqual(
            list(KnowledgeItem.objects.filter(business=business).values_list("question", "status")),
            [("Hours?", KnowledgeItem.Status.DRAFT), ("Location?", KnowledgeItem.Status.DRAFT)],
        )

    def test_invalid_item_rejects_the_entire_file_without_creating_anything(self):
        business = Business.objects.create(name="Coffee House")

        for content in [
            b'[{"question":"Hours?","answer":"Nine to five"},{"question":"Location?"}]',
            b'[{"question":"Hours?","answer":"Nine to five","extra":"no"}]',
        ]:
            with self.subTest(content=content):
                with self.assertRaisesRegex(KnowledgeImportError, "Item"):
                    import_qa_json(business, content)

        self.assertFalse(KnowledgeItem.objects.filter(business=business).exists())

    def test_conflicting_answer_rejects_the_entire_file_after_normalization(self):
        business = Business.objects.create(name="Coffee House")
        KnowledgeItem.objects.create(business=business, question="Café?", answer="Old answer")

        with self.assertRaisesRegex(KnowledgeImportError, "conflicts"):
            import_qa_json(business, b'[{"question":"Caf\xc3\xa9?","answer":"New answer"}]')

        self.assertEqual(KnowledgeItem.objects.filter(business=business).count(), 1)

    def test_replacement_drafts_are_included_in_duplicate_and_conflict_checks(self):
        business = Business.objects.create(name="Coffee House")
        original = KnowledgeItem.objects.create(business=business, question="Hours?", answer="Nine to five")
        KnowledgeItem.objects.create(
            business=business,
            question="Delivery?",
            answer="Available weekdays",
            replacement_for=original,
        )

        duplicate = import_qa_json(
            business,
            b'[{"question":"Delivery?","answer":"Available weekdays"}]',
        )
        self.assertEqual((duplicate.created, duplicate.skipped), (0, 1))
        with self.assertRaisesRegex(KnowledgeImportError, "conflicts"):
            import_qa_json(business, b'[{"question":"Delivery?","answer":"Not available"}]')
        self.assertEqual(KnowledgeItem.objects.filter(business=business).count(), 2)

    def test_decoder_limits_and_invalid_unicode_reject_the_file(self):
        business = Business.objects.create(name="Coffee House")
        for content in [
            b'[{"question":' + (b"9" * 5000) + b',"answer":"Nine to five"}]',
            b'[{"question":"\\ud800","answer":"Nine to five"}]',
        ]:
            with self.subTest(content=content[:30]):
                with self.assertRaises(KnowledgeImportError):
                    import_qa_json(business, content)
        self.assertFalse(KnowledgeItem.objects.filter(business=business).exists())

    def test_admin_uploads_json_for_the_selected_business(self):
        business = Business.objects.create(name="Coffee House")
        get_user_model().objects.create_superuser("owner", "owner@example.com", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        self.assertContains(self.client.get("/admin/businesses/business/"), "Import Q")
        upload = SimpleUploadedFile(
            "qa.json",
            b'[{"question":"Hours?","answer":"Nine to five"}]',
            content_type="application/json",
        )

        response = self.client.post(
            "/admin/businesses/business/import-qa/",
            {"business": business.pk, "file": upload},
        )

        self.assertRedirects(response, "/admin/businesses/knowledgeitem/", fetch_redirect_response=False)
        item = KnowledgeItem.objects.get(business=business)
        self.assertEqual((item.question, item.answer, item.status), ("Hours?", "Nine to five", KnowledgeItem.Status.DRAFT))

    def test_imported_draft_can_be_published_and_answered(self):
        business = Business.objects.create(name="Coffee House")
        import_qa_json(business, b'[{"question":"Hours?","answer":"Nine to five"}]')
        item = KnowledgeItem.objects.get(business=business)

        publish_item(
            item,
            embed_document=lambda text: [1.0, 0.0],
            upsert_vector=lambda business, item_id, vector: None,
        )
        answer = answer_question(
            business,
            "When do you open?",
            embed_query=lambda text: [1.0, 0.0],
            search_vectors=lambda business, vector, limit, threshold, active_vector_ids: [(item.id, 0.91)],
            complete=lambda question, knowledge: CompletionResult("answer", str(knowledge[0]["answer"]), ("src-1",)),
        )

        self.assertEqual(answer.text, "Nine to five")
