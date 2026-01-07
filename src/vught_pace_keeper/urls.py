"""
URL configuration for vught_pace_keeper project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Health checks (no auth required, accessed by load balancer)
    path("", include("vught_pace_keeper.core.urls")),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # Allauth URLs (login, logout, etc.)
    path("training/", include("vught_pace_keeper.training.urls")),  # Training plans
    path("strava/", include("vught_pace_keeper.strava_integration.urls")),  # Strava sync
    path("", include("vught_pace_keeper.accounts.urls")),  # Landing page, dashboard
]
