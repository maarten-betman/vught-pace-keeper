"""Workout matching service for linking completed workouts to scheduled workouts."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from vught_pace_keeper.training.models import CompletedWorkout, ScheduledWorkout, TrainingPlan

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


@dataclass
class MatchCandidate:
    """A potential match for a completed workout."""

    scheduled_workout: ScheduledWorkout
    workout_date: date
    score: float  # 0.0 to 1.0, higher is better match
    date_diff_days: int
    distance_diff_km: Optional[Decimal]
    reason: str


@dataclass
class MatchResult:
    """Result of an auto-match attempt."""

    matched: int = 0
    skipped: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class WorkoutMatchingService:
    """Service for matching completed workouts to scheduled workouts."""

    # Scoring weights
    DATE_WEIGHT = 0.6
    DISTANCE_WEIGHT = 0.4

    # Thresholds
    MAX_DATE_DIFF_DAYS = 3  # Only consider workouts within 3 days
    AUTO_MATCH_THRESHOLD = 0.7  # Auto-match if score >= 0.7

    def __init__(self, user: "User"):
        self.user = user

    def get_unmatched_workouts(self) -> list[CompletedWorkout]:
        """Get all completed workouts without a scheduled workout link."""
        return list(
            CompletedWorkout.objects.filter(
                user=self.user,
                scheduled_workout__isnull=True,
            ).order_by("-date")
        )

    def get_unmatched_count(self) -> int:
        """Get count of unmatched workouts."""
        return CompletedWorkout.objects.filter(
            user=self.user,
            scheduled_workout__isnull=True,
        ).count()

    def find_candidates(
        self, workout: CompletedWorkout, limit: int = 5
    ) -> list[MatchCandidate]:
        """
        Find potential scheduled workout matches for a completed workout.

        Args:
            workout: The completed workout to find matches for
            limit: Maximum number of candidates to return

        Returns:
            List of MatchCandidate sorted by score (best first)
        """
        candidates = []

        # Get all active plans for this user
        plans = TrainingPlan.objects.filter(
            user=self.user,
            is_template=False,
        ).prefetch_related("weeks__scheduled_workouts")

        for plan in plans:
            if not plan.target_race_date or not plan.duration_weeks:
                continue

            # Calculate plan start date
            plan_start = plan.target_race_date - timedelta(weeks=plan.duration_weeks)

            for week in plan.weeks.all():
                week_start = plan_start + timedelta(weeks=week.week_number - 1)

                for scheduled in week.scheduled_workouts.all():
                    # Skip rest days
                    if scheduled.workout_type == "rest":
                        continue

                    # Skip already matched workouts
                    if scheduled.completions.exists():
                        continue

                    # Calculate the scheduled workout date
                    scheduled_date = week_start + timedelta(days=scheduled.day_of_week - 1)

                    # Check date proximity
                    date_diff = abs((workout.date - scheduled_date).days)
                    if date_diff > self.MAX_DATE_DIFF_DAYS:
                        continue

                    # Calculate match score
                    candidate = self._score_candidate(
                        workout, scheduled, scheduled_date, date_diff
                    )
                    candidates.append(candidate)

        # Sort by score (highest first) and limit
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:limit]

    def _score_candidate(
        self,
        workout: CompletedWorkout,
        scheduled: ScheduledWorkout,
        scheduled_date: date,
        date_diff: int,
    ) -> MatchCandidate:
        """
        Calculate a match score for a scheduled workout candidate.

        Score is 0.0 to 1.0, based on:
        - Date proximity (60% weight)
        - Distance similarity (40% weight)
        """
        # Date score: 1.0 for same day, decreasing for further days
        date_score = max(0, 1.0 - (date_diff / (self.MAX_DATE_DIFF_DAYS + 1)))

        # Distance score
        distance_diff = None
        if workout.actual_distance_km and scheduled.target_distance_km:
            distance_diff = abs(workout.actual_distance_km - scheduled.target_distance_km)
            # Score based on percentage difference
            target = float(scheduled.target_distance_km)
            if target > 0:
                pct_diff = float(distance_diff) / target
                distance_score = max(0, 1.0 - pct_diff)
            else:
                distance_score = 0.5
        else:
            distance_score = 0.5  # Neutral if no distance to compare

        # Combined score
        total_score = (
            date_score * self.DATE_WEIGHT + distance_score * self.DISTANCE_WEIGHT
        )

        # Build reason string
        reasons = []
        if date_diff == 0:
            reasons.append("Same day")
        elif date_diff == 1:
            reasons.append("1 day apart")
        else:
            reasons.append(f"{date_diff} days apart")

        if distance_diff is not None:
            if distance_diff < Decimal("0.5"):
                reasons.append("Distance matches")
            else:
                reasons.append(f"{distance_diff:.1f}km difference")

        return MatchCandidate(
            scheduled_workout=scheduled,
            workout_date=scheduled_date,
            score=round(total_score, 2),
            date_diff_days=date_diff,
            distance_diff_km=distance_diff,
            reason=", ".join(reasons),
        )

    def match_workout(
        self, completed_id: int, scheduled_id: int
    ) -> tuple[bool, str]:
        """
        Link a completed workout to a scheduled workout.

        Args:
            completed_id: ID of the completed workout
            scheduled_id: ID of the scheduled workout

        Returns:
            Tuple of (success, message)
        """
        try:
            completed = CompletedWorkout.objects.get(
                pk=completed_id, user=self.user
            )
            scheduled = ScheduledWorkout.objects.get(pk=scheduled_id)

            # Verify the scheduled workout belongs to user's plan
            if scheduled.week.plan.user != self.user:
                return False, "Scheduled workout not found"

            # Check if already matched
            if completed.scheduled_workout:
                return False, "Workout already matched"

            if scheduled.completions.exists():
                return False, "Scheduled workout already has a completion"

            # Create the match
            completed.scheduled_workout = scheduled
            completed.save(update_fields=["scheduled_workout", "updated_at"])

            return True, "Workout matched successfully"

        except CompletedWorkout.DoesNotExist:
            return False, "Completed workout not found"
        except ScheduledWorkout.DoesNotExist:
            return False, "Scheduled workout not found"

    def unmatch_workout(self, completed_id: int) -> tuple[bool, str]:
        """
        Remove the link between a completed workout and its scheduled workout.

        Args:
            completed_id: ID of the completed workout

        Returns:
            Tuple of (success, message)
        """
        try:
            completed = CompletedWorkout.objects.get(
                pk=completed_id, user=self.user
            )

            if not completed.scheduled_workout:
                return False, "Workout is not matched"

            completed.scheduled_workout = None
            completed.save(update_fields=["scheduled_workout", "updated_at"])

            return True, "Workout unmatched successfully"

        except CompletedWorkout.DoesNotExist:
            return False, "Workout not found"

    def auto_match_all(self, threshold: float = None) -> MatchResult:
        """
        Automatically match all unmatched workouts that have high-confidence matches.

        Args:
            threshold: Minimum score to auto-match (default: AUTO_MATCH_THRESHOLD)

        Returns:
            MatchResult with counts
        """
        if threshold is None:
            threshold = self.AUTO_MATCH_THRESHOLD

        result = MatchResult()
        unmatched = self.get_unmatched_workouts()

        for workout in unmatched:
            candidates = self.find_candidates(workout, limit=1)

            if not candidates:
                result.skipped += 1
                continue

            best = candidates[0]
            if best.score >= threshold:
                success, msg = self.match_workout(
                    workout.pk, best.scheduled_workout.pk
                )
                if success:
                    result.matched += 1
                else:
                    result.errors.append(f"Workout {workout.pk}: {msg}")
            else:
                result.skipped += 1

        return result

    def get_best_match(self, workout: CompletedWorkout) -> Optional[MatchCandidate]:
        """Get the best match candidate for a workout, if any."""
        candidates = self.find_candidates(workout, limit=1)
        return candidates[0] if candidates else None
