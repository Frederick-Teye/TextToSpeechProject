from django.contrib import admin, messages
from .models import Document, DocumentPage, TextStatus
from .tasks import parse_document_task


# Inline for displaying DocumentPage within Document admin
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


# Admin action for reprocessing documents
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
        doc.pages.all().delete()
        doc.save()

        parse_document_task.delay(doc.id)
        requeued_count += 1

    if requeued_count:
        modeladmin.message_user(
            request,
            f"Successfully re-queued {requeued_count} documents for processing.",
            messages.SUCCESS,
        )

    if skipped_count:
        modeladmin.message_user(
            request,
            f"Skipped {skipped_count} documents that were already pending or processing.",
            messages.WARNING,
        )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "status", "created_at", "updated_at")
    list_filter = ("status", "source_type", "user")
    search_fields = ("title", "user__email", "source_content")
    readonly_fields = ("source_content", "error_message", "created_at", "updated_at")
    inlines = [DocumentPageInline]
    actions = [reprocess_documents]


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
