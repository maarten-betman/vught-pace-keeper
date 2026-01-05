from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import (
    CompletedWorkout,
    PaceZone,
    ScheduledWorkout,
    TrainingPlan,
    TrainingWeek,
)


@admin.register(PaceZone)
class PaceZoneAdmin(admin.ModelAdmin):
    """Admin configuration for pace zones."""

    list_display = [
        "user",
        "name",
        "min_pace_min_per_km",
        "max_pace_min_per_km",
        "color_hex",
    ]
    list_filter = ["name", "user"]
    search_fields = ["user__username", "description"]
    ordering = ["user", "min_pace_min_per_km"]
    readonly_fields = ["created_at", "updated_at"]


class TrainingWeekInline(admin.TabularInline):
    """Inline admin for training weeks within a plan."""

    model = TrainingWeek
    extra = 0
    fields = ["week_number", "focus", "total_distance_km", "notes"]


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    """Admin configuration for training plans."""

    list_display = [
        "name",
        "user",
        "plan_type",
        "methodology",
        "duration_weeks",
        "target_race_date",
        "is_template",
    ]
    list_filter = ["plan_type", "methodology", "is_template"]
    search_fields = ["name", "user__username", "description"]
    date_hierarchy = "created_at"
    inlines = [TrainingWeekInline]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        (None, {
            "fields": ["user", "name", "description"],
        }),
        ("Plan Configuration", {
            "fields": [
                "plan_type",
                "methodology",
                "duration_weeks",
                "is_template",
            ],
        }),
        ("Goals", {
            "fields": ["target_race_date", "goal_time"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]


class ScheduledWorkoutInline(admin.TabularInline):
    """Inline admin for scheduled workouts within a week."""

    model = ScheduledWorkout
    extra = 0
    fields = [
        "day_of_week",
        "workout_type",
        "target_distance_km",
        "target_duration",
        "target_pace_min_per_km",
        "order_in_day",
    ]


@admin.register(TrainingWeek)
class TrainingWeekAdmin(admin.ModelAdmin):
    """Admin configuration for training weeks."""

    list_display = ["plan", "week_number", "focus", "total_distance_km"]
    list_filter = ["focus", "plan__user"]
    search_fields = ["plan__name", "notes"]
    inlines = [ScheduledWorkoutInline]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ScheduledWorkout)
class ScheduledWorkoutAdmin(admin.ModelAdmin):
    """Admin configuration for scheduled workouts."""

    list_display = [
        "week",
        "day_of_week",
        "workout_type",
        "target_distance_km",
        "target_pace_min_per_km",
    ]
    list_filter = ["workout_type", "day_of_week", "week__focus"]
    search_fields = ["description", "week__plan__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CompletedWorkout)
class CompletedWorkoutAdmin(GISModelAdmin):
    """
    Admin configuration for completed workouts.

    Uses GISModelAdmin for map widget on route field.
    """

    list_display = [
        "user",
        "date",
        "actual_distance_km",
        "actual_duration",
        "average_pace_min_per_km",
        "source",
    ]
    list_filter = ["source", "date", "user"]
    search_fields = ["user__username", "notes"]
    date_hierarchy = "date"
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        (None, {
            "fields": ["user", "scheduled_workout", "date"],
        }),
        ("Performance Data", {
            "fields": [
                "actual_distance_km",
                "actual_duration",
                "average_pace_min_per_km",
                "average_heart_rate",
                "elevation_gain_m",
                "perceived_effort",
            ],
        }),
        ("GPS & Source", {
            "fields": ["route", "gpx_file", "source", "strava_activity_id"],
        }),
        ("Notes", {
            "fields": ["notes"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]
