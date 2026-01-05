"""Strava API utilities for token refresh and API calls."""

from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone


def refresh_strava_token(strava_token) -> bool:
    """
    Refresh an expired Strava access token.

    Updates the StravaToken instance in-place and saves to database.

    Args:
        strava_token: StravaToken model instance with expired access_token

    Returns:
        True if token was successfully refreshed, False otherwise
    """
    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": strava_token.refresh_token,
        },
        timeout=30,
    )

    if response.status_code != 200:
        return False

    data = response.json()
    strava_token.access_token = data["access_token"]
    strava_token.refresh_token = data["refresh_token"]
    strava_token.expires_at = timezone.now() + timedelta(seconds=data["expires_in"])
    strava_token.save()
    return True


def get_strava_athlete(access_token: str) -> dict | None:
    """
    Fetch the authenticated athlete's profile from Strava.

    Args:
        access_token: Valid Strava access token

    Returns:
        Dict with athlete data or None if request failed
    """
    response = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )

    if response.status_code != 200:
        return None

    return response.json()
