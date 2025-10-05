from django.urls import path
from . import views

app_name = "document_processing"

urlpatterns = [
    path("", views.document_list_view, name="document_list"),
    path("upload/", views.document_upload, name="upload"),
    path("docs/<int:pk>/", views.document_detail, name="document_detail"),
    path("docs/<int:doc_id>/pages/<int:page>/", views.page_detail, name="page_detail"),
    path("api/docs/<int:pk>/status/", views.document_status_api, name="status_api"),
    path("shared-with-me/", views.shared_with_me_view, name="shared_with_me"),
]
