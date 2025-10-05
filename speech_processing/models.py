from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta


# Choices for audio generation and sharing feature
class AudioGenerationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    GENERATING = "GENERATING", "Generating"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class SharingPermission(models.TextChoices):
    VIEW_ONLY = "VIEW_ONLY", "View Only"
    COLLABORATOR = "COLLABORATOR", "Collaborator"
    CAN_SHARE = "CAN_SHARE", "Can Share"


class AudioAction(models.TextChoices):
    GENERATE = "GENERATE", "Generate"
    PLAY = "PLAY", "Play"
    DOWNLOAD = "DOWNLOAD", "Download"
    DELETE = "DELETE", "Delete"
    SHARE = "SHARE", "Share"
    UNSHARE = "UNSHARE", "Unshare"


class AudioLifetimeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DELETED = "DELETED", "Deleted"
    EXPIRED = "EXPIRED", "Expired"


# Available TTS voices - matches your existing voice preview setup
class TTSVoice(models.TextChoices):
    IVY = "Ivy", "Ivy (English US)"
    JOANNA = "Joanna", "Joanna (English US)"
    JOEY = "Joey", "Joey (English US)"
    JUSTIN = "Justin", "Justin (English US)"
    KENDRA = "Kendra", "Kendra (English US)"
    KIMBERLY = "Kimberly", "Kimberly (English US)"
    MATTHEW = "Matthew", "Matthew (English US)"
    SALLI = "Salli", "Salli (English US)"


class Audio(models.Model):
    """
    Represents a generated audio file for a document page.
    Maximum 4 audios per page (lifetime), unique voices at any time.
    """

    page = models.ForeignKey(
        "document_processing.DocumentPage",
        on_delete=models.CASCADE,
        related_name="audios",
        help_text="The page this audio belongs to.",
    )
    voice = models.CharField(
        max_length=20,
        choices=TTSVoice.choices,
        help_text="The TTS voice used for this audio.",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_audios",
        help_text="The user who generated this audio.",
    )
    s3_key = models.CharField(
        max_length=1024, help_text="The S3 object key for the audio file."
    )
    status = models.CharField(
        max_length=20,
        choices=AudioGenerationStatus.choices,
        default=AudioGenerationStatus.PENDING,
        help_text="The current status of audio generation.",
    )
    lifetime_status = models.CharField(
        max_length=20,
        choices=AudioLifetimeStatus.choices,
        default=AudioLifetimeStatus.ACTIVE,
        help_text="Whether the audio is active, deleted, or expired.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_played_at = models.DateTimeField(
        null=True, blank=True, help_text="When this audio was last played."
    )
    deleted_at = models.DateTimeField(
        null=True, blank=True, help_text="When this audio was deleted (soft delete)."
    )
    error_message = models.TextField(
        blank=True, null=True, help_text="Any error message from audio generation."
    )

    class Meta:
        ordering = ["-created_at"]
        # Ensure unique voices per page (for active audios only)
        constraints = [
            models.UniqueConstraint(
                fields=["page", "voice"],
                condition=models.Q(lifetime_status=AudioLifetimeStatus.ACTIVE),
                name="unique_voice_per_page",
            )
        ]

    def clean(self):
        """Validate business rules."""
        # Check lifetime quota (max 4 audios ever created for this page)
        from speech_processing.models import SiteSettings

        settings_obj = SiteSettings.get_settings()
        max_audios = settings_obj.max_audios_per_page

        total_audios_count = Audio.objects.filter(page=self.page).count()
        if not self.pk:  # New audio being created
            if total_audios_count >= max_audios:
                raise ValidationError(
                    f"Maximum {max_audios} audios per page allowed (lifetime)."
                )

        # Check active audios and voice uniqueness
        if self.lifetime_status == AudioLifetimeStatus.ACTIVE:
            # Check for voice uniqueness (already handled by constraint, but good for explicit validation)
            existing_voice = (
                Audio.objects.filter(
                    page=self.page,
                    voice=self.voice,
                    lifetime_status=AudioLifetimeStatus.ACTIVE,
                )
                .exclude(pk=self.pk)
                .exists()
            )

            if existing_voice:
                raise ValidationError(
                    f"Voice {self.voice} is already used for this page."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.voice} audio for {self.page} by {self.generated_by.email}"

    def is_expired(self):
        """Check if audio should be expired (not played for 6 months)."""
        from speech_processing.models import SiteSettings

        settings_obj = SiteSettings.get_settings()
        retention_days = settings_obj.audio_retention_months * 30

        if not self.last_played_at:
            # If never played, check if created more than retention period ago
            return self.created_at < timezone.now() - timedelta(days=retention_days)
        return self.last_played_at < timezone.now() - timedelta(days=retention_days)

    def days_until_expiry(self):
        """Calculate days until expiry."""
        from speech_processing.models import SiteSettings

        settings_obj = SiteSettings.get_settings()
        retention_days = settings_obj.audio_retention_months * 30

        reference_date = self.last_played_at or self.created_at
        expiry_date = reference_date + timedelta(days=retention_days)
        days_left = (expiry_date - timezone.now()).days
        return max(0, days_left)

    def needs_expiry_warning(self):
        """Check if audio needs expiry warning (30 days before expiry)."""
        days_left = self.days_until_expiry()
        return 0 < days_left <= 30

    def get_expiry_date(self):
        """Get the exact expiry date for this audio."""
        from speech_processing.models import SiteSettings

        settings_obj = SiteSettings.get_settings()
        retention_days = settings_obj.audio_retention_months * 30

        reference_date = self.last_played_at or self.created_at
        return reference_date + timedelta(days=retention_days)

    def get_s3_url(self):
        """Get the full S3 URL for this audio file."""
        if self.s3_key:
            return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{self.s3_key}"
        return None


