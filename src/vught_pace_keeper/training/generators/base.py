"""Base classes and dataclasses for training plan generators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vught_pace_keeper.accounts.models import User


@dataclass
class FitnessProfile:
    """User's current fitness level for plan generation."""

    recent_weekly_km: Decimal | None = None
    recent_long_run_km: Decimal | None = None
    estimated_half_pace: timedelta | None = None  # per km
    estimated_full_pace: timedelta | None = None  # per km


@dataclass
class PlanConfig:
    """Configuration for generating a training plan."""

    user: "User"
    plan_type: str  # "half_marathon" or "full_marathon"
    race_date: date
    goal_time: timedelta | None = None
    fitness: FitnessProfile | None = None
    name: str = ""


@dataclass
class GeneratedWorkout:
    """Preview data for a generated workout."""

    day_of_week: int  # 1-7 (Monday-Sunday)
    workout_type: str  # easy, long, tempo, interval, recovery, rest
    target_distance_km: Decimal | None = None
    target_duration: timedelta | None = None
    target_pace_min_per_km: Decimal | None = None
    description: str = ""


@dataclass
class GeneratedWeek:
    """Preview data for a generated week."""

    week_number: int
    focus: str  # base, build, peak, taper
    total_distance_km: Decimal
    workouts: list[GeneratedWorkout] = field(default_factory=list)
    notes: str = ""


@dataclass
class GeneratedPlan:
    """Preview of a complete plan before saving to database."""

    name: str
    description: str
    plan_type: str
    methodology: str
    duration_weeks: int
    weeks: list[GeneratedWeek] = field(default_factory=list)


class BasePlanGenerator(ABC):
    """
    Abstract base class for training plan generators.

    To create a new generator:
    1. Subclass BasePlanGenerator
    2. Set class attributes (methodology_name, display_name, etc.)
    3. Implement generate_plan() and get_week_focus()
    4. Decorate with @register_generator
    """

    # Class attributes to be defined by subclasses
    methodology_name: str = ""
    display_name: str = ""
    description: str = ""
    supported_distances: list[str] = []  # ["half_marathon", "full_marathon"]
    min_weeks: dict[str, int] = {}  # {"half_marathon": 8, "full_marathon": 12}
    max_weeks: dict[str, int] = {}  # {"half_marathon": 20, "full_marathon": 30}

    @abstractmethod
    def generate_plan(self, config: PlanConfig) -> GeneratedPlan:
        """
        Generate a training plan based on the configuration.

        Returns a GeneratedPlan dataclass for preview.
        Does NOT save to database - that's handled by the view.
        """
        pass

    @abstractmethod
    def get_week_focus(self, week_number: int, total_weeks: int) -> str:
        """
        Determine the training focus for a given week.

        Args:
            week_number: Current week (1-indexed)
            total_weeks: Total weeks in the plan

        Returns:
            One of: "base", "build", "peak", "taper"
        """
        pass

    def calculate_weeks_until_race(self, race_date: date) -> int:
        """Calculate full weeks from today until race date."""
        today = date.today()
        delta = race_date - today
        return delta.days // 7

    def validate_config(self, config: PlanConfig) -> list[str]:
        """
        Validate plan configuration.

        Returns list of validation error messages (empty if valid).
        """
        errors = []
        weeks = self.calculate_weeks_until_race(config.race_date)

        # Check supported distance
        if config.plan_type not in self.supported_distances:
            errors.append(
                f"This generator does not support {config.plan_type.replace('_', ' ')}"
            )
            return errors  # Can't validate further without valid plan_type

        # Check minimum weeks
        min_w = self.min_weeks.get(config.plan_type, 8)
        if weeks < min_w:
            errors.append(
                f"At least {min_w} weeks required for "
                f"{config.plan_type.replace('_', ' ')}. "
                f"You have {weeks} weeks until race day."
            )

        # Check maximum weeks
        max_w = self.max_weeks.get(config.plan_type, 30)
        if weeks > max_w:
            # This is a warning, not an error - plan will be capped
            pass

        # Validate goal time if provided
        if config.goal_time:
            errors.extend(self._validate_goal_time(config.goal_time, config.plan_type))

        return errors

    def _validate_goal_time(
        self, goal_time: timedelta, plan_type: str
    ) -> list[str]:
        """Validate goal time is reasonable for the distance."""
        errors = []

        if plan_type == "half_marathon":
            if goal_time < timedelta(hours=1):
                errors.append(
                    "Half marathon goal time under 1 hour is faster than "
                    "the world record. Please enter a realistic goal."
                )
            elif goal_time > timedelta(hours=4):
                errors.append(
                    "Half marathon goal time over 4 hours exceeds typical "
                    "race cutoffs. Consider a more achievable goal."
                )
        elif plan_type == "full_marathon":
            if goal_time < timedelta(hours=2):
                errors.append(
                    "Marathon goal time under 2 hours is faster than "
                    "the world record. Please enter a realistic goal."
                )
            elif goal_time > timedelta(hours=7):
                errors.append(
                    "Marathon goal time over 7 hours exceeds typical "
                    "race cutoffs. Consider a more achievable goal."
                )

        return errors
