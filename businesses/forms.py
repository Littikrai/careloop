from django import forms

from .models import Business


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
