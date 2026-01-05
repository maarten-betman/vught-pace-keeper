"""Training load calculation service (TSS, ATL, CTL, TSB)."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from django.db.models import Sum

from vught_pace_keeper.training.models import (
    CompletedWorkout,
    TrainingLoad,
    UserFitnessSettings,
)

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


# Exponential decay constants
ATL_DECAY = 7  # Acute Training Load time constant (days)
CTL_DECAY = 42  # Chronic Training Load time constant (days)

# Default threshold pace if user hasn't set one (5:00/km in decimal)
DEFAULT_THRESHOLD_PACE = Decimal("5.00")


@dataclass
class TrainingLoadSummary:
    """Summary of current training load status."""

    current_tss: Decimal
    atl: Decimal
    ctl: Decimal
    tsb: Decimal
    form_status: str
    form_color: str
    weekly_tss: Decimal
    weekly_target: int
    weekly_progress_percent: int
    fitness_trend: str  # "improving", "maintaining", "declining"


class TrainingLoadService:
    """Service for calculating and managing training load metrics."""

    def __init__(self, user: "User"):
        self.user = user
        self._settings: Optional[UserFitnessSettings] = None

    @property
    def settings(self) -> UserFitnessSettings:
        """Get or create user's fitness settings."""
        if self._settings is None:
            self._settings, _ = UserFitnessSettings.objects.get_or_create(
                user=self.user
            )
        return self._settings

    def calculate_workout_tss(self, workout: CompletedWorkout) -> Decimal:
        """
        Calculate Training Stress Score for a single workout.

        TSS = (duration_hours) * (intensity_factor)² * 100

        Intensity Factor (IF) = threshold_pace / actual_pace
        - IF > 1.0 means workout is harder than threshold
        - IF < 1.0 means workout is easier than threshold
        """
        if not workout.actual_duration or not workout.average_pace_min_per_km:
            return Decimal("0")

        threshold_pace = self.settings.threshold_pace or DEFAULT_THRESHOLD_PACE
        actual_pace = workout.average_pace_min_per_km

        # Calculate intensity factor
        # Lower pace = faster, so IF = threshold/actual
        # If actual pace is faster (lower) than threshold, IF > 1
        if actual_pace <= 0:
            return Decimal("0")

        intensity_factor = threshold_pace / actual_pace

        # Duration in hours
        duration_hours = Decimal(str(workout.actual_duration.total_seconds() / 3600))

        # TSS formula
        tss = duration_hours * (intensity_factor ** 2) * Decimal("100")

        return tss.quantize(Decimal("0.01"))

    def calculate_daily_tss(self, day: date) -> Decimal:
        """Calculate total TSS for all workouts on a given day."""
        workouts = CompletedWorkout.objects.filter(
            user=self.user,
            date=day,
        )

        total_tss = Decimal("0")
        for workout in workouts:
            total_tss += self.calculate_workout_tss(workout)

        return total_tss.quantize(Decimal("0.01"))

    def update_training_load(self, day: date) -> TrainingLoad:
        """
        Calculate and store training load for a specific day.

        Uses exponentially weighted moving averages:
        - ATL (Acute) = previous_ATL + (daily_TSS - previous_ATL) * (1 - e^(-1/7))
        - CTL (Chronic) = previous_CTL + (daily_TSS - previous_CTL) * (1 - e^(-1/42))
        - TSB = CTL - ATL
        """
        import math

        # Calculate daily TSS
        daily_tss = self.calculate_daily_tss(day)

        # Get previous day's load (if exists)
        previous_day = day - timedelta(days=1)
        try:
            previous_load = TrainingLoad.objects.get(user=self.user, date=previous_day)
            prev_atl = previous_load.atl
            prev_ctl = previous_load.ctl
        except TrainingLoad.DoesNotExist:
            # Bootstrap with zeros or look back further
            prev_atl = Decimal("0")
            prev_ctl = Decimal("0")

        # Exponential decay factors
        atl_factor = Decimal(str(1 - math.exp(-1 / ATL_DECAY)))
        ctl_factor = Decimal(str(1 - math.exp(-1 / CTL_DECAY)))

        # Calculate new ATL and CTL
        new_atl = prev_atl + (daily_tss - prev_atl) * atl_factor
        new_ctl = prev_ctl + (daily_tss - prev_ctl) * ctl_factor
        new_tsb = new_ctl - new_atl

        # Round to 2 decimal places
        new_atl = new_atl.quantize(Decimal("0.01"))
        new_ctl = new_ctl.quantize(Decimal("0.01"))
        new_tsb = new_tsb.quantize(Decimal("0.01"))

        # Create or update the training load record
        load, _ = TrainingLoad.objects.update_or_create(
            user=self.user,
            date=day,
            defaults={
                "daily_tss": daily_tss,
                "atl": new_atl,
                "ctl": new_ctl,
                "tsb": new_tsb,
            },
        )

        return load

    def recalculate_from_date(self, start_date: date) -> int:
        """
        Recalculate all training loads from a given date to today.

        Returns the number of days recalculated.
        """
        today = date.today()
        current = start_date
        count = 0

        while current <= today:
            self.update_training_load(current)
            current += timedelta(days=1)
            count += 1

        return count

    def backfill_historical_data(self, days_back: int = 90) -> int:
        """
        Backfill training load data from historical workouts.

        Args:
            days_back: Number of days to look back

        Returns:
            Number of days processed
        """
        start_date = date.today() - timedelta(days=days_back)
        return self.recalculate_from_date(start_date)

    def get_current_load(self) -> Optional[TrainingLoad]:
        """Get the most recent training load record."""
        return TrainingLoad.objects.filter(user=self.user).first()

    def get_load_history(self, days: int = 42) -> list[TrainingLoad]:
        """Get training load history for the specified number of days."""
        start_date = date.today() - timedelta(days=days)
        return list(
            TrainingLoad.objects.filter(
                user=self.user,
                date__gte=start_date,
            ).order_by("date")
        )

    def get_weekly_tss(self) -> Decimal:
        """Get total TSS for the current week (Monday to today)."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())

        result = TrainingLoad.objects.filter(
            user=self.user,
            date__gte=monday,
            date__lte=today,
        ).aggregate(total=Sum("daily_tss"))

        return result["total"] or Decimal("0")

    def get_summary(self) -> TrainingLoadSummary:
        """Get a complete summary of current training load status."""
        current_load = self.get_current_load()

        if current_load:
            current_tss = current_load.daily_tss
            atl = current_load.atl
            ctl = current_load.ctl
            tsb = current_load.tsb
            form_status = current_load.form_status
            form_color = current_load.form_color
        else:
            current_tss = Decimal("0")
            atl = Decimal("0")
            ctl = Decimal("0")
            tsb = Decimal("0")
            form_status = "No Data"
            form_color = "#9ca3af"

        weekly_tss = self.get_weekly_tss()
        weekly_target = self.settings.target_weekly_tss

        if weekly_target > 0:
            weekly_progress = int((weekly_tss / Decimal(weekly_target)) * 100)
        else:
            weekly_progress = 0

        # Determine fitness trend from CTL changes
        fitness_trend = self._calculate_fitness_trend()

        return TrainingLoadSummary(
            current_tss=current_tss,
            atl=atl,
            ctl=ctl,
            tsb=tsb,
            form_status=form_status,
            form_color=form_color,
            weekly_tss=weekly_tss,
            weekly_target=weekly_target,
            weekly_progress_percent=min(weekly_progress, 100),
            fitness_trend=fitness_trend,
        )

    def _calculate_fitness_trend(self) -> str:
        """Calculate whether fitness (CTL) is improving, maintaining, or declining."""
        # Compare CTL from 7 days ago to today
        today = date.today()
        week_ago = today - timedelta(days=7)

        try:
            current = TrainingLoad.objects.get(user=self.user, date=today)
            past = TrainingLoad.objects.get(user=self.user, date=week_ago)

            diff = current.ctl - past.ctl
            if diff > 2:
                return "improving"
            elif diff < -2:
                return "declining"
            else:
                return "maintaining"
        except TrainingLoad.DoesNotExist:
            return "unknown"

    def get_chart_data(self, days: int = 42) -> dict:
        """Get training load data formatted for Chart.js."""
        history = self.get_load_history(days)

        return {
            "labels": [load.date.isoformat() for load in history],
            "tss": [float(load.daily_tss) for load in history],
            "atl": [float(load.atl) for load in history],
            "ctl": [float(load.ctl) for load in history],
            "tsb": [float(load.tsb) for load in history],
        }
