from django.db import models
from django.conf import settings


# These choices will be used for the status fields. Using a class like this
# makes the code more organized and readable. It also prevents typos since
# we can refer to statuses like `TextStatus.PENDING` instead of typing "Pending".
class TextStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing Text"
    COMPLETED = "COMPLETED", "Text Ready"
    FAILED = "FAILED", "Failed"


class AudioStatus(models.TextChoices):
    AUDIO_PENDING = "AUDIO_PENDING", "Ready to Generate"
    AUDIO_GENERATING = "AUDIO_GENERATING", "Generating Audio"
    AUDIO_COMPLETED = "AUDIO_COMPLETED", "Audio Ready"
    AUDIO_FAILED = "AUDIO_FAILED", "Audio Failed"


# This class define the different types of document sources we can handle.
class SourceType(models.TextChoices):
    FILE = "FILE", "File Upload"
    URL = "URL", "Webpage URL"
    TEXT = "TEXT", "Raw Text Input"  # Added for future flexibility!


class Document(models.Model):
    """
    Represents an uploaded document file. This is the master record for each upload.
    """

    # Foreign Key to the user who owns this document.
    # `settings.AUTH_USER_MODEL` is the best practice for referring to the user model.
    # `on_delete=models.CASCADE` means if a user is deleted, all their documents are also deleted.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        help_text="The user who uploaded the document.",
    )
    title = models.CharField(max_length=255, help_text="The title of the document.")

    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.FILE,
        help_text="The type of the source content (File, URL, etc.).",
    )

    # This field now generically stores the source, either an S3 path or a URL.
    source_content = models.CharField(
        max_length=1024,
        blank=True,
        help_text="The path to the original document file in S3 or the URL of the webpage.",
    )

    status = models.CharField(
        max_length=20,
        choices=TextStatus.choices,
        default=TextStatus.PENDING,
        help_text="The current status of the text extraction process.",
    )

    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Any error message that occurred during processing.",
    )
    # Timestamps for tracking when the record was created and last updated.
    # `auto_now_add=True` sets the creation timestamp automatically.
    # `auto_now=True` updates the timestamp every time the model is saved.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} (User: {self.user.email})"

    class Meta:
        # This ensures that documents are ordered by creation date by default.
        ordering = ["-created_at"]


class DocumentPage(models.Model):
    """
    Represents a single page within a Document.
    """

    # Link back to the parent document.
    # `related_name='pages'` lets us access all pages of a document
    # with `document.pages.all()`.
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="pages",
        help_text="The parent document this page belongs to.",
    )
    page_number = models.PositiveIntegerField(
        help_text="The page number in the original document."
    )
    # `TextField` is used for storing large amounts of text.
    markdown_content = models.TextField(
        blank=True, help_text="The extracted text(markdown) content of this page."
    )
    audio_status = models.CharField(
        max_length=20,
        choices=AudioStatus.choices,
        default=AudioStatus.AUDIO_PENDING,
        help_text="The current status of the audio generation for this page.",
    )

    # We will store the public URL to the generated MP3 file in S3 here.
    audio_file_s3_url = models.URLField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="The public URL to the generated audio file in AWS S3.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Page {self.page_number} of {self.document.title}"

    class Meta:
        # This ensures that pages are ordered by their page number within a document.
        # The `unique_together` constraint prevents duplicate page numbers for the same document.
        ordering = ["document", "page_number"]
        unique_together = ("document", "page_number")
