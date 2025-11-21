from django.urls import path
from . import views

app_name = "document_processing"

urlpatterns = [
    path("", views.document_list_view, name="document_list"),
    path("upload/", views.document_upload, name="document_upload"),
    path("docs/<int:pk>/", views.document_detail, name="document_detail"),
    path(
        "docs/<int:pk>/retry/", views.retry_document_processing, name="document_retry"
    ),
    path("docs/<int:doc_id>/pages/<int:page>/", views.page_detail, name="page_detail"),
    path("pages/<int:page_id>/edit/", views.page_edit, name="page_edit"),
    path("pages/render-markdown/", views.render_markdown, name="render_markdown"),
    path("api/docs/<int:pk>/status/", views.document_status_api, name="status_api"),
    path("shared-with-me/", views.shared_with_me_view, name="shared_with_me"),
    path("<int:pk>/delete/", views.document_delete, name="document_delete"),
    path(
        "docs/<int:doc_id>/add-page/", views.add_document_page, name="add_document_page"
    ),
]
