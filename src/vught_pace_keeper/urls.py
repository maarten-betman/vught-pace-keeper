"""
URL configuration for vught_pace_keeper project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # Allauth URLs (login, logout, etc.)
    path("", include("vught_pace_keeper.accounts.urls")),  # Landing page, dashboard
]
