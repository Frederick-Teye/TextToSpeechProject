import logging
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import JsonResponse
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext as _
from django_ratelimit.decorators import ratelimit
import markdown as md
import nh3

from core.decorators import (
    document_access_required,
    page_access_required,
    owner_required,
)
from .forms import DocumentUploadForm
from .models import SourceType, TextStatus, Document, DocumentPage
from .utils import upload_to_s3, validate_markdown, sanitize_markdown
from .tasks import parse_document_task
from speech_processing.models import DocumentSharing

logger = logging.getLogger(__name__)


class DocumentListView(LoginRequiredMixin, ListView):
    """
    A view to display a list of documents uploaded by the current user.

    Optimized with prefetch_related to prevent N+1 queries:
    - Fetches all pages for each document in one query
    - Fetches all shares for each document in one query
    - Reduces database queries from 1 + N + N to just 3 queries
    """

    model = Document
    template_name = "document_processing/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        """
        Returns only documents belonging to current user with optimized queries.

        This queryset uses:
        - prefetch_related('pages'): Fetch all pages in one query
        - prefetch_related('shares'): Fetch all shares in one query
        - annotate(page_count=...): Add computed field for template

        Example query reduction:
        BEFORE: 1 query for documents + 100 queries for pages + 100 queries for shares
        AFTER: 3 queries total (documents + pages + shares)
        """
        # Create prefetch for pages (will be fetched in second query)
        pages_prefetch = Prefetch(
            "pages",
            DocumentPage.objects.select_related("document").prefetch_related("audios"),
        )

        return (
            Document.objects.filter(user=self.request.user)
            .prefetch_related(pages_prefetch)
            .prefetch_related("shares")  # Fetch all document shares
            .annotate(page_count=Count("pages"))  # Add page count for template
            .order_by("-created_at")
        )


document_list_view = DocumentListView.as_view()


@login_required
@ratelimit(
    key="user",  # Rate limit per user
    rate=f"{settings.RATE_LIMIT_UPLOADS_PER_HOUR}/h",  # uploads per hour
    method="POST",  # Only rate limit POST requests
    block=False,  # Don't block, let us handle the response
)
@transaction.atomic
def document_upload(request):
    """
    Handle uploads of new documents from FILE, URL, or TEXT sources.

    Rate limiting:
    - Maximum 10 document uploads per hour per user
    - Prevents DoS attacks and excessive server load
    - Returns 429 Too Many Requests if limit exceeded

    Uses @transaction.atomic to ensure DB consistency.
    """
    # Check if user has exceeded rate limit
    if getattr(request, "limited", False):
        logger.warning(
            f"Rate limit exceeded for user {request.user.id} on document upload"
        )
        messages.error(
            request,
            _(
                f"You have exceeded the maximum number of uploads allowed ({settings.RATE_LIMIT_UPLOADS_PER_HOUR} per hour). "
                "Please try again later."
            ),
        )
        return JsonResponse(
            {
                "success": False,
                "error": _(
                    f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_UPLOADS_PER_HOUR} uploads per hour."
                ),
            },
            status=429,
        )

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
                    request,
                    _("Your document has been submitted and is now processing."),
                )
                return redirect("document_processing:document_detail", pk=document.id)

            except Exception as e:
                logger.exception("Failed during document upload process.")
                messages.error(
                    request,
                    _(
                        "An unexpected error occurred during the upload. Please try again."
                    ),
                )
                # No manual cleanup needed due to @transaction.atomic

        else:
            messages.error(request, _("Please correct the errors below."))

    else:
        form = DocumentUploadForm()

    return render(request, "document_processing/document_upload.html", {"form": form})


@login_required
@document_access_required(param_name="pk", permission_level="view")
def document_detail(request, pk, document):
    """
    Display a document with all its pages.

    Args:
        request: HTTP request
        pk: Document ID
        document: Document object (injected by decorator)

    Returns:
        Rendered document detail page
    """
    # Check if user can share (owner or has CAN_SHARE permission)
    sharing = DocumentSharing.objects.filter(
        document=document, shared_with=request.user
    ).first()
    can_share = document.user == request.user or (sharing and sharing.can_share())

    pages = []
    if document.status == TextStatus.COMPLETED:
        pages = document.pages.all()
    return render(
        request,
        "document_processing/document_detail.html",
        {"document": document, "pages": pages, "can_share": can_share},
    )


@login_required
@page_access_required(doc_param="doc_id", page_param="page", permission_level="view")
def page_detail(request, doc_id, page, page_obj):
    """
    Display a single page with navigation controls.

    Args:
        request: HTTP request
        doc_id: Document ID
        page: Page number
        page_obj: DocumentPage object (injected by decorator)

    Returns:
        Rendered page detail view
    """
    # Check if user can edit (owner or has CAN_SHARE permission)
    is_owner = request.user == page_obj.document.user
    shared_access = DocumentSharing.objects.filter(
        document=page_obj.document, shared_with=request.user
    ).first()
    can_user_edit = is_owner or (shared_access and shared_access.can_share())

    # Calculate pagination
    total_pages = page_obj.document.pages.count()

    # Build URLs for previous and next pages
    previous_page_url = None
    next_page_url = None

    if page > 1:
        previous_page_url = f"/documents/docs/{doc_id}/pages/{page - 1}/"

    if page < total_pages:
        next_page_url = f"/documents/docs/{doc_id}/pages/{page + 1}/"

    context = {
        "page": page_obj,
        "total_pages": total_pages,
        "previous_page_url": previous_page_url,
        "next_page_url": next_page_url,
        "can_edit": can_user_edit,
    }

    return render(request, "document_processing/page_detail.html", context)


@login_required
@owner_required(doc_param="pk")
def document_status_api(request, pk):
    """
    Returns the document's current processing status in JSON format.
    Used for front-end polling (e.g., AJAX).

    Args:
        request: HTTP request
        pk: Document ID

    Returns:
        JSON response with document status and error message (if any)
    """
    doc = get_object_or_404(Document, pk=pk)
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
            {"success": False, "message": _("Invalid request method")}, status=405
        )

    doc = get_object_or_404(Document, pk=pk)

    # Permission check
    if request.user != doc.user:
        return JsonResponse(
            {"success": False, "message": _("Permission denied")}, status=403
        )

    # Get the confirmed title from request
    import json

    try:
        data = json.loads(request.body)
        confirmed_title = data.get("title", "").strip()
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": _("Invalid JSON data")}, status=400
        )

    # Verify title matches
    if confirmed_title != doc.title:
        return JsonResponse(
            {"success": False, "message": _("Document title does not match")},
            status=400,
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


@login_required
def page_edit(request, page_id):
    """
    API endpoint to update a page's markdown content.
    Owner or users with CAN_SHARE permission can edit.

    Security features:
    - Validates markdown content to prevent injection attacks
    - Sanitizes markdown input (removes dangerous patterns)
    - Sanitizes HTML output with nh3
    - Validates user permissions
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Invalid request method"}, status=405
        )

    page_obj = get_object_or_404(DocumentPage, id=page_id)

    # Check if user is the document owner or has CAN_SHARE permission
    is_owner = request.user == page_obj.document.user
    shared_access = DocumentSharing.objects.filter(
        document=page_obj.document, shared_with=request.user
    ).first()
    can_user_edit = is_owner or (shared_access and shared_access.can_share())

    if not can_user_edit:
        return JsonResponse(
            {"success": False, "error": "Permission denied"}, status=403
        )

    try:
        data = json.loads(request.body)
        markdown_content = data.get("markdown_content", "").strip()

        if not markdown_content:
            return JsonResponse(
                {"success": False, "error": "Content cannot be empty"}, status=400
            )

        # Validate markdown for dangerous patterns
        is_valid, error_msg = validate_markdown(markdown_content)
        if not is_valid:
            logger.warning(
                f"User {request.user.id} attempted to save invalid markdown: {error_msg}"
            )
            return JsonResponse(
                {"success": False, "error": "Content contains invalid patterns"},
                status=400,
            )

        # Sanitize markdown content
        try:
            markdown_content = sanitize_markdown(markdown_content)
        except ValueError as e:
            logger.warning(f"Markdown sanitization failed: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "Content validation failed"}, status=400
            )

        # Additional HTML sanitization with nh3
        markdown_content = nh3.clean(markdown_content)

        # Update the page content
        page_obj.markdown_content = markdown_content
        page_obj.save()

        # Convert markdown to HTML for preview
        html = md.markdown(
            markdown_content,
            extensions=[
                "fenced_code",
                "codehilite",
                "tables",
                "toc",
            ],
            output_format="html5",
        )

        # Sanitize HTML output with nh3
        html = nh3.clean(html)

        logger.info(
            f"Page {page_obj.page_number} of document '{page_obj.document.title}' "
            f"updated by user {request.user.id}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Page updated successfully",
                "html": html,
                "page_id": page_obj.id,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.exception(f"Failed to update page {page_id}")
        return JsonResponse(
            {"success": False, "error": "An error occurred while updating the page"},
            status=500,
        )


@login_required
def render_markdown(request):
    """
    API endpoint to render markdown to HTML.
    Used for live preview in the page edit modal.

    Security features:
    - Validates markdown content to prevent injection attacks
    - Sanitizes HTML output with nh3
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Invalid request method"}, status=405
        )

    try:
        data = json.loads(request.body)
        markdown_content = data.get("markdown", "").strip()

        if not markdown_content:
            return JsonResponse(
                {
                    "success": True,
                    "html": "<p class='text-white-50'>Preview will appear here...</p>",
                }
            )

        # Validate markdown for dangerous patterns
        is_valid, error_msg = validate_markdown(markdown_content)
        if not is_valid:
            logger.warning(
                f"User {request.user.id} attempted to render invalid markdown: {error_msg}"
            )
            return JsonResponse(
                {"success": False, "error": "Content contains invalid patterns"},
                status=400,
            )

        # Convert markdown to HTML
        html = md.markdown(
            markdown_content,
            extensions=[
                "fenced_code",
                "codehilite",
                "tables",
                "toc",
            ],
            output_format="html5",
        )

        # Sanitize HTML output with nh3
        html = nh3.clean(html)

        return JsonResponse(
            {
                "success": True,
                "html": html,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.exception("Failed to render markdown")
        return JsonResponse(
            {"success": False, "error": "An error occurred while rendering markdown"},
            status=500,
        )
