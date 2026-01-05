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
    # Workout editing (HTMX partials)
    path("workouts/<int:pk>/", views.workout_detail, name="workout_detail"),
    path("workouts/<int:pk>/edit/", views.workout_edit, name="workout_edit"),
    path("workouts/<int:pk>/update/", views.workout_update, name="workout_update"),
]
