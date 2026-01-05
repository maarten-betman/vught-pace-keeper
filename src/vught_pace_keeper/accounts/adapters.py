from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for login redirects."""

    def get_login_redirect_url(self, request):
        return "/dashboard/"


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter for Strava integration."""

    def save_user(self, request, sociallogin, form=None):
        """
        Called when a social account is connected (new user).
        Store Strava-specific data on the User model.
        """
        user = super().save_user(request, sociallogin, form)
        self._handle_strava_connection(user, sociallogin)
        return user

    def pre_social_login(self, request, sociallogin):
        """
        Called after authentication but before login.
        Handle existing users connecting Strava.
        """
        super().pre_social_login(request, sociallogin)

        # If user exists and is connecting Strava, store the data
        if sociallogin.is_existing and sociallogin.account.provider == "strava":
            self._handle_strava_connection(sociallogin.user, sociallogin)

    def _handle_strava_connection(self, user, sociallogin):
        """Store Strava data and tokens for a user."""
        if sociallogin.account.provider != "strava":
            return

        extra_data = sociallogin.account.extra_data
        user.strava_athlete_id = extra_data.get("id")
        user.strava_profile_picture_url = extra_data.get("profile", "")

        # Use first/last name from Strava if not set
        if not user.first_name:
            user.first_name = extra_data.get("firstname", "")
        if not user.last_name:
            user.last_name = extra_data.get("lastname", "")

        user.save()

        # Store tokens
        self._store_strava_tokens(user, sociallogin)

    def _store_strava_tokens(self, user, sociallogin):
        """Store Strava OAuth tokens for the user."""
        from datetime import timedelta

        from django.utils import timezone

        from vught_pace_keeper.accounts.models import StravaToken

        token = sociallogin.token

        # Get expires_in from token or default to 6 hours
        expires_in = getattr(token, "expires_in", None) or 21600

        StravaToken.objects.update_or_create(
            user=user,
            defaults={
                "access_token": token.token,
                "refresh_token": token.token_secret or "",
                "expires_at": timezone.now() + timedelta(seconds=expires_in),
                "scope": "read,read_all,activity:read_all",
            },
        )
