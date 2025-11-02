from django.contrib import admin
from .models import Audio, DocumentSharing, AudioAccessLog, SiteSettings, AdminAuditLog


@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    list_display = (
        "voice",
        "page",
        "generated_by",
        "status",
        "lifetime_status",
        "created_at",
        "last_played_at",
    )
    list_filter = ("status", "lifetime_status", "voice", "created_at")
    search_fields = ("page__document__title", "generated_by__email", "voice")
    readonly_fields = ("created_at", "last_played_at", "deleted_at")
    fieldsets = (
        ("Audio Information", {"fields": ("page", "voice", "generated_by", "s3_key")}),
        ("Status", {"fields": ("status", "lifetime_status", "error_message")}),
        ("Timestamps", {"fields": ("created_at", "last_played_at", "deleted_at")}),
    )


@admin.register(DocumentSharing)
class DocumentSharingAdmin(admin.ModelAdmin):
    list_display = ("document", "shared_with", "permission", "shared_by", "created_at")
    list_filter = ("permission", "created_at")
    search_fields = ("document__title", "shared_with__email", "shared_by__email")
    readonly_fields = ("created_at",)


@admin.register(AudioAccessLog)
class AudioAccessLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "audio", "document", "status", "timestamp")
    list_filter = ("action", "status", "timestamp")
    search_fields = ("user__email", "audio__voice", "document__title")
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "audio_generation_enabled",
        "max_audios_per_page",
        "audio_retention_months",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        # Only allow one instance
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "ip_address", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = ("user__email", "description", "ip_address")
    readonly_fields = (
        "timestamp",
        "user",
        "action",
        "description",
        "ip_address",
        "user_agent",
        "changes",
    )
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        # Audit logs should only be created programmatically
        return False

    def has_delete_permission(self, request, obj=None):
        # Audit logs should not be deleted
        return False
