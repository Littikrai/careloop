from django import forms


class ChatQuestionForm(forms.Form):
    question = forms.CharField(
        max_length=1000,
        strip=True,
        label="Your question",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Type your message..."}),
    )
