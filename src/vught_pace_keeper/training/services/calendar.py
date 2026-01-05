"""Calendar service for training plan visualization."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Sum

from vught_pace_keeper.training.models import (
    CompletedWorkout,
    ScheduledWorkout,
    TrainingPlan,
    TrainingWeek,
)


@dataclass
class CalendarDay:
    """Data for a single calendar day."""

    date: date
    scheduled_workouts: list = field(default_factory=list)
    completed_workouts: list = field(default_factory=list)
    is_today: bool = False
    is_current_month: bool = True
    zone_color: Optional[str] = None
    total_distance_km: Decimal = Decimal("0")
    status: str = "empty"  # completed, partial, missed, planned, rest, empty

    @property
    def has_workouts(self) -> bool:
        return bool(self.scheduled_workouts or self.completed_workouts)


@dataclass
class CalendarWeek:
    """Data for a calendar week."""

    week_number: int
    days: list
    total_planned_km: Decimal = Decimal("0")
    total_actual_km: Decimal = Decimal("0")
    training_week: Optional[TrainingWeek] = None


class CalendarService:
    """Service for generating calendar data."""

    # Zone colors for workout types
    WORKOUT_COLORS = {
        "easy": "#22c55e",      # green
        "long": "#3b82f6",      # blue
        "tempo": "#f59e0b",     # amber
        "interval": "#ef4444",  # red
        "recovery": "#9ca3af",  # gray
        "rest": "#e5e7eb",      # light gray
    }

    def __init__(self, user):
        self.user = user

    def get_month_data(self, year: int, month: int) -> list[CalendarWeek]:
        """Get calendar data for a full month."""
        # Find first day of month and last day
        first_of_month = date(year, month, 1)
        if month == 12:
            last_of_month = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_of_month = date(year, month + 1, 1) - timedelta(days=1)

        # Extend to full weeks (Monday = 0)
        start_date = first_of_month - timedelta(days=first_of_month.weekday())
        end_date = last_of_month + timedelta(days=(6 - last_of_month.weekday()))

        # Get scheduled workouts mapped to dates
        scheduled_by_date = self._get_scheduled_workouts_by_date(start_date, end_date)

        # Get completed workouts
        completed_by_date = self._get_completed_workouts_by_date(start_date, end_date)

        # Build weeks
        weeks = []
        current_date = start_date
        today = date.today()

        while current_date <= end_date:
            week_days = []
            week_planned = Decimal("0")
            week_actual = Decimal("0")

            for _ in range(7):
                scheduled = scheduled_by_date.get(current_date, [])
                completed = completed_by_date.get(current_date, [])

                # Calculate totals
                planned_km = sum(
                    w.target_distance_km or Decimal("0") for w in scheduled
                )
                actual_km = sum(
                    w.actual_distance_km or Decimal("0") for w in completed
                )

                # Determine status
                status = self._determine_day_status(scheduled, completed, current_date, today)

                # Get zone color
                zone_color = self._get_zone_color(scheduled, completed)

                day = CalendarDay(
                    date=current_date,
                    scheduled_workouts=scheduled,
                    completed_workouts=completed,
                    is_today=(current_date == today),
                    is_current_month=(current_date.month == month),
                    zone_color=zone_color,
                    total_distance_km=actual_km if actual_km else planned_km,
                    status=status,
                )

                week_days.append(day)
                week_planned += planned_km
                week_actual += actual_km
                current_date += timedelta(days=1)

            week = CalendarWeek(
                week_number=week_days[0].date.isocalendar()[1],
                days=week_days,
                total_planned_km=week_planned,
                total_actual_km=week_actual,
            )
            weeks.append(week)

        return weeks

    def get_day_data(self, day: date) -> CalendarDay:
        """Get detailed data for a specific day."""
        scheduled_by_date = self._get_scheduled_workouts_by_date(day, day)
        completed_by_date = self._get_completed_workouts_by_date(day, day)

        scheduled = scheduled_by_date.get(day, [])
        completed = completed_by_date.get(day, [])
        today = date.today()

        actual_km = sum(w.actual_distance_km or Decimal("0") for w in completed)
        planned_km = sum(w.target_distance_km or Decimal("0") for w in scheduled)

        return CalendarDay(
            date=day,
            scheduled_workouts=scheduled,
            completed_workouts=completed,
            is_today=(day == today),
            is_current_month=True,
            zone_color=self._get_zone_color(scheduled, completed),
            total_distance_km=actual_km if actual_km else planned_km,
            status=self._determine_day_status(scheduled, completed, day, today),
        )

    def _get_scheduled_workouts_by_date(
        self, start_date: date, end_date: date
    ) -> dict[date, list]:
        """Map scheduled workouts to calendar dates."""
        result: dict[date, list] = {}

        # Get active plans for user
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

                for workout in week.scheduled_workouts.all():
                    workout_date = week_start + timedelta(days=workout.day_of_week - 1)

                    if start_date <= workout_date <= end_date:
                        if workout_date not in result:
                            result[workout_date] = []
                        result[workout_date].append(workout)

        return result

    def _get_completed_workouts_by_date(
        self, start_date: date, end_date: date
    ) -> dict[date, list]:
        """Get completed workouts grouped by date."""
        result: dict[date, list] = {}

        workouts = CompletedWorkout.objects.filter(
            user=self.user,
            date__gte=start_date,
            date__lte=end_date,
        ).select_related("scheduled_workout")

        for workout in workouts:
            if workout.date not in result:
                result[workout.date] = []
            result[workout.date].append(workout)

        return result

    def _determine_day_status(
        self,
        scheduled: list,
        completed: list,
        day: date,
        today: date,
    ) -> str:
        """Determine the status of a calendar day."""
        has_scheduled = bool(scheduled)
        has_completed = bool(completed)

        # Check if it's a rest day
        if has_scheduled and all(w.workout_type == "rest" for w in scheduled):
            return "rest"

        if not has_scheduled and not has_completed:
            return "empty"

        if has_completed:
            if has_scheduled:
                # Check if all scheduled workouts have completions
                scheduled_non_rest = [w for w in scheduled if w.workout_type != "rest"]
                if len(completed) >= len(scheduled_non_rest):
                    return "completed"
                return "partial"
            return "completed"

        # Has scheduled but no completed
        if day < today:
            return "missed"
        return "planned"

    def _get_zone_color(self, scheduled: list, completed: list) -> Optional[str]:
        """Get the dominant zone color for a day."""
        # Prioritize completed workouts for color
        workouts = completed if completed else scheduled

        if not workouts:
            return None

        # Get the first non-rest workout type
        for workout in workouts:
            if hasattr(workout, "workout_type"):
                workout_type = workout.workout_type
            else:
                # CompletedWorkout - check scheduled workout or use default
                if workout.scheduled_workout:
                    workout_type = workout.scheduled_workout.workout_type
                else:
                    workout_type = "easy"

            if workout_type != "rest":
                return self.WORKOUT_COLORS.get(workout_type, "#3b82f6")

        return self.WORKOUT_COLORS.get("rest")
