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
]
