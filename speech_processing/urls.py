from django.urls import path
from . import views

app_name = "speech_processing"

urlpatterns = [
    # Audio generation
    path("generate/<int:page_id>/", views.generate_audio, name="generate_audio"),
    # Audio management
    path("audio/<int:audio_id>/status/", views.audio_status, name="audio_status"),
    path("audio/<int:audio_id>/download/", views.download_audio, name="download_audio"),
    path("audio/<int:audio_id>/play/", views.play_audio, name="play_audio"),
    path("audio/<int:audio_id>/delete/", views.delete_audio, name="delete_audio"),
    # Page audios list
    path("page/<int:page_id>/audios/", views.page_audios, name="page_audios"),
    # Sharing and permissions
    path("share/<int:document_id>/", views.share_document, name="share_document"),
    path("unshare/<int:sharing_id>/", views.unshare_document, name="unshare_document"),
    path(
        "document/<int:document_id>/shares/",
        views.document_shares,
        name="document_shares",
    ),
    path("shared-with-me/", views.shared_with_me, name="shared_with_me"),
    path(
        "share/<int:sharing_id>/permission/",
        views.update_share_permission,
        name="update_share_permission",
    ),
]
