from pathlib import Path

from django import forms

from .document_importer import MAX_DOCUMENT_IMPORT_BYTES
from .models import Business, DocumentRevision


class ChatQuestionForm(forms.Form):
    question = forms.CharField(
        max_length=1000,
        strip=True,
        label="Your question",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Type your message..."}),
    )


class KnowledgeImportForm(forms.Form):
    business = forms.ModelChoiceField(queryset=Business.objects.all())
    file = forms.FileField(help_text="UTF-8 JSON array with question and answer fields.")


class DocumentImportForm(forms.Form):
    business = forms.ModelChoiceField(queryset=Business.objects.all())
    file = forms.FileField(help_text="UTF-8 JSON array of documents, up to 5 MiB.")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_DOCUMENT_IMPORT_BYTES:
            raise forms.ValidationError("JSON file cannot exceed 5 MiB.")
        return upload


class DocumentDraftForm(forms.ModelForm):
    business = forms.ModelChoiceField(queryset=Business.objects.all())
    title = forms.CharField(required=False, max_length=200)
    content = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 18}))
    upload = forms.FileField(required=False, help_text="Optional UTF-8 .txt or .md file, up to 256 KiB.")

    class Meta:
        model = DocumentRevision
        fields = ["title", "content", "product", "version"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["business"].required = False

    def clean(self):
        cleaned = super().clean() or {}
        upload = cleaned.get("upload")
        if upload:
            if Path(upload.name).suffix.lower() not in {".txt", ".md"}:
                self.add_error("upload", "Upload a TXT or Markdown (.txt or .md) file.")
            elif upload.size > 256 * 1024:
                self.add_error("upload", "File cannot exceed 256 KiB.")
            elif cleaned.get("content", "").strip():
                self.add_error("upload", "Use either pasted content or a file, not both.")
            else:
                try:
                    cleaned["content"] = upload.read().decode("utf-8-sig")
                except UnicodeDecodeError:
                    self.add_error("upload", "File must contain UTF-8 text.")
                if not cleaned.get("title"):
                    cleaned["title"] = Path(upload.name).stem
        if not cleaned.get("title", "").strip():
            self.add_error("title", "Enter a title or upload a file.")
        content = cleaned.get("content", "")
        if not content.strip():
            self.add_error("content", "Enter content or upload a file.")
        else:
            try:
                size = len(content.encode("utf-8"))
            except UnicodeEncodeError:
                self.add_error("content", "Content must be valid Unicode text.")
            else:
                if size > 256 * 1024:
                    self.add_error("content", "Content cannot exceed 256 KiB of UTF-8 text.")
        return cleaned
