from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    path(
        "update-voice-preference/",
        views.update_voice_preference,
        name="update_voice_preference",
    ),
]
