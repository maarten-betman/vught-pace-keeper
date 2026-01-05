"""Goal tracking and progress calculation service."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from django.db.models import Sum

from vught_pace_keeper.training.models import CompletedWorkout, Goal, PersonalRecord

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


@dataclass
class GoalProgress:
    """Progress information for a goal."""

    goal: Goal
    current_value: Optional[Decimal]
    target_value: Optional[Decimal]
    progress_percent: int
    remaining: Optional[str]
    status_message: str
    is_achieved: bool


class GoalTrackingService:
    """Service for tracking goal progress."""

    def __init__(self, user: "User"):
        self.user = user

    def get_active_goals(self) -> list[Goal]:
        """Get all active goals for the user."""
        return list(
            Goal.objects.filter(user=self.user, status=Goal.Status.ACTIVE)
            .order_by("-created_at")
        )

    def get_all_goals(self) -> list[Goal]:
        """Get all goals for the user."""
        return list(Goal.objects.filter(user=self.user).order_by("-created_at"))

    def calculate_progress(self, goal: Goal) -> GoalProgress:
        """Calculate current progress for a goal."""
        if goal.goal_type == Goal.GoalType.RACE_TIME:
            return self._calculate_race_time_progress(goal)
        elif goal.goal_type == Goal.GoalType.WEEKLY_DISTANCE:
            return self._calculate_weekly_distance_progress(goal)
        elif goal.goal_type == Goal.GoalType.MONTHLY_DISTANCE:
            return self._calculate_monthly_distance_progress(goal)
        elif goal.goal_type == Goal.GoalType.PACE_IMPROVEMENT:
            return self._calculate_pace_progress(goal)

        return GoalProgress(
            goal=goal,
            current_value=None,
            target_value=None,
            progress_percent=0,
            remaining=None,
            status_message="Unknown goal type",
            is_achieved=False,
        )

    def _calculate_race_time_progress(self, goal: Goal) -> GoalProgress:
        """Calculate progress for a race time goal."""
        if not goal.race_distance or not goal.target_time:
            return GoalProgress(
                goal=goal,
                current_value=None,
                target_value=None,
                progress_percent=0,
                remaining=None,
                status_message="Invalid goal configuration",
                is_achieved=False,
            )

        # Get current PR for this distance
        current_pr = PersonalRecord.objects.filter(
            user=self.user, distance=goal.race_distance
        ).order_by("time").first()

        target_seconds = goal.target_time.total_seconds()

        if not current_pr:
            return GoalProgress(
                goal=goal,
                current_value=None,
                target_value=Decimal(str(target_seconds)),
                progress_percent=0,
                remaining=self._format_time(goal.target_time),
                status_message="No PR recorded yet",
                is_achieved=False,
            )

        current_seconds = current_pr.time.total_seconds()

        # Check if achieved
        if current_seconds <= target_seconds:
            return GoalProgress(
                goal=goal,
                current_value=Decimal(str(current_seconds)),
                target_value=Decimal(str(target_seconds)),
                progress_percent=100,
                remaining="0:00",
                status_message=f"Achieved! PR: {current_pr.formatted_time}",
                is_achieved=True,
            )

        # Calculate progress (how close to target)
        # If current is 4:00:00 and target is 3:30:00, we need to improve by 30 min
        time_to_improve = current_seconds - target_seconds
        remaining_delta = timedelta(seconds=time_to_improve)

        # Progress is based on improvement from starting point
        # This is tricky - we'll use a simple approach based on how close we are
        # 100% = at or below target, 0% = no PR yet
        # Scale linearly between "double target time" (0%) and target (100%)
        max_time = target_seconds * 2
        if current_seconds >= max_time:
            progress = 0
        else:
            progress = int(((max_time - current_seconds) / (max_time - target_seconds)) * 100)
            progress = max(0, min(100, progress))

        return GoalProgress(
            goal=goal,
            current_value=Decimal(str(current_seconds)),
            target_value=Decimal(str(target_seconds)),
            progress_percent=progress,
            remaining=self._format_time(remaining_delta),
            status_message=f"Current PR: {current_pr.formatted_time}",
            is_achieved=False,
        )

    def _calculate_weekly_distance_progress(self, goal: Goal) -> GoalProgress:
        """Calculate progress for a weekly distance goal."""
        if not goal.target_distance_km:
            return GoalProgress(
                goal=goal,
                current_value=None,
                target_value=None,
                progress_percent=0,
                remaining=None,
                status_message="Invalid goal configuration",
                is_achieved=False,
            )

        # Get current week's total
        today = date.today()
        monday = today - timedelta(days=today.weekday())

        result = CompletedWorkout.objects.filter(
            user=self.user,
            date__gte=monday,
            date__lte=today,
        ).aggregate(total=Sum("actual_distance_km"))

        current_km = result["total"] or Decimal("0")
        target_km = goal.target_distance_km

        progress = int((current_km / target_km) * 100) if target_km > 0 else 0
        progress = min(progress, 100)

        remaining_km = max(Decimal("0"), target_km - current_km)
        is_achieved = current_km >= target_km

        return GoalProgress(
            goal=goal,
            current_value=current_km,
            target_value=target_km,
            progress_percent=progress,
            remaining=f"{remaining_km:.1f} km",
            status_message=f"{current_km:.1f} / {target_km:.1f} km this week",
            is_achieved=is_achieved,
        )

    def _calculate_monthly_distance_progress(self, goal: Goal) -> GoalProgress:
        """Calculate progress for a monthly distance goal."""
        if not goal.target_distance_km:
            return GoalProgress(
                goal=goal,
                current_value=None,
                target_value=None,
                progress_percent=0,
                remaining=None,
                status_message="Invalid goal configuration",
                is_achieved=False,
            )

        # Get current month's total
        today = date.today()
        first_of_month = date(today.year, today.month, 1)

        result = CompletedWorkout.objects.filter(
            user=self.user,
            date__gte=first_of_month,
            date__lte=today,
        ).aggregate(total=Sum("actual_distance_km"))

        current_km = result["total"] or Decimal("0")
        target_km = goal.target_distance_km

        progress = int((current_km / target_km) * 100) if target_km > 0 else 0
        progress = min(progress, 100)

        remaining_km = max(Decimal("0"), target_km - current_km)
        is_achieved = current_km >= target_km

        return GoalProgress(
            goal=goal,
            current_value=current_km,
            target_value=target_km,
            progress_percent=progress,
            remaining=f"{remaining_km:.1f} km",
            status_message=f"{current_km:.1f} / {target_km:.1f} km this month",
            is_achieved=is_achieved,
        )

    def _calculate_pace_progress(self, goal: Goal) -> GoalProgress:
        """Calculate progress for a pace improvement goal."""
        if not goal.target_pace or not goal.race_distance:
            return GoalProgress(
                goal=goal,
                current_value=None,
                target_value=None,
                progress_percent=0,
                remaining=None,
                status_message="Invalid goal configuration",
                is_achieved=False,
            )

        # Get current PR pace for this distance
        current_pr = PersonalRecord.objects.filter(
            user=self.user, distance=goal.race_distance
        ).order_by("time").first()

        if not current_pr:
            return GoalProgress(
                goal=goal,
                current_value=None,
                target_value=goal.target_pace,
                progress_percent=0,
                remaining=self._format_pace(goal.target_pace),
                status_message="No PR recorded yet",
                is_achieved=False,
            )

        current_pace = current_pr.pace_min_per_km
        target_pace = goal.target_pace

        # Check if achieved (lower pace = faster = achieved)
        if current_pace <= target_pace:
            return GoalProgress(
                goal=goal,
                current_value=current_pace,
                target_value=target_pace,
                progress_percent=100,
                remaining="0:00/km",
                status_message=f"Achieved! Current: {current_pr.formatted_pace}",
                is_achieved=True,
            )

        # Calculate progress
        pace_to_improve = float(current_pace - target_pace)
        remaining_pace = self._format_pace(Decimal(str(pace_to_improve)))

        # Progress based on improvement needed
        max_pace = float(target_pace) * 1.5  # Arbitrary starting point
        if float(current_pace) >= max_pace:
            progress = 0
        else:
            progress = int(((max_pace - float(current_pace)) / (max_pace - float(target_pace))) * 100)
            progress = max(0, min(100, progress))

        return GoalProgress(
            goal=goal,
            current_value=current_pace,
            target_value=target_pace,
            progress_percent=progress,
            remaining=f"{remaining_pace}/km to improve",
            status_message=f"Current: {current_pr.formatted_pace}",
            is_achieved=False,
        )

    def update_goal_status(self, goal: Goal) -> Goal:
        """Update goal status based on current progress."""
        progress = self.calculate_progress(goal)

        if progress.is_achieved and goal.status == Goal.Status.ACTIVE:
            goal.status = Goal.Status.ACHIEVED
            goal.save(update_fields=["status", "updated_at"])
        elif goal.is_overdue and goal.status == Goal.Status.ACTIVE:
            goal.status = Goal.Status.EXPIRED
            goal.save(update_fields=["status", "updated_at"])

        # Update current_value
        if progress.current_value is not None:
            goal.current_value = progress.current_value
            goal.save(update_fields=["current_value", "updated_at"])

        return goal

    def check_all_goals(self) -> list[Goal]:
        """Check and update status of all active goals."""
        goals = self.get_active_goals()
        updated = []

        for goal in goals:
            updated_goal = self.update_goal_status(goal)
            updated.append(updated_goal)

        return updated

    def _format_time(self, delta: timedelta) -> str:
        """Format timedelta as H:MM:SS or MM:SS."""
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _format_pace(self, pace: Decimal) -> str:
        """Format pace as M:SS."""
        pace_float = float(pace)
        minutes = int(pace_float)
        seconds = int((pace_float % 1) * 60)
        return f"{minutes}:{seconds:02d}"
