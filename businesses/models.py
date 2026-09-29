import uuid
import unicodedata
import hashlib
import ipaddress
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


def _new_embed_token() -> str:
    return secrets.token_urlsafe(32)


_HOSTNAME_PATTERN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*",
    re.ASCII,
)


def _normalise_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError from error
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME_PATTERN.fullmatch(host):
            raise ValueError
    if ":" in host:
        host = f"[{host}]"
    if port and port != {"http": 80, "https": 443}[scheme]:
        host = f"{host}:{port}"
    return f"{scheme}://{host}"


class Business(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "businesses"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("business-chat", kwargs={"business_id": self.pk})


class KnowledgeItem(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class IndexStatus(models.TextChoices):
        NOT_INDEXED = "not_indexed", "Not indexed"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="knowledge_items")
    vector_id = models.UUIDField(blank=True, null=True, editable=False)
    replacement_for = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="replacement_drafts",
    )
    question = models.TextField()
    answer = models.TextField()
    status = models.CharField(max_length=16, choices=Status, default=Status.DRAFT)
    index_status = models.CharField(max_length=16, choices=IndexStatus, default=IndexStatus.NOT_INDEXED)
    index_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business", "question", "id"]
        verbose_name = "Q&A"
        verbose_name_plural = "Q&A"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "question", "answer"],
                name="unique_business_question_answer",
                condition=Q(replacement_for__isnull=True),
            )
        ]

    def clean(self) -> None:
        self.question = unicodedata.normalize("NFC", self.question.strip())
        self.answer = unicodedata.normalize("NFC", self.answer.strip())
        errors = {}
        if not self.question:
            errors["question"] = "Question cannot be empty."
        if not self.answer:
            errors["answer"] = "Answer cannot be empty."
        replacement = self.replacement_for
        if replacement and replacement.business_id != self.business_id:
            errors["replacement_for"] = "A replacement must belong to the same business."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if self.status == self.Status.PUBLISHED and self.vector_id is None:
            self.vector_id = self.id
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.question


class BusinessIntegration(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="integration")
    embed_token = models.CharField(max_length=64, unique=True, default=_new_embed_token)
    allowed_origins = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self) -> None:
        errors = {}
        if not isinstance(self.allowed_origins, list) or not self.allowed_origins:
            errors["allowed_origins"] = "Add at least one allowed origin."
        else:
            normalised_origins = []
            for origin in self.allowed_origins:
                if not isinstance(origin, str):
                    errors["allowed_origins"] = "Origins must be exact http or https origins without paths."
                    break
                try:
                    normalised_origins.append(_normalise_origin(origin))
                except ValueError:
                    errors["allowed_origins"] = "Origins must be exact http or https origins without paths."
                    break
            if not errors and len(set(normalised_origins)) != len(normalised_origins):
                errors["allowed_origins"] = "Each allowed origin can only be added once."
            if not errors:
                self.allowed_origins = normalised_origins
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def create_api_key(self) -> tuple["BusinessApiKey", str]:
        now = timezone.now()
        self.api_keys.filter(revoked_at__isnull=True, expires_at__isnull=True).update(expires_at=now + timedelta(hours=24))
        secret = secrets.token_urlsafe(32)
        key = self.api_keys.create(secret_hash=hashlib.sha256(secret.encode()).hexdigest())
        return key, secret

    def rotate_embed_token(self) -> None:
        self.embed_token = _new_embed_token()
        self.save(update_fields=["embed_token", "updated_at"])

    def __str__(self) -> str:
        return f"Integration for {self.business}"


class BusinessApiKey(models.Model):
    integration = models.ForeignKey(BusinessIntegration, on_delete=models.CASCADE, related_name="api_keys")
    secret_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_active(self) -> bool:
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > timezone.now())
