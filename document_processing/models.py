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


class TaskFailureAlert(models.Model):
    """
    Tracks task failures and stores alert history for monitoring and investigation.

    When a Celery task fails, an alert record is created here with full context.
    This allows admins to investigate failures, understand patterns, and debug issues.

    Fields:
        - task_name: Name of the failed task (e.g., 'parse_document_task')
        - document: Link to related document (if applicable)
        - user: User whose action triggered the task (if applicable)
        - error_message: Full error message from the exception
        - error_traceback: Full traceback for debugging
        - task_args: Arguments passed to the task (JSON)
        - task_kwargs: Keyword arguments passed to the task (JSON)
        - retry_count: Number of times task was retried
        - created_at: When the failure occurred
        - resolved_at: When admin resolved the issue (null if unresolved)
        - resolution_notes: Admin notes about the fix
    """

    TASK_CHOICES = [
        ("parse_document_task", "Parse Document Task"),
        ("generate_audio_task", "Generate Audio Task"),
        ("cleanup_task", "Cleanup Task"),
        ("other", "Other Task"),
    ]

    STATUS_CHOICES = [
        ("NEW", "New Alert"),
        ("ACKNOWLEDGED", "Acknowledged"),
        ("INVESTIGATING", "Under Investigation"),
        ("RESOLVED", "Resolved"),
        ("IGNORED", "Ignored"),
    ]

    task_name = models.CharField(
        max_length=100, choices=TASK_CHOICES, help_text="Name of the failed Celery task"
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_failures",
        help_text="Related document, if applicable",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_failures",
        help_text="User whose action triggered the task",
    )
    error_message = models.TextField(help_text="Error message from the exception")
    error_traceback = models.TextField(
        blank=True, help_text="Full exception traceback for debugging"
    )
    task_args = models.JSONField(
        default=list, blank=True, help_text="Positional arguments passed to task"
    )
    task_kwargs = models.JSONField(
        default=dict, blank=True, help_text="Keyword arguments passed to task"
    )
    retry_count = models.IntegerField(default=0, help_text="Number of retry attempts")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="NEW",
        help_text="Current status of the alert",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="When the failure occurred"
    )
    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="When admin resolved the issue"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_task_failures",
        help_text="Admin who resolved the issue",
    )
    resolution_notes = models.TextField(
        blank=True, help_text="Admin notes about the resolution"
    )
    email_sent = models.BooleanField(
        default=False, help_text="Whether alert email was sent"
    )
    email_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="When alert email was sent"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["task_name", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]
        verbose_name = "Task Failure Alert"
        verbose_name_plural = "Task Failure Alerts"

    def __str__(self):
        return f"{self.get_task_name_display()} - {self.get_status_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"

    def mark_resolved(self, notes="", resolved_by=None):
        """Mark this alert as resolved."""
        from django.utils import timezone

        self.status = "RESOLVED"
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        self.resolution_notes = notes
        self.save()
