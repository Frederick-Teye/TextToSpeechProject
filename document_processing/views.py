import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin

from .forms import DocumentUploadForm
from .models import SourceType, TextStatus, Document, DocumentPage
from .utils import upload_to_s3
from .tasks import parse_document_task
from speech_processing.models import DocumentSharing

logger = logging.getLogger(__name__)


class DocumentListView(LoginRequiredMixin, ListView):
    """
    A view to display a list of documents uploaded by the current user.
    """

    model = Document
    template_name = "document_processing/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        """
        Overrides the default queryset to return only the documents
        belonging to the currently logged-in user, ordered by the
        most recently created.
        """
        return Document.objects.filter(user=self.request.user).order_by("-created_at")


document_list_view = DocumentListView.as_view()


@login_required
@transaction.atomic
def document_upload(request):
    """
    Handle uploads of new documents from FILE, URL, or TEXT sources.
    Uses @transaction.atomic to ensure DB consistency.
    """
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                # This is to avoid error when what the user uploads is not raw text
                raw_text = ""

                # Start building the document (but don’t save just yet)
                document = Document(
                    user=request.user,
                    title=form.cleaned_data["title"],
                    source_type=form.cleaned_data["source_type"],
                )
                stype = form.cleaned_data["source_type"]

                # Set source_content based on the selected source type
                if stype == SourceType.FILE:
                    uploaded_file = form.cleaned_data["file"]
                    document.save()  # Needed to get an ID for the upload path
                    s3_path = upload_to_s3(
                        uploaded_file, request.user.id, uploaded_file.name
                    )
                    document.source_content = s3_path

                elif stype == SourceType.URL:
                    document.source_content = form.cleaned_data["url"]

                elif stype == SourceType.TEXT:
                    if len(form.cleaned_data["text"]) > 1024:
                        document.source_content = form.cleaned_data["text"][:1024]
                    else:
                        document.source_content = form.cleaned_data["text"]
                    raw_text = form.cleaned_data["text"]

                # Final save after source_content is set
                document.save()

                # Schedule background parsing
                transaction.on_commit(
                    lambda: parse_document_task.delay(document.id, raw_text=raw_text)
                )

                messages.success(
                    request, "Your document has been submitted and is now processing."
                )
                return redirect("document_processing:document_detail", pk=document.id)

            except Exception as e:
                logger.exception("Failed during document upload process.")
                messages.error(
                    request,
                    "An unexpected error occurred during the upload. Please try again.",
                )
                # No manual cleanup needed due to @transaction.atomic

        else:
            messages.error(request, "Please correct the errors below.")

    else:
        form = DocumentUploadForm()

    return render(request, "document_processing/document_upload.html", {"form": form})


@login_required
def document_detail(request, pk):
    doc = get_object_or_404(Document, pk=pk)

    # Check if user has access
    has_access = (
        doc.user == request.user
        or DocumentSharing.objects.filter(
            document=doc, shared_with=request.user
        ).exists()
    )

    if not has_access:
        raise PermissionDenied
    pages = []
    if doc.status == TextStatus.COMPLETED:
        pages = doc.pages.all()
    return render(
        request,
        "document_processing/document_detail.html",
        {"document": doc, "pages": pages},
    )


@login_required
def page_detail(request, doc_id, page):
    page_obj = get_object_or_404(DocumentPage, document_id=doc_id, page_number=page)

    # Check if user has access
    has_access = (
        request.user != page_obj.document.user
        or DocumentSharing.objects.filter(
            document = page_obj.document,
            shared_with = request.user
        )
    )
    if not has_access:
        raise PermissionDenied
    return render(request, "document_processing/page_detail.html", {"page": page_obj})


@login_required
def document_status_api(request, pk):
    """
    Returns the document’s current processing status in JSON format.
    Used for front-end polling (e.g., AJAX).
    """
    doc = get_object_or_404(Document, pk=pk)
    if request.user != doc.user:
        raise PermissionDenied
    return JsonResponse(
        {
            "status": doc.get_status_display(),
            "error": doc.error_message,  # Optional: if you have an error_message field
        }
    )


@login_required
def shared_with_me_view(request):
    """
    Render the 'Shared with Me' page showing all documents shared with the user.
    """
    return render(request, "document_processing/shared_with_me.html")


@login_required
def document_delete(request, pk):
    """
    Delete a document after title confirmation.
    Only the document owner can delete it.
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Invalid request method"}, status=405
        )

    doc = get_object_or_404(Document, pk=pk)

    # Permission check
    if request.user != doc.user:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )

    # Get the confirmed title from request
    import json

    try:
        data = json.loads(request.body)
        confirmed_title = data.get("title", "").strip()
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data"}, status=400
        )

    # Verify title matches
    if confirmed_title != doc.title:
        return JsonResponse(
            {"success": False, "message": "Document title does not match"}, status=400
        )

    try:
        document_title = doc.title
        doc.delete()
        logger.info(
            f"Document '{document_title}' (ID: {pk}) deleted by user {request.user.id}"
        )
        return JsonResponse(
            {
                "success": True,
                "message": f'Document "{document_title}" has been successfully deleted',
            }
        )
    except Exception as e:
        logger.exception(f"Failed to delete document {pk}")
        return JsonResponse(
            {
                "success": False,
                "message": "An error occurred while deleting the document",
            },
            status=500,
        )
