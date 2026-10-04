import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .document_importer import DocumentImportError, import_document_json
from .models import Business, Document, DocumentRevision


class DocumentImportTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Router shop")
        self.other = Business.objects.create(name="Book shop")

    def test_import_normalizes_and_skips_duplicates_without_crossing_businesses(self):
        existing = Document.objects.create(business=self.business)
        DocumentRevision.objects.create(document=existing, title="Café", content="Old details")
        other = Document.objects.create(business=self.other)
        DocumentRevision.objects.create(document=other, title="Same title", content="Different business")
        payload = [
            {"title": " Cafe\u0301 ", "content": " Old details ", "product": "", "version": ""},
            {"title": "Same title", "content": "Different business"},
            {"title": " Same title ", "content": "Different business"},
            {"title": "Same title", "content": "New content", "product": " X500 ", "version": " 2026 "},
        ]

        with (
            patch("businesses.vector_store.embed_document", side_effect=AssertionError("Import must not embed")),
            patch("businesses.vector_store.upsert_vector", side_effect=AssertionError("Import must not index")),
        ):
            result = import_document_json(self.business, json.dumps(payload).encode(), source_name="catalog.json")

        self.assertEqual((result.created, result.skipped), (2, 2))
        drafts = DocumentRevision.objects.filter(document__business=self.business, source_name="catalog.json")
        self.assertEqual(drafts.count(), 2)
        self.assertTrue(all(item.status == DocumentRevision.Status.DRAFT for item in drafts))
        self.assertTrue(all(item.index_status == DocumentRevision.IndexStatus.NOT_INDEXED for item in drafts))
        self.assertEqual(drafts.get(content="New content").product, "X500")
        self.assertEqual(Document.objects.filter(business=self.other).count(), 1)

        repeated = import_document_json(self.business, json.dumps(payload).encode(), source_name="another.json")
        self.assertEqual((repeated.created, repeated.skipped), (0, 4))
        self.assertEqual(Document.objects.filter(business=self.business).count(), 3)

    def test_example_file_is_importable(self):
        example = Path(__file__).resolve().parent.parent / "examples" / "document-import.example.json"
        result = import_document_json(self.business, example.read_bytes(), source_name=example.name)
        self.assertEqual((result.created, result.skipped), (3, 0))
        self.assertEqual(DocumentRevision.objects.filter(document__business=self.business).count(), 3)

    def test_invalid_later_item_rejects_entire_file_with_position(self):
        valid = {"title": "First", "content": "Good"}
        bad_items = [
            ({"title": "Missing content"}, "content"),
            ({"title": "Extra", "content": "Good", "business": str(self.other.pk)}, "business"),
            ({"title": 123, "content": "Good"}, "title"),
            ({"title": "Blank", "content": "   "}, "content"),
            ({"title": "Too long", "content": "x" * (256 * 1024 + 1)}, "256 KiB"),
            ({"title": "x" * 201, "content": "Good"}, "title"),
            ({"title": "Long product", "content": "Good", "product": "x" * 121}, "product"),
            ({"title": "Bad Unicode", "content": "\ud800"}, "Unicode"),
        ]
        for bad, reason in bad_items:
            with self.subTest(reason=reason):
                with self.assertRaises(DocumentImportError) as caught:
                    import_document_json(self.business, json.dumps([valid, bad]).encode())
                self.assertIn("Item 2", str(caught.exception))
                self.assertIn(reason, str(caught.exception))
                self.assertFalse(Document.objects.exists())

    def test_invalid_file_and_oversized_import_are_rejected(self):
        cases = [b"\xff", b"{}", b"[]", b"[", b"[null]", b" " * (5 * 1024 * 1024 + 1)]
        for content in cases:
            with self.subTest(content=content[:15]):
                with self.assertRaises(DocumentImportError):
                    import_document_json(self.business, content)
                self.assertFalse(Document.objects.exists())

    def test_database_failure_rolls_back_all_documents(self):
        payload = json.dumps([
            {"title": "One", "content": "First"},
            {"title": "Two", "content": "Second"},
        ]).encode()
        create = DocumentRevision.objects.create
        count = 0

        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("database write failed")
            return create(*args, **kwargs)

        with patch("businesses.document_importer.DocumentRevision.objects.create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                import_document_json(self.business, payload)
        self.assertFalse(Document.objects.exists())
        self.assertFalse(DocumentRevision.objects.exists())

    def test_admin_import_shows_result_and_filters_drafts_for_selected_business(self):
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        self.assertContains(self.client.get("/admin/businesses/documentrevision/"), "Import Documents from JSON")
        upload = SimpleUploadedFile("catalog.json", json.dumps([
            {"title": "Router X500", "content": "WAN throughput: 2.5 Gbps"},
            {"title": "Router X500", "content": "WAN throughput: 2.5 Gbps"},
        ]).encode())

        response = self.client.post(
            "/admin/businesses/documentrevision/import-json/",
            {"business": self.business.pk, "file": upload},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"document__business__id__exact={self.business.pk}", response.request["QUERY_STRING"])
        self.assertIn("status__exact=draft", response.request["QUERY_STRING"])
        self.assertContains(response, "Created 1 document draft(s); skipped 1 duplicate(s).")
        self.assertContains(response, "Router X500")
        self.assertEqual(DocumentRevision.objects.get().source_name, "catalog.json")

    def test_admin_invalid_upload_keeps_form_and_creates_nothing(self):
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        upload = SimpleUploadedFile("bad.json", b'[{"title":"Good","content":"Fine"},{"title":"Bad"}]')
        response = self.client.post(
            "/admin/businesses/documentrevision/import-json/",
            {"business": self.business.pk, "file": upload},
        )
        self.assertContains(response, "Item 2")
        self.assertFalse(Document.objects.exists())

        too_large = SimpleUploadedFile("huge.json", b" " * (5 * 1024 * 1024 + 1))
        response = self.client.post(
            "/admin/businesses/documentrevision/import-json/",
            {"business": self.business.pk, "file": too_large},
        )
        self.assertContains(response, "5 MiB")
        self.assertFalse(Document.objects.exists())
