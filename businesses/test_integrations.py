from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from unittest.mock import patch

from .models import Business, BusinessIntegration, KnowledgeItem


class BusinessIntegrationTests(TestCase):
    def test_business_integration_creates_public_embed_token_and_rotatable_api_key(self):
        business = Business.objects.create(name="Coffee House")
        integration = BusinessIntegration.objects.create(
            business=business,
            allowed_origins=["http://localhost:3000", "https://coffee.example"],
        )

        key, secret = integration.create_api_key()

        self.assertTrue(integration.embed_token)
        self.assertTrue(secret)
        self.assertNotIn(secret, key.secret_hash)
        self.assertTrue(key.is_active())

    def test_new_api_key_expires_the_previous_active_key_after_24_hours(self):
        integration = BusinessIntegration.objects.create(
            business=Business.objects.create(name="Coffee House"),
            allowed_origins=["https://coffee.example"],
        )
        previous_key, _ = integration.create_api_key()
        current_key, _ = integration.create_api_key()

        previous_key.refresh_from_db()
        self.assertIsNotNone(previous_key.expires_at)
        self.assertTrue(previous_key.is_active())
        self.assertIsNone(current_key.expires_at)

    def test_rotating_embed_token_immediately_invalidates_the_old_token(self):
        integration = BusinessIntegration.objects.create(
            business=Business.objects.create(name="Coffee House"),
            allowed_origins=["https://coffee.example"],
        )
        old_token = integration.embed_token

        integration.rotate_embed_token()

        self.assertNotEqual(old_token, integration.embed_token)
        self.assertFalse(BusinessIntegration.objects.filter(embed_token=old_token).exists())

    def test_allowed_origins_must_be_exact_http_origins(self):
        business = Business.objects.create(name="Coffee House")
        integration = BusinessIntegration(business=business, allowed_origins=["https://coffee.example/path"])

        with self.assertRaises(ValidationError):
            integration.full_clean()

    def test_allowed_origins_reject_wildcards_and_malformed_hosts(self):
        business = Business.objects.create(name="Coffee House")

        for origin in ["https://*", "https://*.coffee.example", "https://coffee.example other.example"]:
            with self.subTest(origin=origin):
                integration = BusinessIntegration(business=business, allowed_origins=[origin])
                with self.assertRaises(ValidationError):
                    integration.full_clean()

    def test_origins_are_normalized_for_csp(self):
        integration = BusinessIntegration(
            business=Business.objects.create(name="Coffee House"),
            allowed_origins=["HTTPS://Coffee.Example:443/", "http://localhost:3000"],
        )

        integration.full_clean()

        self.assertEqual(integration.allowed_origins, ["https://coffee.example", "http://localhost:3000"])


class BusinessIntegrationAdminTests(TestCase):
    def setUp(self) -> None:
        get_user_model().objects.create_superuser("owner", "owner@example.com", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")

    def test_admin_creates_an_integration_with_one_origin_per_line(self):
        business = Business.objects.create(name="Coffee House")

        response = self.client.post(
            "/admin/businesses/businessintegration/add/",
            {
                "business": business.pk,
                "allowed_origins": "https://coffee.example\nhttp://localhost:3000",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        integration = BusinessIntegration.objects.get(business=business)
        self.assertEqual(integration.allowed_origins, ["https://coffee.example", "http://localhost:3000"])
        detail = self.client.get(f"/admin/businesses/businessintegration/{integration.pk}/change/")
        self.assertContains(detail, "data-token")
        self.assertContains(detail, integration.embed_token)


class EmbeddedChatTests(TestCase):
    def setUp(self) -> None:
        self.business = Business.objects.create(name="Coffee House")
        self.integration = BusinessIntegration.objects.create(
            business=self.business,
            allowed_origins=["https://coffee.example", "http://localhost:3000"],
        )
        self.item = KnowledgeItem.objects.create(
            business=self.business,
            question="Hours?",
            answer="Nine to five",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )

    def test_embed_page_allows_only_configured_parent_origins(self):
        response = self.client.get(f"/embed/{self.integration.embed_token}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Security-Policy"],
            "frame-ancestors https://coffee.example http://localhost:3000",
        )
        self.assertNotIn("X-Frame-Options", response)
        self.assertContains(response, "customer-service-close")

    def test_invalid_or_rotated_token_cannot_open_embed_page(self):
        old_token = self.integration.embed_token
        self.integration.rotate_embed_token()

        self.assertEqual(self.client.get(f"/embed/{old_token}/").status_code, 404)
        self.assertEqual(self.client.get("/embed/not-a-token/").status_code, 404)

    def test_embed_chat_uses_its_business_rag_without_csrf_cookie(self):
        other = Business.objects.create(name="Book Store")
        KnowledgeItem.objects.create(
            business=other,
            question="Hours?",
            answer="Ten to six",
            status=KnowledgeItem.Status.PUBLISHED,
            index_status=KnowledgeItem.IndexStatus.READY,
        )
        browser = Client(enforce_csrf_checks=True)
        with (
            patch("businesses.vector_store.embed_query", return_value=[1.0, 0.0]),
            patch("businesses.vector_store.search_vectors", return_value=[(self.item.id, 0.91)]),
            patch("businesses.openrouter.complete_answer", return_value="Nine to five") as complete,
        ):
            response = browser.post(f"/embed/{self.integration.embed_token}/", {"question": "Hours?"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nine to five")
        self.assertNotContains(response, "Ten to six")
        self.assertEqual(complete.call_args.args[0], "Hours?")

    def test_widget_script_has_an_accessible_toggle_and_uses_the_embed_token(self):
        from django.contrib.staticfiles import finders

        script_path = finders.find("businesses/widget.js")
        self.assertIsNotNone(script_path)
        assert script_path is not None
        script = open(script_path).read()

        self.assertIn("aria-label", script)
        self.assertIn("dataset.token", script)
        self.assertIn("/embed/", script)
        self.assertIn("event.source === frame.contentWindow", script)

    def test_widget_demo_page_installs_a_supplied_embed_token(self):
        response = self.client.get(f"/widget-test/?token={self.integration.embed_token}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.integration.embed_token)
        self.assertContains(response, "/static/businesses/widget.js")
