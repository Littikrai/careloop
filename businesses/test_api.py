import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Business, BusinessIntegration
from .rag import AnswerResult


class ChatApiTests(TestCase):
    def setUp(self) -> None:
        self.business = Business.objects.create(name="Coffee House")
        self.integration = BusinessIntegration.objects.create(
            business=self.business,
            allowed_origins=["http://localhost:3000"],
        )
        self.key, self.secret = self.integration.create_api_key()

    def post(self, secret: str | None, payload: object):
        headers = None if secret is None else {"Authorization": f"Bearer {secret}"}
        return self.client.post(
            "/api/v1/chat",
            data=json.dumps(payload),
            content_type="application/json",
            headers=headers,
        )

    def test_api_key_answers_for_its_business_without_cors(self):
        with patch("businesses.views.answer_question", return_value=AnswerResult("answer", "Nine to five")) as answer:
            response = self.post(self.secret, {"question": "Hours?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "Nine to five", "status": "answer"})
        answer.assert_called_once_with(self.business, "Hours?")
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_missing_or_revoked_key_returns_the_same_unauthorized_response(self):
        missing = self.post(None, {"question": "Hours?"})
        self.key.revoked_at = timezone.now()
        self.key.save(update_fields=["revoked_at"])
        revoked = self.post(self.secret, {"question": "Hours?"})

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(revoked.status_code, 401)
        self.assertEqual(missing.json(), revoked.json())

    def test_expired_key_returns_unauthorized(self):
        self.key.expires_at = timezone.now()
        self.key.save(update_fields=["expires_at"])

        response = self.post(self.secret, {"question": "Hours?"})

        self.assertEqual(response.status_code, 401)

    def test_json_question_is_required_and_must_be_a_nonempty_string(self):
        for payload in [{}, {"question": ""}, {"question": 4}, []]:
            with self.subTest(payload=payload):
                response = self.post(self.secret, payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_malformed_json_returns_a_validation_error(self):
        response = self.client.post(
            "/api/v1/chat",
            data=b'{"question":',
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.secret}"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_json_decoder_limits_are_validation_errors(self):
        response = self.client.post(
            "/api/v1/chat",
            data=b'{"question":' + (b"9" * 5000) + b"}",
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.secret}"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_rag_or_llm_failure_returns_a_nonrevealing_service_error(self):
        with patch("businesses.views.answer_question", side_effect=RuntimeError("Qdrant stack trace")):
            response = self.post(self.secret, {"question": "Hours?"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": {"code": "service_unavailable", "message": "Chat is temporarily unavailable."}})

    @override_settings(API_RATE_LIMIT_PER_MINUTE=1)
    def test_api_rate_limit_is_per_api_key(self):
        cache.clear()
        with patch("businesses.views.answer_question", return_value=AnswerResult("answer", "Nine to five")):
            first = self.post(self.secret, {"question": "First"})
            second = self.post(self.secret, {"question": "Second"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"]["code"], "rate_limited")
