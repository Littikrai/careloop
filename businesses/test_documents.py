from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Business, Document, DocumentRevision
from .document_chunks import preview_chunks


class CharacterTokenizer:
    def __call__(self, text, *, add_special_tokens=False, return_offsets_mapping=False, verbose=True):
        offsets = [(index, index + 1) for index, char in enumerate(text) if not char.isspace()]
        return {"input_ids": [ord(text[start]) for start, _ in offsets], "offset_mapping": offsets}

    def encode(self, text, *, add_special_tokens=False):
        tokens = self(text)["input_ids"]
        return [1, *tokens, 2] if add_special_tokens else tokens

    def num_special_tokens_to_add(self, *, pair=False):
        return 2


class DocumentAdminTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Fish shop")
        self.other = Business.objects.create(name="Book shop")
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")

    def test_admin_creates_pasted_draft_and_preview_without_indexing(self):
        with (
            patch("businesses.document_chunks.embedding_tokenizer", return_value=(CharacterTokenizer(), 64)),
            patch("businesses.vector_store.embed_document", side_effect=AssertionError("Preview must not embed")),
            patch("businesses.vector_store.upsert_vector", side_effect=AssertionError("Preview must not index")),
        ):
            response = self.client.post(
                "/admin/businesses/documentrevision/add/",
                {
                    "business": self.business.pk,
                    "title": "X500 specs",
                    "product": "Router X500",
                    "version": "2026.1",
                    "content": "## Speed\r\nWAN throughput: 2.5 Gbps\r\n\r\n- Wi-Fi 6\r\n\r\n| Port | Speed |\r\n| --- | --- |\r\n| WAN | 2.5 Gbps |",
                    "_continue": "Save and continue editing",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        revision = DocumentRevision.objects.get()
        self.assertEqual(revision.document.business, self.business)
        self.assertEqual(revision.revision_number, 1)
        self.assertEqual(revision.status, DocumentRevision.Status.DRAFT)
        self.assertEqual(
            revision.content,
            "## Speed\nWAN throughput: 2.5 Gbps\n\n- Wi-Fi 6\n\n| Port | Speed |\n| --- | --- |\n| WAN | 2.5 Gbps |",
        )
        self.assertContains(response, "Chunk preview")
        self.assertContains(response, "Speed")
        self.assertContains(response, "2.5 Gbps")
        self.assertContains(response, "Wi-Fi 6")
        self.assertContains(response, "| Port | Speed |")
        self.assertContains(response, f"{len(revision.content)} characters")
        self.assertEqual(Document.objects.filter(business=self.other).count(), 0)

    def test_draft_can_be_edited_and_preview_updates(self):
        document = Document.objects.create(business=self.business)
        revision = DocumentRevision.objects.create(document=document, title="Manual", content="Old instructions")
        with patch("businesses.document_chunks.embedding_tokenizer", return_value=(CharacterTokenizer(), 64)):
            response = self.client.post(
                f"/admin/businesses/documentrevision/{revision.pk}/change/",
                {"title": "Updated manual", "content": "# Setup\nNew instructions", "product": "X500", "version": "2", "_continue": "Save"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        revision.refresh_from_db()
        self.assertEqual(revision.title, "Updated manual")
        self.assertEqual(revision.content, "# Setup\nNew instructions")
        self.assertEqual(revision.document_id, document.pk)
        self.assertContains(response, "New instructions")
        self.assertContains(response, "Chunk preview")

    def test_admin_upload_sets_title_and_source_name(self):
        file = SimpleUploadedFile("guide.md", "# การใช้งาน\r\nเปิดเครื่องก่อน".encode())
        response = self.client.post(
            "/admin/businesses/documentrevision/add/",
            {"business": self.business.pk, "title": "", "content": "", "upload": file, "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        revision = DocumentRevision.objects.get()
        self.assertEqual(revision.title, "guide")
        self.assertEqual(revision.source_name, "guide.md")
        self.assertEqual(revision.content, "# การใช้งาน\nเปิดเครื่องก่อน")

    def test_invalid_upload_and_oversized_text_do_not_create_document(self):
        cases = [
            ("manual.pdf", b"some text", "TXT or Markdown"),
            ("bad.txt", b"\xff", "UTF-8"),
            ("large.md", b"x" * (256 * 1024 + 1), "256 KiB"),
        ]
        for name, content, error in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    "/admin/businesses/documentrevision/add/",
                    {"business": self.business.pk, "title": "Manual", "content": "", "upload": SimpleUploadedFile(name, content), "_save": "Save"},
                )
                self.assertContains(response, error)
                self.assertFalse(Document.objects.exists())
        response = self.client.post(
            "/admin/businesses/documentrevision/add/",
            {"business": self.business.pk, "title": "Manual", "content": "x" * (256 * 1024 + 1), "_save": "Save"},
        )
        self.assertContains(response, "256 KiB")
        self.assertFalse(Document.objects.exists())

    def test_published_revision_is_view_only(self):
        document = Document.objects.create(business=self.business)
        revision = DocumentRevision.objects.create(
            document=document, revision_number=1, title="Manual", content="Keep this", status=DocumentRevision.Status.PUBLISHED
        )
        response = self.client.post(
            f"/admin/businesses/documentrevision/{revision.pk}/change/",
            {"title": "Changed", "content": "Wrong", "_save": "Save"},
        )
        revision.refresh_from_db()
        self.assertEqual(revision.content, "Keep this")
        self.assertEqual(response.status_code, 403)
        with patch("businesses.document_chunks.embedding_tokenizer", return_value=(CharacterTokenizer(), 64)):
            view = self.client.get(f"/admin/businesses/documentrevision/{revision.pk}/change/")
        self.assertContains(view, "Keep this")
        self.assertNotContains(view, 'name="_save"')


class ChunkPreviewTests(TestCase):
    @override_settings(DOCUMENT_CHUNK_MAX_TOKENS=48)
    def test_overlap_carries_across_headings_in_one_document(self):
        document = Document.objects.create(business=Business.objects.create(name="Router shop"))
        revision = DocumentRevision.objects.create(
            document=document, title="M", content="A" * 30 + "\n# Second\n" + "B" * 20,
        )
        chunks = preview_chunks(revision, tokenizer=CharacterTokenizer(), max_seq_length=48)
        second = next(chunk for chunk in chunks if chunk.heading == "Second")
        self.assertRegex(second.text, r"^A{6}\nB")
        self.assertIn("B" * 20, second.text)

    @override_settings(DOCUMENT_CHUNK_MAX_TOKENS=48)
    def test_short_paragraph_does_not_split_a_following_paragraph_that_fits(self):
        document = Document.objects.create(business=Business.objects.create(name="Router shop"))
        revision = DocumentRevision.objects.create(
            document=document, title="M", content="Short para\n\n" + "x" * 31,
        )
        chunks = preview_chunks(revision, tokenizer=CharacterTokenizer(), max_seq_length=48)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].text, "Short para")
        self.assertIn("x" * 31, chunks[1].text)

    @override_settings(DOCUMENT_CHUNK_MAX_TOKENS=48)
    def test_long_mixed_language_content_uses_token_windows_without_truncation(self):
        document = Document.objects.create(business=Business.objects.create(name="Router shop"))
        revision = DocumentRevision.objects.create(
            document=document, revision_number=1, title="Speed", product="X500",
            content="## Speed\n" + ("ความเร็ว 2.5 Gbps และ Wi-Fi 6\n\n" * 12),
        )
        tokenizer = CharacterTokenizer()
        chunks = preview_chunks(revision, tokenizer=tokenizer, max_seq_length=48)
        self.assertGreater(len(chunks), 2)
        self.assertEqual([chunk.order for chunk in chunks], list(range(1, len(chunks) + 1)))
        self.assertTrue(all(chunk.heading == "Speed" for chunk in chunks))
        self.assertTrue(all(chunk.token_count <= 48 for chunk in chunks))
        self.assertTrue(all(len(tokenizer.encode(chunk.embedding_text, add_special_tokens=True)) <= 48 for chunk in chunks))
        self.assertIn("Wi-Fi 6", " ".join(chunk.text for chunk in chunks))

    @override_settings(DOCUMENT_CHUNK_MAX_TOKENS=48)
    def test_long_metadata_is_trimmed_before_body(self):
        document = Document.objects.create(business=Business.objects.create(name="Router shop"))
        revision = DocumentRevision.objects.create(
            document=document, revision_number=1, title="Very long title", product="X" * 100,
            content="Useful body text about the product.",
        )
        tokenizer = CharacterTokenizer()
        chunks = preview_chunks(revision, tokenizer=tokenizer, max_seq_length=48)
        self.assertTrue(chunks)
        self.assertIn("Useful", chunks[0].text)
        self.assertLessEqual(chunks[0].token_count, 48)
        self.assertLessEqual(
            len(tokenizer.encode(chunks[0].embedding_text.split("\n")[0], add_special_tokens=False)), 12
        )
