"""Low-level Strava API client."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import requests

from .exceptions import StravaAPIError, StravaAuthError, StravaRateLimitError

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


@dataclass
class StravaActivity:
    """Represents a Strava activity."""

    id: int
    name: str
    type: str
    start_date: datetime
    distance: float  # meters
    moving_time: int  # seconds
    elapsed_time: int  # seconds
    total_elevation_gain: float
    average_heartrate: float | None
    max_heartrate: float | None
    map_polyline: str | None  # encoded polyline

    @classmethod
    def from_api_response(cls, data: dict) -> "StravaActivity":
        """Create StravaActivity from Strava API response."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            type=data.get("type", ""),
            start_date=datetime.fromisoformat(data["start_date_local"].replace("Z", "+00:00")),
            distance=data.get("distance", 0),
            moving_time=data.get("moving_time", 0),
            elapsed_time=data.get("elapsed_time", 0),
            total_elevation_gain=data.get("total_elevation_gain", 0),
            average_heartrate=data.get("average_heartrate"),
            max_heartrate=data.get("max_heartrate"),
            map_polyline=data.get("map", {}).get("summary_polyline"),
        )


class StravaClient:
    """Low-level Strava API client with error handling."""

    BASE_URL = "https://www.strava.com/api/v3"
    TIMEOUT = 30

    def __init__(self, user: "User"):
        """
        Initialize client with a user's credentials.

        Args:
            user: User instance with associated StravaToken
        """
        self.user = user
        self._access_token: str | None = None
        self._ensure_valid_token()

    def _ensure_valid_token(self) -> None:
        """Refresh token if expired and cache access token."""
        if not hasattr(self.user, "strava_token"):
            raise StravaAuthError("No Strava account connected")

        self.user.strava_token.refresh_if_needed()
        self._access_token = self.user.strava_token.access_token

    def _get_headers(self) -> dict:
        """Get authorization headers."""
        return {"Authorization": f"Bearer {self._access_token}"}

    def _request(self, method: str, endpoint: str, **kwargs) -> dict | list:
        """
        Make authenticated request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests

        Returns:
            Parsed JSON response

        Raises:
            StravaAuthError: On 401 response
            StravaRateLimitError: On 429 response
            StravaAPIError: On other errors
        """
        url = f"{self.BASE_URL}{endpoint}"
        kwargs.setdefault("timeout", self.TIMEOUT)
        kwargs.setdefault("headers", {}).update(self._get_headers())

        response = requests.request(method, url, **kwargs)

        if response.status_code == 401:
            raise StravaAuthError(
                "Strava authentication failed. Please reconnect your account.",
                status_code=401,
                response=response.json() if response.text else None,
            )

        if response.status_code == 429:
            raise StravaRateLimitError(
                "Strava rate limit exceeded. Please try again in 15 minutes.",
                status_code=429,
                response=response.json() if response.text else None,
            )

        if response.status_code >= 400:
            raise StravaAPIError(
                f"Strava API error: {response.status_code}",
                status_code=response.status_code,
                response=response.json() if response.text else None,
            )

        return response.json()

    def get_athlete(self) -> dict:
        """
        Get authenticated athlete's profile.

        Returns:
            Athlete profile data
        """
        return self._request("GET", "/athlete")

    def get_activities(
        self,
        after: datetime | None = None,
        before: datetime | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[StravaActivity]:
        """
        Fetch activities for the authenticated athlete.

        Args:
            after: Only return activities after this time
            before: Only return activities before this time
            page: Page number (1-indexed)
            per_page: Number of results per page (max 200)

        Returns:
            List of StravaActivity objects
        """
        params = {"page": page, "per_page": min(per_page, 200)}

        if after:
            params["after"] = int(after.timestamp())
        if before:
            params["before"] = int(before.timestamp())

        data = self._request("GET", "/athlete/activities", params=params)
        return [StravaActivity.from_api_response(activity) for activity in data]

    def get_all_activities(
        self,
        after: datetime | None = None,
        before: datetime | None = None,
        max_pages: int = 10,
    ) -> list[StravaActivity]:
        """
        Fetch all activities with pagination.

        Args:
            after: Only return activities after this time
            before: Only return activities before this time
            max_pages: Maximum number of pages to fetch (safety limit)

        Returns:
            List of all StravaActivity objects
        """
        all_activities = []
        page = 1
        per_page = 100  # Use larger page size for efficiency

        while page <= max_pages:
            activities = self.get_activities(
                after=after, before=before, page=page, per_page=per_page
            )

            if not activities:
                break

            all_activities.extend(activities)

            if len(activities) < per_page:
                break

            page += 1

        return all_activities

    def get_activity_detail(self, activity_id: int) -> dict:
        """
        Get detailed information about a specific activity.

        Args:
            activity_id: Strava activity ID

        Returns:
            Detailed activity data
        """
        return self._request("GET", f"/activities/{activity_id}")

    def get_activity_streams(
        self,
        activity_id: int,
        stream_types: list[str] | None = None,
    ) -> dict:
        """
        Get activity streams (GPS, heart rate, etc.).

        Args:
            activity_id: Strava activity ID
            stream_types: Types of streams to fetch (default: latlng, altitude, heartrate, time)

        Returns:
            Stream data keyed by type
        """
        if stream_types is None:
            stream_types = ["latlng", "altitude", "heartrate", "time"]

        params = {
            "keys": ",".join(stream_types),
            "key_by_type": "true",
        }

        return self._request("GET", f"/activities/{activity_id}/streams", params=params)
