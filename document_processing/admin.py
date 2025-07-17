import csv
import os  # Import os to build the log file path
from django.conf import settings  # Import settings to find the log file
from django.contrib import admin, messages
from django.http import HttpResponse, FileResponse
from .models import Document, DocumentPage, TextStatus
from .tasks import parse_document_task


# 1. Inline to show pages on the Document admin page (This is a key feature)
class DocumentPageInline(admin.TabularInline):
    model = DocumentPage
    readonly_fields = (
        "page_number",
        "markdown_content",
        "audio_status",
        "audio_file_s3_url",
        "created_at",
        "updated_at",
    )
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# 2. Admin action to re-queue documents (Our refined, robust version)
@admin.action(description="Re-queue selected documents for processing")
def reprocess_documents(modeladmin, request, queryset):
    requeued_count = 0
    skipped_count = 0
    for doc in queryset:
        if doc.status in [TextStatus.PENDING, TextStatus.PROCESSING]:
            skipped_count += 1
            continue
        doc.status = TextStatus.PENDING
        doc.error_message = None
        doc.pages.all().delete()  # Essential: Clear out old pages before reprocessing
        doc.save()
        parse_document_task.delay(doc.id)
        requeued_count += 1
    if requeued_count:
        modeladmin.message_user(
            request,
            f"Successfully re-queued {requeued_count} documents.",
            messages.SUCCESS,
        )
    if skipped_count:
        modeladmin.message_user(
            request,
            f"Skipped {skipped_count} documents that were already in progress.",
            messages.WARNING,
        )


# 3. Admin action to export data (Your excellent new feature!)
@admin.action(description="Export selected documents to CSV")
def export_as_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    # We select which fields to export for clarity
    field_names = [
        "id",
        "title",
        "user",
        "status",
        "source_type",
        "source_content",
        "created_at",
    ]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f"attachment; filename={meta.model_name}_export.csv"
    )
    writer = csv.writer(response)
    writer.writerow(field_names)
    for obj in queryset:
        writer.writerow([getattr(obj, field) for field in field_names])
    return response


# 4. NEW: Admin action to export the application log file
@admin.action(description="Export application log file")
def export_logs(modeladmin, request, queryset):
    """
    Finds the log file defined in settings and serves it for download.
    Note: This action doesn't use the queryset, it's a global action.
    """
    try:
        # Construct the log file path based on the LOGGING setting
        log_file_path = settings.LOGGING["handlers"]["file"]["filename"]
        if os.path.exists(log_file_path):
            # Use FileResponse for efficiently serving large files
            return FileResponse(
                open(log_file_path, "rb"),
                as_attachment=True,
                filename="application.log",
            )
        else:
            modeladmin.message_user(request, "Log file not found.", messages.ERROR)
            return HttpResponse(status=404)
    except (KeyError, AttributeError):
        modeladmin.message_user(
            request,
            "LOGGING setting is not configured correctly to find the file handler.",
            messages.ERROR,
        )
        return HttpResponse(status=500)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "status", "source_type", "created_at")
    list_filter = ("status", "source_type", "user")
    search_fields = ("title", "user__email", "source_content")
    readonly_fields = ("created_at", "updated_at")
    inlines = [DocumentPageInline]
    # We combine all our powerful actions
    actions = [reprocess_documents, export_as_csv, export_logs]

    # 5. Use your fieldsets idea to organize the form (using our correct field names)
    fieldsets = (
        (None, {"fields": ("title", "user", "status", "source_type")}),
        (
            "Source & Error Details",
            {
                "classes": ("collapse",),  # This makes the section collapsible
                "fields": (
                    "source_content",
                    "error_message",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


@admin.register(DocumentPage)
class DocumentPageAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number", "audio_status")
    list_filter = ("audio_status", "document__user")
    search_fields = ("document__title",)
    readonly_fields = (
        "document",
        "page_number",
        "markdown_content",
        "audio_file_s3_url",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
