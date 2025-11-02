"""
View decorators for common permission and access control patterns.

This module provides reusable decorators to:
- Check ownership of documents
- Verify sharing access with different permission levels
- Enforce editing permissions
- Handle permission denied scenarios consistently
"""

from functools import wraps
from typing import Callable, Optional, Any, Dict
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, Http404
from django.shortcuts import get_object_or_404


def document_access_required(
    param_name: str = 'pk',
    permission_level: str = 'view'
) -> Callable:
    """
    Decorator to check document access (ownership or sharing).

    This decorator checks if the current user has access to a document.
    It supports different permission levels:
    - 'view': User can view the document (owner or any sharing permission)
    - 'edit': User can edit the document (owner or CAN_SHARE permission)
    - 'own': User must be the owner

    The document is passed to the view as a 'document' kwarg.

    Args:
        param_name: URL parameter name containing the document ID (default: 'pk')
        permission_level: Required permission level - 'view', 'edit', or 'own'

    Returns:
        Decorated view function

    Raises:
        PermissionDenied: If user doesn't have required access
        Http404: If document not found

    Example:
        @login_required
        @document_access_required(permission_level='edit')
        def edit_document(request, pk, document):
            # 'document' is automatically injected by decorator
            return render(request, 'edit.html', {'document': document})
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> Any:
            from document_processing.models import Document
            from speech_processing.models import DocumentSharing

            # Get document ID from URL parameters
            doc_id = kwargs.get(param_name)
            if not doc_id:
                raise Http404("Document ID not provided")

            # Fetch document or 404
            document = get_object_or_404(Document, pk=doc_id)

            # Check ownership
            is_owner = document.user == request.user

            # Check sharing access
            sharing = DocumentSharing.objects.filter(
                document=document,
                shared_with=request.user
            ).first()

            # Validate permission level
            if permission_level == 'own':
                # Must be owner
                if not is_owner:
                    raise PermissionDenied("You don't have permission to access this document.")

            elif permission_level == 'edit':
                # Must be owner or have CAN_SHARE permission
                can_edit = is_owner or (sharing and sharing.can_share())
                if not can_edit:
                    raise PermissionDenied("You don't have permission to edit this document.")

            elif permission_level == 'view':
                # Must be owner or have any sharing permission
                has_access = is_owner or sharing is not None
                if not has_access:
                    raise PermissionDenied("You don't have permission to access this document.")

            else:
                raise ValueError(f"Invalid permission level: {permission_level}")

            # Inject document into kwargs and call view
            kwargs['document'] = document
            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def page_access_required(
    doc_param: str = 'doc_id',
    page_param: str = 'page',
    permission_level: str = 'view'
) -> Callable:
    """
    Decorator to check page access (via document ownership/sharing).

    This decorator checks if the current user has access to a specific page.
    Access is determined by the parent document's sharing permissions.

    The page is passed to the view as a 'page' kwarg.

    Args:
        doc_param: URL parameter name containing the document ID
        page_param: URL parameter name containing the page number
        permission_level: Required permission level - 'view' or 'edit'

    Returns:
        Decorated view function

    Raises:
        PermissionDenied: If user doesn't have required access to document
        Http404: If page not found

    Example:
        @login_required
        @page_access_required(permission_level='edit')
        def edit_page(request, doc_id, page, page_obj):
            # 'page_obj' is automatically injected by decorator
            return render(request, 'edit_page.html', {'page': page_obj})
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> Any:
            from document_processing.models import DocumentPage
            from speech_processing.models import DocumentSharing

            # Get page parameters
            doc_id = kwargs.get(doc_param)
            page_num = kwargs.get(page_param)

            if not doc_id or not page_num:
                raise Http404("Document ID or page number not provided")

            # Fetch page or 404
            page_obj = get_object_or_404(
                DocumentPage,
                document_id=doc_id,
                page_number=page_num
            )

            # Check ownership
            is_owner = request.user == page_obj.document.user

            # Check sharing access
            sharing = DocumentSharing.objects.filter(
                document=page_obj.document,
                shared_with=request.user
            ).first()

            # Validate permission level
            if permission_level == 'edit':
                # Must be owner or have CAN_SHARE permission
                can_edit = is_owner or (sharing and sharing.can_share())
                if not can_edit:
                    raise PermissionDenied("You don't have permission to edit this page.")

            elif permission_level == 'view':
                # Must be owner or have any sharing permission
                has_access = is_owner or sharing is not None
                if not has_access:
                    raise PermissionDenied("You don't have permission to view this page.")

            else:
                raise ValueError(f"Invalid permission level: {permission_level}")

            # Inject page into kwargs and call view
            kwargs['page_obj'] = page_obj
            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def audio_generation_allowed(
    page_param: str = 'page_id',
) -> Callable:
    """
    Decorator to check if audio generation is allowed for a page.

    This decorator verifies that the user has permission to generate
    audio for a specific page (based on document access).

    Args:
        page_param: URL parameter name containing the page ID

    Returns:
        Decorated view function

    Raises:
        PermissionDenied: If user doesn't have generation permission
        Http404: If page not found

    Example:
        @login_required
        @audio_generation_allowed()
        def generate_audio_view(request, page_id):
            # Generate audio for the page
            pass
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> Any:
            from document_processing.models import DocumentPage
            from speech_processing.models import DocumentSharing

            # Get page ID
            page_id = kwargs.get(page_param)
            if not page_id:
                raise Http404("Page ID not provided")

            # Fetch page or 404
            page_obj = get_object_or_404(DocumentPage, pk=page_id)

            # Check ownership
            is_owner = request.user == page_obj.document.user

            # Check sharing access with generation permission
            sharing = DocumentSharing.objects.filter(
                document=page_obj.document,
                shared_with=request.user
            ).first()

            # Can generate if owner or has COLLABORATOR/CAN_SHARE permission
            can_generate = is_owner or (sharing and sharing.can_generate_audio())

            if not can_generate:
                raise PermissionDenied(
                    "You don't have permission to generate audio for this page."
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def owner_required(doc_param: str = 'pk') -> Callable:
    """
    Decorator to require document ownership.

    Simpler variant that only allows the document owner.
    Useful for sensitive operations like document deletion.

    Args:
        doc_param: URL parameter name containing the document ID

    Returns:
        Decorated view function

    Raises:
        PermissionDenied: If user is not the owner
        Http404: If document not found

    Example:
        @login_required
        @owner_required()
        def delete_document(request, pk):
            document = get_object_or_404(Document, pk=pk)
            document.delete()
            return redirect('documents_list')
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> Any:
            from document_processing.models import Document

            doc_id = kwargs.get(doc_param)
            if not doc_id:
                raise Http404("Document ID not provided")

            document = get_object_or_404(Document, pk=doc_id)

            if document.user != request.user:
                raise PermissionDenied("Only the document owner can perform this action.")

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator
