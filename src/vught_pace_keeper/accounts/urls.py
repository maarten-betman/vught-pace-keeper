"""URL configuration for the accounts app."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
