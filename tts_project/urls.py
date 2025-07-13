"""
URL configuration for tts_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path  # Import re_path
from django.conf import settings
from django.conf.urls.static import static
from core.views import (
    CustomPasswordResetFromKeyView,
)  # Ensure this import path is correct

urlpatterns = [
    path("admin/", admin.site.urls),
    # CRITICAL FIX: Place your custom password reset URL BEFORE allauth.urls
    # This ensures your custom view is hit first for this specific pattern.
    re_path(  # Use re_path for more precise regex matching
        r"^accounts/password/reset/key/(?P<uidb36>[^/]+)-(?P<key>[^/]+)/$",
        CustomPasswordResetFromKeyView.as_view(),
        name="account_reset_password_from_key",
    ),
    path(
        "accounts/", include("allauth.urls")
    ),  # Django-allauth URLs (now comes after your override)
    # Add your app URLs here as you create them:
    path("", include("core.urls")),
    # path('documents/', include('document_processing.urls')),
    # path('audio/', include('audio_playback.urls')),
]

if settings.DEBUG:
    # Serve static and media files locally only in development mode
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Optional: Django Debug Toolbar URLs (uncomment if you install debug_toolbar)
    # import debug_toolbar
    # urlpatterns = [
    #     path('__debug__/', include(debug_toolbar.urls)),
    # ] + urlpatterns
