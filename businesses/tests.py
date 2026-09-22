from django.contrib.auth import get_user_model
from django.test import TestCase

class BusinessJourneyTests(TestCase):
    def test_admin_creates_business_and_visitors_see_empty_chat(self):
        get_user_model().objects.create_superuser("owner", "owner@example.com", "Strong-password-123")
        self.assertTrue(self.client.login(username="owner", password="Strong-password-123"))
        response = self.client.post("/admin/businesses/business/add/", {"name": "Coffee House", "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        listing = self.client.get("/admin/businesses/business/")
        self.assertContains(listing, "Coffee House")
        import re
        links = re.findall(r'href="(/chat/[^" ]+/)"', listing.content.decode())
        self.assertEqual(len(links), 1)
        self.client.logout()
        chat = self.client.get(links[0])
        self.assertContains(chat, "Coffee House")
        self.assertContains(chat, "not available yet")

    def test_two_businesses_have_separate_pages_and_unknown_business_is_404(self):
        import re
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.client.login(username="owner", password="Strong-password-123")
        for name in ["Coffee House", "Book Store"]:
            self.assertEqual(self.client.post("/admin/businesses/business/add/", {"name": name, "_save": "Save"}).status_code, 302)
        listing = self.client.get("/admin/businesses/business/")
        links = re.findall(r'href="(/chat/[^" ]+/)"', listing.content.decode())
        self.assertEqual(len(set(links)), 2)
        self.client.logout()
        for link in links:
            content = self.client.get(link).content.decode()
            self.assertNotEqual("Coffee House" in content, "Book Store" in content)
        self.assertEqual(self.client.get("/chat/00000000-0000-0000-0000-000000000000/").status_code, 404)

    def test_admin_requires_login_and_logout_revokes_access(self):
        from django.test import Client
        secured = Client(enforce_csrf_checks=True)
        self.assertEqual(secured.post("/admin/businesses/business/add/", {"name": "Intruder"}).status_code, 403)
        self.assertRedirects(self.client.get("/admin/businesses/business/"), "/admin/login/?next=/admin/businesses/business/", fetch_redirect_response=False)
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        self.assertFalse(self.client.login(username="owner", password="wrong"))
        self.client.login(username="owner", password="Strong-password-123")
        self.assertEqual(self.client.post("/admin/logout/").status_code, 200)
        self.assertEqual(self.client.get("/admin/businesses/business/").status_code, 302)
        get_user_model().objects.create_user("visitor", password="Strong-password-456")
        self.client.login(username="visitor", password="Strong-password-456")
        self.assertEqual(self.client.post("/admin/businesses/business/add/", {"name": "Intruder"}).status_code, 302)

    def test_real_login_form_and_csrf_protect_mutations(self):
        import re
        from django.test import Client
        get_user_model().objects.create_superuser("owner", "", "Strong-password-123")
        browser = Client(enforce_csrf_checks=True)
        form = browser.get("/admin/login/")
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form.content.decode())
        assert match is not None
        token = match.group(1)
        self.assertEqual(browser.post("/admin/login/", {"username": "owner", "password": "Strong-password-123", "csrfmiddlewaretoken": token, "next": "/admin/"}).status_code, 302)
        self.assertEqual(browser.post("/admin/businesses/business/add/", {"name": "No token"}).status_code, 403)
        form = browser.get("/admin/businesses/business/add/")
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form.content.decode())
        assert match is not None
        token = match.group(1)
        invalid = browser.post("/admin/businesses/business/add/", {"name": "  ", "csrfmiddlewaretoken": token})
        self.assertContains(invalid, "This field is required")
        created = browser.post("/admin/businesses/business/add/", {"name": "<script>alert(1)</script>", "csrfmiddlewaretoken": token, "_save": "Save"})
        self.assertEqual(created.status_code, 302)
        listing = browser.get("/admin/businesses/business/")
        self.assertNotContains(listing, "<script>alert(1)</script>")

    def test_accounts_and_businesses_survive_new_process(self):
        import os
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as data:
            env = {**os.environ, "DATA_DIR": data, "DJANGO_SETTINGS_MODULE": "config.settings", "DJANGO_SECRET_KEY": "persistence-test-only-" * 4, "DJANGO_ALLOWED_HOSTS": "testserver", "DJANGO_SUPERUSER_USERNAME": "owner", "DJANGO_SUPERUSER_EMAIL": "owner@example.com", "DJANGO_SUPERUSER_PASSWORD": "Strong-password-123"}
            subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], env=env, check=True, capture_output=True)
            subprocess.run([sys.executable, "manage.py", "createsuperuser", "--noinput"], env=env, check=True, capture_output=True)
            common = "import django; django.setup(); from django.test import Client; c=Client(); assert c.login(username='owner',password='Strong-password-123'); "
            subprocess.run([sys.executable, "-c", common + "assert c.post('/admin/businesses/business/add/', {'name':'Persistent shop','_save':'Save'}).status_code == 302"], env=env, check=True, capture_output=True)
            subprocess.run([sys.executable, "-c", common + "assert b'Persistent shop' in c.get('/admin/businesses/business/').content"], env=env, check=True, capture_output=True)
