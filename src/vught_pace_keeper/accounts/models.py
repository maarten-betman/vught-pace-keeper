from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from encrypted_fields.fields import EncryptedTextField

from vught_pace_keeper.core.models import TimestampedModel


class User(AbstractUser):
    """
    Custom user model with Strava integration fields.

    Using a custom user model from the start allows adding fields later
    without complex migrations.
    """

    strava_athlete_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        help_text="Strava athlete ID for quick lookups",
    )
    preferred_distance_unit = models.CharField(
        max_length=5,
        choices=[("km", "Kilometers"), ("mi", "Miles")],
        default="km",
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="For age-graded performance calculations",
    )
    strava_profile_picture_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Strava profile picture URL",
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"


class StravaToken(TimestampedModel):
    """
    Stores encrypted Strava OAuth tokens for a user.

    Tokens are encrypted at rest using Fernet symmetric encryption.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="strava_token",
    )
    access_token = EncryptedTextField()
    refresh_token = EncryptedTextField()
    expires_at = models.DateTimeField()
    scope = models.CharField(
        max_length=255,
        default="read,read_all,activity:read_all",
    )

    class Meta:
        verbose_name = "Strava token"
        verbose_name_plural = "Strava tokens"

    def __str__(self):
        return f"Strava token for {self.user.username}"

    def is_expired(self) -> bool:
        """Check if the access token has expired."""
        return timezone.now() >= self.expires_at

    def refresh_if_needed(self) -> bool:
        """
        Refresh the token if expired.
        Returns True if token was refreshed.
        """
        if not self.is_expired():
            return False

        from vught_pace_keeper.accounts.strava_utils import refresh_strava_token

        return refresh_strava_token(self)
