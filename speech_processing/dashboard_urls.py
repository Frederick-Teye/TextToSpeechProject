"""
URL configuration for admin dashboard.
"""

from django.urls import path
from speech_processing import dashboard_views

app_name = "dashboard"

urlpatterns = [
    path("", dashboard_views.dashboard_home, name="home"),
    path("analytics/", dashboard_views.analytics_view, name="analytics"),
    path("analytics/data/", dashboard_views.analytics_data, name="analytics_data"),
    path("errors/", dashboard_views.error_monitoring, name="errors"),
    path("activity/", dashboard_views.user_activity, name="activity"),
    path("settings/", dashboard_views.settings_control, name="settings"),
]
