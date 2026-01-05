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
    # Calendar
    path("calendar/", views.training_calendar, name="calendar"),
    path("calendar/day/<str:date_str>/", views.calendar_day_detail, name="calendar_day"),
    # Training Load
    path("load/", views.training_load_dashboard, name="load_dashboard"),
    path("load/settings/", views.fitness_settings, name="fitness_settings"),
    path("load/backfill/", views.backfill_training_load, name="backfill_load"),
    path("load/chart-data/", views.training_load_chart_data, name="load_chart_data"),
    # Personal Records
    path("records/", views.personal_records_list, name="records_list"),
    path("records/add/", views.personal_record_add, name="record_add"),
    path("records/<int:pk>/delete/", views.personal_record_delete, name="record_delete"),
    # Goals
    path("goals/", views.goal_list, name="goal_list"),
    path("goals/create/", views.goal_create, name="goal_create"),
    path("goals/<int:pk>/", views.goal_edit, name="goal_edit"),
    path("goals/<int:pk>/delete/", views.goal_delete, name="goal_delete"),
    path("goals/<int:pk>/abandon/", views.goal_abandon, name="goal_abandon"),
]