class DocumentSharing(models.Model):
    """
    Represents sharing permissions for a document.
    """

    document = models.ForeignKey(
        "document_processing.Document",
        on_delete=models.CASCADE,
        related_name="shares",
        help_text="The document being shared.",
    )
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_documents",
        help_text="The user the document is shared with.",
    )
    permission = models.CharField(
        max_length=20,
        choices=SharingPermission.choices,
        default=SharingPermission.VIEW_ONLY,
        help_text="The permission level for the shared user.",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents_shared_by_me",
        help_text="The user who shared this document.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("document", "shared_with")
        verbose_name_plural = "Document Sharings"

    def __str__(self):
        return f"{self.document.title} shared with {self.shared_with.email} ({self.permission})"

    def can_generate_audio(self):
        """Check if this user can generate audio based on their permission."""
        return self.permission in [
            SharingPermission.COLLABORATOR,
            SharingPermission.CAN_SHARE,
        ]

    def can_share(self):
        """Check if this user can share the document with others."""
        return self.permission == SharingPermission.CAN_SHARE


class AudioAccessLog(models.Model):
    """
    Logs all audio-related actions for audit purposes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="audio_logs",
        help_text="The user who performed the action.",
    )
    audio = models.ForeignKey(
        Audio,
        on_delete=models.CASCADE,
        related_name="access_logs",
        null=True,
        blank=True,
        help_text="The audio involved in the action (if applicable).",
    )
    document = models.ForeignKey(
        "document_processing.Document",
        on_delete=models.CASCADE,
        related_name="audio_logs",
        null=True,
        blank=True,
        help_text="The document involved in the action (for sharing actions).",
    )
    action = models.CharField(
        max_length=20, choices=AudioAction.choices, help_text="The action performed."
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=AudioGenerationStatus.choices,
        default=AudioGenerationStatus.COMPLETED,
        help_text="Whether the action succeeded or failed.",
    )
    error_message = models.TextField(
        blank=True, null=True, help_text="Error message if action failed."
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, help_text="IP address of the user."
    )
    user_agent = models.TextField(blank=True, null=True, help_text="User agent string.")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.user.email} {self.action} at {self.timestamp}"


class SiteSettings(models.Model):
    """
    Global site settings for audio generation and management.
    Singleton model - only one instance should exist.
    """

    audio_generation_enabled = models.BooleanField(
        default=True, help_text="Whether audio generation is globally enabled."
    )
    audio_retention_months = models.PositiveIntegerField(
        default=6,
        help_text="Number of months to keep unused audio files before expiry.",
    )
    expiry_warning_days = models.PositiveIntegerField(
        default=30, help_text="Number of days before expiry to warn users."
    )
    admin_notification_email = models.EmailField(
        blank=True, null=True, help_text="Email address for admin notifications."
    )
    enable_email_notifications = models.BooleanField(
        default=True, help_text="Whether to send email notifications to users."
    )
    enable_in_app_notifications = models.BooleanField(
        default=True, help_text="Whether to show in-app notifications to users."
    )
    max_audios_per_page = models.PositiveIntegerField(
        default=4, help_text="Maximum number of audios allowed per page (lifetime)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Site Settings"

    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SiteSettings.objects.exists():
            raise ValidationError("Only one SiteSettings instance is allowed.")
        super().save(*args, **kwargs)

    def __str__(self):
        return "Site Settings"

    @classmethod
    def get_settings(cls):
        """Get the site settings instance, creating if it doesn't exist."""
        settings_obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                "audio_generation_enabled": True,
                "audio_retention_months": 6,
                "expiry_warning_days": 30,
                "enable_email_notifications": True,
                "enable_in_app_notifications": True,
                "max_audios_per_page": 4,
            },
        )
        return settings_obj
