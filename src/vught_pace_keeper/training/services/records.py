"""Personal record detection and management service."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from vught_pace_keeper.training.models import CompletedWorkout, PersonalRecord

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


# Tolerance for matching workout distance to standard distances (in km)
DISTANCE_TOLERANCE = 0.1  # 100 meters


@dataclass
class PRCheckResult:
    """Result of checking for a new PR."""

    is_new_pr: bool
    distance: str
    time: timedelta
    previous_time: Optional[timedelta] = None
    improvement: Optional[timedelta] = None


class PersonalRecordService:
    """Service for managing personal records."""

    def __init__(self, user: "User"):
        self.user = user

    def get_all_records(self) -> dict[str, Optional[PersonalRecord]]:
        """Get all personal records organized by distance."""
        records = {}
        for distance_code, _ in PersonalRecord.Distance.choices:
            records[distance_code] = self.get_record_for_distance(distance_code)
        return records

    def get_record_for_distance(self, distance: str) -> Optional[PersonalRecord]:
        """Get the current PR for a specific distance."""
        return (
            PersonalRecord.objects.filter(user=self.user, distance=distance)
            .order_by("time")
            .first()
        )

    def check_for_pr(self, workout: CompletedWorkout) -> list[PRCheckResult]:
        """
        Check if a workout sets any new personal records.

        Returns list of PRCheckResult for any distances where this is a new PR.
        """
        results = []

        if not workout.actual_distance_km or not workout.actual_duration:
            return results

        workout_distance = float(workout.actual_distance_km)
        workout_time = workout.actual_duration

        # Check against each standard distance
        for distance_code, target_km in PersonalRecord.DISTANCE_KM.items():
            # Check if workout distance is close enough to this standard distance
            if abs(workout_distance - target_km) <= DISTANCE_TOLERANCE:
                result = self._check_distance_pr(
                    distance_code, workout_time, workout
                )
                if result.is_new_pr:
                    results.append(result)

        return results

    def _check_distance_pr(
        self, distance: str, time: timedelta, workout: CompletedWorkout
    ) -> PRCheckResult:
        """Check if a time is a new PR for a specific distance."""
        current_pr = self.get_record_for_distance(distance)

        if current_pr is None:
            # First record for this distance
            return PRCheckResult(
                is_new_pr=True,
                distance=distance,
                time=time,
                previous_time=None,
                improvement=None,
            )

        if time < current_pr.time:
            # New PR!
            improvement = current_pr.time - time
            return PRCheckResult(
                is_new_pr=True,
                distance=distance,
                time=time,
                previous_time=current_pr.time,
                improvement=improvement,
            )

        return PRCheckResult(
            is_new_pr=False,
            distance=distance,
            time=time,
            previous_time=current_pr.time,
            improvement=None,
        )

    def create_record(
        self,
        workout: CompletedWorkout,
        distance: str,
        time: Optional[timedelta] = None,
    ) -> PersonalRecord:
        """
        Create a new personal record from a workout.

        Args:
            workout: The workout that set the record
            distance: Distance code (e.g., "5k", "half")
            time: Override time (defaults to workout duration)
        """
        record_time = time or workout.actual_duration
        distance_km = PersonalRecord.DISTANCE_KM.get(distance, float(workout.actual_distance_km))

        # Calculate pace
        duration_minutes = record_time.total_seconds() / 60
        pace = Decimal(str(duration_minutes / distance_km)).quantize(Decimal("0.01"))

        return PersonalRecord.objects.create(
            user=self.user,
            distance=distance,
            time=record_time,
            date=workout.date,
            pace_min_per_km=pace,
            source_workout=workout,
            is_manual=False,
        )

    def add_manual_record(
        self,
        distance: str,
        time: timedelta,
        date,
        custom_distance_km: Optional[Decimal] = None,
    ) -> PersonalRecord:
        """
        Add a manual personal record (not from a workout).

        Args:
            distance: Distance code
            time: Record time
            date: Date the record was set
            custom_distance_km: Distance in km for custom records
        """
        if distance == "custom":
            if not custom_distance_km:
                raise ValueError("custom_distance_km required for custom distance")
            distance_km = float(custom_distance_km)
        else:
            distance_km = PersonalRecord.DISTANCE_KM.get(distance, 0)

        if distance_km <= 0:
            raise ValueError("Invalid distance")

        # Calculate pace
        duration_minutes = time.total_seconds() / 60
        pace = Decimal(str(duration_minutes / distance_km)).quantize(Decimal("0.01"))

        return PersonalRecord.objects.create(
            user=self.user,
            distance=distance,
            custom_distance_km=custom_distance_km if distance == "custom" else None,
            time=time,
            date=date,
            pace_min_per_km=pace,
            source_workout=None,
            is_manual=True,
        )

    def delete_record(self, record_id: int) -> bool:
        """Delete a personal record."""
        try:
            record = PersonalRecord.objects.get(pk=record_id, user=self.user)
            record.delete()
            return True
        except PersonalRecord.DoesNotExist:
            return False

    def get_recent_records(self, limit: int = 5) -> list[PersonalRecord]:
        """Get most recently set records."""
        return list(
            PersonalRecord.objects.filter(user=self.user)
            .order_by("-date", "-created_at")[:limit]
        )

    def get_record_history(self, distance: str) -> list[PersonalRecord]:
        """Get all records for a specific distance, ordered by time."""
        return list(
            PersonalRecord.objects.filter(user=self.user, distance=distance)
            .order_by("time")
        )
