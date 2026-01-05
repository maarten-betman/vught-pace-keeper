"""URL patterns for training app."""

from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    # Plan CRUD
    path("plans/", views.plan_list, name="plan_list"),
    path("plans/create/", views.plan_create_wizard, name="plan_create"),
    path("plans/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:pk>/copy/", views.plan_copy, name="plan_copy"),
    # Scheduled workout editing (HTMX partials)
    path("scheduled/<int:pk>/", views.workout_detail, name="scheduled_workout_detail"),
    path("scheduled/<int:pk>/edit/", views.workout_edit, name="scheduled_workout_edit"),
    path("scheduled/<int:pk>/update/", views.workout_update, name="scheduled_workout_update"),
    # Workout log (completed workouts)
    path("log/", views.workout_log_list, name="workout_log_list"),
    path("log/<int:pk>/", views.workout_log_detail, name="workout_log_detail"),
    path("log/<int:pk>/streams/", views.workout_stream_data, name="workout_streams"),
    path("log/<int:pk>/delete/", views.workout_log_delete, name="workout_log_delete"),
    path("log/manual/", views.workout_log_manual, name="workout_log_manual"),
    path("log/manual/<int:scheduled_workout_pk>/", views.workout_log_manual, name="workout_log_manual_for_scheduled"),
    path("log/gpx/", views.workout_log_gpx, name="workout_log_gpx"),
    path("log/gpx/<int:scheduled_workout_pk>/", views.workout_log_gpx, name="workout_log_gpx_for_scheduled"),
    path("log/gpx-preview/", views.gpx_preview, name="gpx_preview"),
    # Pace zones
    path("zones/", views.pace_zone_list, name="pace_zone_list"),
    path("zones/calculator/", views.pace_zone_calculator, name="pace_zone_calculator"),
    path("zones/save/", views.pace_zone_save, name="pace_zone_save"),
    path("zones/<int:pk>/edit/", views.pace_zone_override, name="pace_zone_override"),
    # Analytics
    path("analytics/", views.analytics_dashboard, name="analytics_dashboard"),
    path(
        "analytics/weekly-summary/",
        views.analytics_weekly_summary,
        name="analytics_weekly_summary",
    ),
]
