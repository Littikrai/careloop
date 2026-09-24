import uuid
import unicodedata

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


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
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.question
