from django.urls import path
from . import views  # Import views from the current app

urlpatterns = [
    path("", views.home, name="home"),  # Add this line
    path("about/", views.about, name="about"),
]
