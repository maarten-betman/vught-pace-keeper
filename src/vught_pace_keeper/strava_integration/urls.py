"""URL configuration for Strava integration."""

from django.urls import path

from . import views

app_name = "strava"

urlpatterns = [
    path("sync/", views.sync_activities, name="sync"),
    path("status/", views.sync_status, name="status"),
]
