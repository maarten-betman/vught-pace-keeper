"""Custom exceptions for Strava integration."""


class StravaError(Exception):
    """Base exception for Strava integration."""

    pass


class StravaAPIError(StravaError):
    """API request failed."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class StravaRateLimitError(StravaAPIError):
    """Rate limit exceeded (429)."""

    pass


class StravaAuthError(StravaAPIError):
    """Authentication failed (401)."""

    pass
