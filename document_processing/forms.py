# document_processing/forms.py

from django import forms
from .models import Document, SourceType


class DocumentUploadForm(forms.ModelForm):
    source_type = forms.ChoiceField(
        choices=SourceType.choices,
        widget=forms.RadioSelect,
        initial=SourceType.FILE,
        label="Upload Method",
        help_text="Choose whether to upload a file, paste a URL, or enter raw text.",
    )

    file = forms.FileField(
        required=False,
        label="Upload File",
        help_text="Allowed: PDF, DOCX, or Markdown files. Max 10MB.",
    )

    url = forms.URLField(
        required=False,
        label="Webpage URL",
        help_text="Enter a public link to the content you'd like to process.",
    )

    text = forms.CharField(
        required=False,
        label="Raw Text",
        help_text="Paste plain text content (e.g. from a document or article).",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )

    class Meta:
        model = Document
        fields = ["title", "source_type"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Enter a title"}
        )
        self.fields["title"].help_text = (
            "Give your document a short, descriptive title."
        )
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["url"].widget.attrs.update(
            {"class": "form-control", "placeholder": "https://example.com"}
        )
        self.fields["text"].widget.attrs.update({"class": "form-control", "rows": 5})

    def clean(self):
        cleaned = super().clean()
        stype = cleaned.get("source_type")
        uploaded = cleaned.get("file")
        url = cleaned.get("url")
        text = cleaned.get("text")

        if stype == SourceType.FILE and not uploaded:
            self.add_error("file", "Please upload a file for this source type.")
        if stype == SourceType.URL and not url:
            self.add_error("url", "Please enter a URL for this source type.")
        if stype == SourceType.TEXT and not text:
            self.add_error("text", "Please enter some text for this source type.")

        # Prevent submission of extra fields (optional but safer)
        if stype != SourceType.FILE and uploaded:
            self.add_error("file", "Remove the file when not in FILE mode.")
        if stype != SourceType.URL and url:
            self.add_error("url", "Remove the URL when not in URL mode.")
        if stype != SourceType.TEXT and text:
            self.add_error("text", "Remove the text when not in TEXT mode.")

        return cleaned

