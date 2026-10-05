from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .document_chunks import PreviewChunk
from .document_knowledge import (
    active_document_chunks,
    archive_document,
    create_document_draft,
    delete_document_revision,
    publish_document,
)
from .models import Business, Document, DocumentChunk, DocumentRevision


class DocumentLifecycleTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Router shop")
        self.document = Document.objects.create(business=self.business)
        self.published = DocumentRevision.objects.create(
            document=self.document,
            revision_number=1,
            title="X500 manual",
            product="X500",
            version="2026",
            source_name="manual.md",
            content="WAN throughput is 2.5 Gbps.",
            status=DocumentRevision.Status.PUBLISHED,
            index_status=DocumentRevision.IndexStatus.READY,
        )
        self.chunk = DocumentChunk.objects.create(
            revision=self.published,
            order=1,
            text="WAN throughput is 2.5 Gbps.",
            index_status=DocumentChunk.IndexStatus.READY,
        )
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")

    def test_admin_can_create_only_one_draft_copy_of_a_published_document(self):
        url = reverse("admin:businesses_documentrevision_changelist")

        for _ in range(2):
            response = self.client.post(
                url,
                {"action": "create_replacement_drafts", "_selected_action": str(self.published.pk)},
            )
            self.assertEqual(response.status_code, 302)

        draft = DocumentRevision.objects.get(status=DocumentRevision.Status.DRAFT)
        self.assertEqual(draft.document, self.document)
        self.assertEqual(draft.revision_number, 2)
        self.assertEqual(draft.title, self.published.title)
        self.assertEqual(draft.product, self.published.product)
        self.assertEqual(draft.version, self.published.version)
        self.assertEqual(draft.source_name, self.published.source_name)
        self.assertEqual(draft.content, self.published.content)
        self.assertEqual(self.document.revisions.filter(status=DocumentRevision.Status.DRAFT).count(), 1)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.PUBLISHED)

    def test_admin_uses_selected_published_revision_over_older_archived_revision(self):
        self.published.status = DocumentRevision.Status.ARCHIVED
        self.published.save(update_fields=["status", "updated_at"])
        current = DocumentRevision.objects.create(
            document=self.document,
            revision_number=2,
            title="X500 manual current",
            product="X500",
            version="2027",
            content="WAN throughput is 5 Gbps.",
            status=DocumentRevision.Status.PUBLISHED,
            index_status=DocumentRevision.IndexStatus.READY,
        )

        response = self.client.post(
            reverse("admin:businesses_documentrevision_changelist"),
            {
                "action": "create_replacement_drafts",
                "_selected_action": [str(self.published.pk), str(current.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        draft = DocumentRevision.objects.get(status=DocumentRevision.Status.DRAFT)
        self.assertEqual(draft.revision_number, 3)
        self.assertEqual(draft.content, current.content)

    def test_replacement_becomes_live_only_after_indexing_and_archives_previous_revision(self):
        replacement = create_document_draft(self.published)
        assert replacement is not None
        replacement.content = "WAN throughput is 5 Gbps."
        replacement.save()
        preview = [
            PreviewChunk(
                1,
                "Speed",
                "WAN throughput is 5 Gbps.",
                "X500\nWAN throughput is 5 Gbps.",
                12,
            )
        ]
        deleted = []

        with patch("businesses.document_knowledge.preview_chunks", return_value=preview):
            count = publish_document(
                replacement,
                embed_document=lambda text: [1.0, 0.0],
                upsert_vector=lambda *args: None,
                delete_vector=lambda business, vector_id: deleted.append((business.pk, vector_id)),
            )

        self.assertEqual(count, 1)
        self.published.refresh_from_db()
        replacement.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.ARCHIVED)
        self.assertEqual(replacement.status, DocumentRevision.Status.PUBLISHED)
        self.assertEqual(list(active_document_chunks(self.business).values_list("revision_id", flat=True)), [replacement.pk])
        self.assertEqual(deleted, [(self.business.pk, self.chunk.vector_id)])

    def test_failed_replacement_keeps_previous_revision_live(self):
        replacement = create_document_draft(self.published)
        assert replacement is not None
        preview = [PreviewChunk(1, "Speed", "New speed", "X500\nNew speed", 4)]

        def fail_upsert(*args):
            raise RuntimeError("Qdrant unavailable")

        with patch("businesses.document_knowledge.preview_chunks", return_value=preview):
            with self.assertRaisesRegex(RuntimeError, "Qdrant unavailable"):
                publish_document(
                    replacement,
                    embed_document=lambda text: [1.0],
                    upsert_vector=fail_upsert,
                )

        self.published.refresh_from_db()
        replacement.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.PUBLISHED)
        self.assertEqual(replacement.status, DocumentRevision.Status.DRAFT)
        self.assertEqual(replacement.index_status, DocumentRevision.IndexStatus.FAILED)
        self.assertEqual(list(active_document_chunks(self.business).values_list("revision_id", flat=True)), [self.published.pk])

    def test_archive_confirms_removal_and_archived_revision_can_be_restored_as_a_draft(self):
        url = reverse("admin:businesses_documentrevision_archive", args=[self.published.pk])
        confirmation = self.client.get(url)
        self.assertContains(confirmation, "Confirm archive")
        self.assertContains(confirmation, self.published.title)

        def fail_cleanup(*args):
            raise RuntimeError("Qdrant unavailable")

        with patch(
            "businesses.admin.archive_document",
            side_effect=lambda revision: archive_document(revision, delete_vector=fail_cleanup),
        ):
            response = self.client.post(url, {"confirm": "yes"}, follow=True)

        self.assertContains(response, "Some stale vectors could not be removed")
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.ARCHIVED)
        self.assertFalse(active_document_chunks(self.business).exists())

        response = self.client.post(
            reverse("admin:businesses_documentrevision_changelist"),
            {"action": "create_replacement_drafts", "_selected_action": str(self.published.pk)},
        )
        self.assertEqual(response.status_code, 302)
        restored = DocumentRevision.objects.get(status=DocumentRevision.Status.DRAFT)
        self.assertEqual(restored.revision_number, 2)
        self.assertEqual(restored.content, self.published.content)

    def test_only_draft_or_archived_revisions_can_be_deleted(self):
        with self.assertRaisesRegex(ValueError, "Only a draft or archived"):
            delete_document_revision(self.published, delete_vector=lambda *args: None)

        published_delete = self.client.get(
            reverse("admin:businesses_documentrevision_delete", args=[self.published.pk])
        )
        self.assertEqual(published_delete.status_code, 403)

        draft = create_document_draft(self.published)
        assert draft is not None
        self.published.status = DocumentRevision.Status.ARCHIVED
        self.published.save(update_fields=["status"])
        archived_delete_url = reverse("admin:businesses_documentrevision_delete", args=[self.published.pk])
        self.assertEqual(self.client.get(archived_delete_url).status_code, 200)

        def fail_cleanup(*args):
            raise RuntimeError("Qdrant unavailable")

        with patch(
            "businesses.admin.delete_document_revision",
            side_effect=lambda revision: delete_document_revision(revision, delete_vector=fail_cleanup),
        ):
            response = self.client.post(archived_delete_url, {"post": "yes"}, follow=True)

        self.assertContains(response, "Some stale vectors could not be removed")
        self.assertFalse(DocumentRevision.objects.filter(pk=self.published.pk).exists())
        self.assertTrue(DocumentRevision.objects.filter(pk=draft.pk, status=DocumentRevision.Status.DRAFT).exists())
        self.assertTrue(Document.objects.filter(pk=self.document.pk).exists())
        self.assertFalse(active_document_chunks(self.business).exists())

        draft_delete_url = reverse("admin:businesses_documentrevision_delete", args=[draft.pk])
        self.assertEqual(self.client.post(draft_delete_url, {"post": "yes"}).status_code, 302)
        self.assertFalse(Document.objects.filter(pk=self.document.pk).exists())

    def test_read_only_staff_cannot_archive_a_published_document(self):
        viewer = get_user_model().objects.create_user("viewer", password="Strong-password-123", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_documentrevision"))
        self.client.force_login(viewer)

        response = self.client.post(
            reverse("admin:businesses_documentrevision_archive", args=[self.published.pk]),
            {"confirm": "yes"},
        )

        self.assertEqual(response.status_code, 403)
        self.client.post(
            reverse("admin:businesses_documentrevision_changelist"),
            {"action": "create_replacement_drafts", "_selected_action": str(self.published.pk)},
        )
        self.assertFalse(DocumentRevision.objects.filter(status=DocumentRevision.Status.DRAFT).exists())
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, DocumentRevision.Status.PUBLISHED)
