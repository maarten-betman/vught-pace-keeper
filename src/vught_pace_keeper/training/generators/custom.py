"""Custom plan generator for user-defined training plans."""

from decimal import Decimal

from .base import (
    BasePlanGenerator,
    GeneratedPlan,
    GeneratedWeek,
    GeneratedWorkout,
    PlanConfig,
)
from .registry import register_generator


@register_generator
class CustomPlanGenerator(BasePlanGenerator):
    """
    Generator for custom user-defined training plans.

    Creates a balanced plan structure with progressive loading:
    - Base phase (25%): Building aerobic foundation
    - Build phase (35%): Increasing volume and adding quality
    - Peak phase (25%): Highest volume with key workouts
    - Taper phase (15%): Reducing volume before race
    """

    methodology_name = "custom"
    display_name = "Custom Plan"
    description = "Create your own week-by-week training structure"
    supported_distances = ["half_marathon", "full_marathon"]
    min_weeks = {"half_marathon": 8, "full_marathon": 12}
    max_weeks = {"half_marathon": 20, "full_marathon": 30}

    # Base weekly distances for starting point (km)
    BASE_WEEKLY_KM = {
        "half_marathon": Decimal("30"),
        "full_marathon": Decimal("45"),
    }

    # Weekly volume multipliers by phase
    PHASE_MULTIPLIERS = {
        "base": Decimal("0.80"),
        "build": Decimal("1.00"),
        "peak": Decimal("1.15"),
        "taper": Decimal("0.60"),
    }

    # Workout descriptions
    WORKOUT_DESCRIPTIONS = {
        "easy": "Easy effort, conversational pace",
        "long": "Long run - focus on time on feet",
        "tempo": "Comfortably hard, sustainable effort",
        "interval": "Hard efforts with recovery intervals",
        "recovery": "Very easy recovery run",
        "rest": "Rest day - optional stretching or cross-training",
    }

    def generate_plan(self, config: PlanConfig) -> GeneratedPlan:
        """Generate a custom training plan scaffold."""
        weeks_available = self.calculate_weeks_until_race(config.race_date)

        # Cap at max weeks for the distance
        max_w = self.max_weeks.get(config.plan_type, 16)
        duration = min(weeks_available, max_w)

        # Generate each week
        weeks = []
        for week_num in range(1, duration + 1):
            focus = self.get_week_focus(week_num, duration)
            week = self._generate_week(week_num, focus, config.plan_type, duration)
            weeks.append(week)

        # Generate plan name if not provided
        plan_name = config.name or self._generate_plan_name(duration, config.plan_type)

        return GeneratedPlan(
            name=plan_name,
            description=f"Custom {config.plan_type.replace('_', ' ')} training plan",
            plan_type=config.plan_type,
            methodology=self.methodology_name,
            duration_weeks=duration,
            weeks=weeks,
        )

    def get_week_focus(self, week_number: int, total_weeks: int) -> str:
        """
        Determine week focus based on position in plan.

        Distribution:
        - Base: 25% (weeks 1 to ~25%)
        - Build: 35% (weeks ~25% to ~60%)
        - Peak: 25% (weeks ~60% to ~85%)
        - Taper: 15% (weeks ~85% to 100%)
        """
        progress = week_number / total_weeks

        if progress <= 0.25:
            return "base"
        elif progress <= 0.60:
            return "build"
        elif progress <= 0.85:
            return "peak"
        else:
            return "taper"

    def _generate_plan_name(self, duration: int, plan_type: str) -> str:
        """Generate a default plan name."""
        distance = "Half Marathon" if plan_type == "half_marathon" else "Marathon"
        return f"{duration}-Week {distance} Plan"

    def _generate_week(
        self,
        week_num: int,
        focus: str,
        plan_type: str,
        total_weeks: int,
    ) -> GeneratedWeek:
        """Generate a single week structure."""
        base_km = self.BASE_WEEKLY_KM.get(plan_type, Decimal("30"))
        multiplier = self.PHASE_MULTIPLIERS.get(focus, Decimal("1.0"))

        # Progressive build within phases (slight increase each week)
        phase_progress = self._get_phase_progress(week_num, total_weeks, focus)
        week_km = base_km * multiplier * (Decimal("0.9") + phase_progress * Decimal("0.2"))

        workouts = self._generate_week_workouts(focus, week_km, plan_type)

        return GeneratedWeek(
            week_number=week_num,
            focus=focus,
            total_distance_km=week_km.quantize(Decimal("0.1")),
            workouts=workouts,
            notes=self._get_week_notes(focus, week_num, total_weeks),
        )

    def _generate_week_workouts(
        self,
        focus: str,
        total_km: Decimal,
        plan_type: str,
    ) -> list[GeneratedWorkout]:
        """Generate workout structure for a week based on focus phase."""
        # Define weekly structure by focus
        # Format: (day, workout_type, fraction_of_weekly_km or None for rest)
        structures = {
            "base": [
                (1, "easy", Decimal("0.20")),  # Monday
                (2, "rest", None),  # Tuesday
                (3, "easy", Decimal("0.18")),  # Wednesday
                (4, "rest", None),  # Thursday
                (5, "easy", Decimal("0.15")),  # Friday
                (6, "rest", None),  # Saturday
                (7, "long", Decimal("0.35")),  # Sunday
            ],
            "build": [
                (1, "easy", Decimal("0.15")),
                (2, "tempo", Decimal("0.15")),
                (3, "easy", Decimal("0.12")),
                (4, "rest", None),
                (5, "easy", Decimal("0.12")),
                (6, "recovery", Decimal("0.08")),
                (7, "long", Decimal("0.38")),
            ],
            "peak": [
                (1, "easy", Decimal("0.12")),
                (2, "tempo", Decimal("0.15")),
                (3, "easy", Decimal("0.10")),
                (4, "interval", Decimal("0.12")),
                (5, "recovery", Decimal("0.08")),
                (6, "rest", None),
                (7, "long", Decimal("0.43")),
            ],
            "taper": [
                (1, "easy", Decimal("0.18")),
                (2, "rest", None),
                (3, "easy", Decimal("0.15")),
                (4, "rest", None),
                (5, "easy", Decimal("0.12")),
                (6, "rest", None),
                (7, "long", Decimal("0.30")),
            ],
        }

        structure = structures.get(focus, structures["base"])
        workouts = []

        for day, workout_type, fraction in structure:
            distance = None
            if fraction is not None:
                distance = (total_km * fraction).quantize(Decimal("0.1"))

            workouts.append(
                GeneratedWorkout(
                    day_of_week=day,
                    workout_type=workout_type,
                    target_distance_km=distance,
                    description=self.WORKOUT_DESCRIPTIONS.get(workout_type, ""),
                )
            )

        return workouts

    def _get_phase_progress(
        self,
        week_num: int,
        total_weeks: int,
        focus: str,
    ) -> Decimal:
        """
        Calculate progress within the current phase (0.0 to 1.0).

        Used for progressive loading within a phase.
        """
        # Simple linear progression based on overall plan progress
        progress = Decimal(str(week_num / total_weeks))
        return min(progress, Decimal("1.0"))

    def _get_week_notes(self, focus: str, week_num: int, total_weeks: int) -> str:
        """Get contextual notes for a week based on focus and position."""
        base_notes = {
            "base": "Focus on building aerobic base. Keep all runs at conversational pace.",
            "build": "Building volume with quality sessions. Listen to your body.",
            "peak": "Peak training block. Prioritize recovery between hard efforts.",
            "taper": "Reducing volume to arrive fresh at race day. Trust your training.",
        }

        note = base_notes.get(focus, "")

        # Add race week note
        if week_num == total_weeks:
            note = "Race week! Keep runs short and easy. Focus on rest and nutrition."

        return note
