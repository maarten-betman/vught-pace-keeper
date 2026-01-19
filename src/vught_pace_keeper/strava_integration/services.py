"""High-level services for Strava activity synchronization."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import polyline
from django.conf import settings
from django.contrib.gis.geos import LineString
from django.utils import timezone

from vught_pace_keeper.training.models import ActivityStream, CompletedWorkout, ScheduledWorkout

from .client import StravaActivity, StravaClient

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


@dataclass
class SyncResult:
    """Result of a sync operation."""

    imported: int = 0
    skipped: int = 0
    matched: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.imported + self.skipped


class ActivitySyncService:
    """Service for syncing Strava activities to CompletedWorkout records."""

    def __init__(self, user: "User"):
        """
        Initialize sync service for a user.

        Args:
            user: User instance with associated StravaToken
        """
        self.user = user
        self.client = StravaClient(user)

    def sync_activities(self, since: datetime | None = None) -> SyncResult:
        """
        Fetch and import activities since last sync.

        Args:
            since: Optional start time (defaults to last_strava_sync or 30 days ago)

        Returns:
            SyncResult with counts of imported/skipped activities
        """
        if since is None:
            since = self._get_sync_start_time()

        activities = self.client.get_all_activities(after=since)
        result = SyncResult()

        for activity in activities:
            # Only sync running activities
            if activity.type != "Run":
                continue

            # Skip if already imported
            if self._already_imported(activity.id):
                result.skipped += 1
                continue

            try:
                workout = self._create_completed_workout(activity)
                result.imported += 1

                # Fetch and store activity streams (pace, HR, etc.)
                self._fetch_and_store_streams(activity.id, workout)

                if self._try_match_scheduled(workout):
                    result.matched += 1
            except Exception as e:
                result.errors.append(f"Failed to import activity {activity.id}: {e}")

        # Update last sync timestamp
        self.user.last_strava_sync = timezone.now()
        self.user.save(update_fields=["last_strava_sync"])

        return result

    def _get_sync_start_time(self) -> datetime:
        """Get the start time for syncing activities.

        Uses the date of the latest Strava-synced workout rather than
        the sync timestamp, to catch late-uploaded activities.
        """
        # Find the most recent Strava-synced workout
        latest_workout = (
            CompletedWorkout.objects.filter(
                user=self.user,
                source=CompletedWorkout.Source.STRAVA,
            )
            .order_by("-date")
            .first()
        )

        if latest_workout:
            # Start from the beginning of that workout's date (midnight)
            # to ensure we don't miss same-day activities
            return timezone.make_aware(
                datetime.combine(latest_workout.date, datetime.min.time())
            )

        # First sync: look back configured days (default 365)
        return timezone.now() - timedelta(days=settings.STRAVA_SYNC_LOOKBACK_DAYS)

    def _already_imported(self, strava_id: int) -> bool:
        """Check if activity has already been imported."""
        return CompletedWorkout.objects.filter(strava_activity_id=strava_id).exists()

    def _create_completed_workout(self, activity: StravaActivity) -> CompletedWorkout:
        """
        Create a CompletedWorkout from a Strava activity.

        Args:
            activity: StravaActivity instance

        Returns:
            Created CompletedWorkout instance
        """
        distance_km = Decimal(str(activity.distance / 1000)).quantize(Decimal("0.01"))
        duration = timedelta(seconds=activity.moving_time)
        pace = self._calculate_pace(activity.distance, activity.moving_time)

        return CompletedWorkout.objects.create(
            user=self.user,
            date=activity.start_date.date(),
            actual_distance_km=distance_km,
            actual_duration=duration,
            average_pace_min_per_km=pace,
            average_heart_rate=int(activity.average_heartrate) if activity.average_heartrate else None,
            elevation_gain_m=Decimal(str(activity.total_elevation_gain)).quantize(Decimal("0.01"))
            if activity.total_elevation_gain
            else None,
            route=self._decode_polyline(activity.map_polyline),
            source=CompletedWorkout.Source.STRAVA,
            strava_activity_id=activity.id,
            notes=activity.name,
        )

    def _calculate_pace(self, distance_meters: float, time_seconds: int) -> Decimal:
        """
        Calculate pace in minutes per kilometer.

        Args:
            distance_meters: Distance in meters
            time_seconds: Time in seconds

        Returns:
            Pace as Decimal (e.g., 5.50 for 5:30/km)
        """
        if distance_meters <= 0 or time_seconds <= 0:
            return Decimal("0.00")

        distance_km = distance_meters / 1000
        time_minutes = time_seconds / 60
        pace = time_minutes / distance_km

        return Decimal(str(pace)).quantize(Decimal("0.01"))

    def _decode_polyline(self, encoded: str | None) -> LineString | None:
        """
        Convert Strava encoded polyline to PostGIS LineString.

        Args:
            encoded: Encoded polyline string

        Returns:
            LineString geometry or None
        """
        if not encoded:
            return None

        try:
            coords = polyline.decode(encoded)
            # Polyline returns (lat, lng), but PostGIS expects (lng, lat)
            points = [(lng, lat) for lat, lng in coords]

            if len(points) < 2:
                return None

            return LineString(points, srid=4326)
        except Exception:
            return None

    def _try_match_scheduled(self, workout: CompletedWorkout) -> bool:
        """
        Try to auto-match a workout to a scheduled workout.

        Matches by date for the user's active training plans.

        Args:
            workout: CompletedWorkout to match

        Returns:
            True if matched, False otherwise
        """
        # Find scheduled workouts for this date
        # We need to calculate which scheduled workouts fall on this date
        # by looking at the plan start date + week number + day of week

        from django.db.models import F

        # Get all active plans for this user
        scheduled = (
            ScheduledWorkout.objects.filter(week__plan__user=self.user)
            .select_related("week__plan")
            .order_by("-week__plan__created_at")  # Most recent plan first
        )

        for sw in scheduled:
            plan = sw.week.plan
            # Calculate plan start date from target_race_date and duration
            if not plan.target_race_date or not plan.duration_weeks:
                continue

            plan_start = plan.target_race_date - timedelta(weeks=plan.duration_weeks)

            # Calculate the date of this scheduled workout
            week_start = plan_start + timedelta(weeks=sw.week.week_number - 1)
            workout_date = week_start + timedelta(days=sw.day_of_week - 1)

            if workout_date == workout.date:
                # Check if already matched to another completion
                if not sw.completions.exists():
                    workout.scheduled_workout = sw
                    workout.save(update_fields=["scheduled_workout"])
                    return True

        return False

    def _fetch_and_store_streams(self, activity_id: int, workout: CompletedWorkout) -> None:
        """
        Fetch activity streams from Strava and store in ActivityStream.

        Args:
            activity_id: Strava activity ID
            workout: CompletedWorkout to associate streams with
        """
        try:
            stream_types = ["time", "distance", "heartrate", "velocity_smooth", "altitude"]
            streams = self.client.get_activity_streams(activity_id, stream_types)

            if not streams:
                return

            # Extract data arrays from stream response
            # Strava returns {type: {data: [...], ...}, ...}
            time_data = streams.get("time", {}).get("data", [])
            distance_data = streams.get("distance", {}).get("data", [])
            heartrate_data = streams.get("heartrate", {}).get("data", [])
            velocity_data = streams.get("velocity_smooth", {}).get("data", [])
            altitude_data = streams.get("altitude", {}).get("data", [])

            # Only create stream if we have some data
            if time_data or distance_data:
                ActivityStream.objects.create(
                    workout=workout,
                    time_data=time_data,
                    distance_data=distance_data,
                    heartrate_data=heartrate_data,
                    velocity_data=velocity_data,
                    altitude_data=altitude_data,
                )
        except Exception:
            # Don't fail workout import if stream fetch fails
            pass
