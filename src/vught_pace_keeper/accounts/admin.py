from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import StravaToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "strava_athlete_id",
        "is_staff",
    ]
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Strava Integration",
            {
                "fields": (
                    "strava_athlete_id",
                    "strava_profile_picture_url",
                    "preferred_distance_unit",
                    "date_of_birth",
                )
            },
        ),
    )


@admin.register(StravaToken)
class StravaTokenAdmin(admin.ModelAdmin):
    """Admin configuration for Strava tokens."""

    list_display = ["user", "expires_at", "scope", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]
