"""Analytics service for training data aggregation and reporting."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncWeek

from vught_pace_keeper.training.models import (
    CompletedWorkout,
    PaceZone,
    ScheduledWorkout,
    TrainingPlan,
    TrainingWeek,
)


@dataclass
class WeeklySummary:
    """Summary statistics for a single week."""

    week_start: date
    week_end: date
    actual_distance_km: Decimal
    planned_distance_km: Optional[Decimal]
    workouts_completed: int
    workouts_scheduled: int
    average_pace: Optional[Decimal]
    completion_percentage: float


@dataclass
class PlanAdherence:
    """Plan adherence metrics."""

    total_scheduled: int
    total_completed: int
    completion_rate: float
    distance_planned_km: Decimal
    distance_actual_km: Decimal
    distance_adherence: float
    missed_workouts: int


@dataclass
class ZoneDistribution:
    """Time/distance spent in each pace zone."""

    zone_name: str
    zone_color: str
    distance_km: Decimal
    percentage: float


@dataclass
class WeeklyTrend:
    """Weekly data point for trend charts."""

    week_start: date
    week_label: str
    actual_distance_km: Decimal
    planned_distance_km: Optional[Decimal]
    average_pace: Optional[Decimal]
    average_heart_rate: Optional[int]


class TrainingAnalyticsService:
    """Service class for computing training analytics."""

    def __init__(self, user):
        self.user = user

    def get_weekly_summary(self, week_start: Optional[date] = None) -> WeeklySummary:
        """Get summary for a specific week (defaults to current week)."""
        if week_start is None:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())

        week_end = week_start + timedelta(days=6)

        # Get completed workouts this week
        completed = CompletedWorkout.objects.filter(
            user=self.user,
            date__gte=week_start,
            date__lte=week_end,
        ).aggregate(
            total_distance=Sum("actual_distance_km"),
            workout_count=Count("id"),
            avg_pace=Avg("average_pace_min_per_km"),
        )

        # Get scheduled workouts for active plan this week
        scheduled_data = self._get_scheduled_for_week(week_start, week_end)

        actual_distance = completed["total_distance"] or Decimal("0")
        planned_distance = scheduled_data["planned_distance"]
        workouts_completed = completed["workout_count"] or 0
        workouts_scheduled = scheduled_data["scheduled_count"]

        completion_pct = 0.0
        if workouts_scheduled > 0:
            completion_pct = (workouts_completed / workouts_scheduled) * 100

        return WeeklySummary(
            week_start=week_start,
            week_end=week_end,
            actual_distance_km=actual_distance,
            planned_distance_km=planned_distance,
            workouts_completed=workouts_completed,
            workouts_scheduled=workouts_scheduled,
            average_pace=completed["avg_pace"],
            completion_percentage=min(completion_pct, 100.0),
        )

    def get_plan_adherence(
        self,
        plan: Optional[TrainingPlan] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> PlanAdherence:
        """Calculate plan adherence metrics."""
        if plan is None:
            plan = (
                TrainingPlan.objects.filter(
                    user=self.user,
                    is_template=False,
                )
                .order_by("-created_at")
                .first()
            )

        if plan is None:
            return PlanAdherence(
                total_scheduled=0,
                total_completed=0,
                completion_rate=0.0,
                distance_planned_km=Decimal("0"),
                distance_actual_km=Decimal("0"),
                distance_adherence=0.0,
                missed_workouts=0,
            )

        # Get all scheduled workouts for this plan (excluding rest days)
        scheduled_qs = ScheduledWorkout.objects.filter(week__plan=plan).exclude(
            workout_type="rest"
        )

        total_scheduled = scheduled_qs.count()
        distance_planned = scheduled_qs.aggregate(total=Sum("target_distance_km"))[
            "total"
        ] or Decimal("0")

        # Get completions linked to this plan
        completed_qs = CompletedWorkout.objects.filter(
            user=self.user,
            scheduled_workout__week__plan=plan,
        )

        if date_from:
            completed_qs = completed_qs.filter(date__gte=date_from)
        if date_to:
            completed_qs = completed_qs.filter(date__lte=date_to)

        completed_data = completed_qs.aggregate(
            count=Count("id"),
            total_distance=Sum("actual_distance_km"),
        )

        total_completed = completed_data["count"] or 0
        distance_actual = completed_data["total_distance"] or Decimal("0")

        completion_rate = 0.0
        if total_scheduled > 0:
            completion_rate = (total_completed / total_scheduled) * 100

        distance_adherence = 0.0
        if distance_planned > 0:
            distance_adherence = float(distance_actual / distance_planned) * 100

        return PlanAdherence(
            total_scheduled=total_scheduled,
            total_completed=total_completed,
            completion_rate=completion_rate,
            distance_planned_km=distance_planned,
            distance_actual_km=distance_actual,
            distance_adherence=min(distance_adherence, 100.0),
            missed_workouts=max(0, total_scheduled - total_completed),
        )

    def get_zone_distribution(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list[ZoneDistribution]:
        """Calculate distance spent in each pace zone."""
        zones = PaceZone.objects.filter(user=self.user).order_by("min_pace_min_per_km")

        if not zones.exists():
            return []

        workouts_qs = CompletedWorkout.objects.filter(user=self.user)
        if date_from:
            workouts_qs = workouts_qs.filter(date__gte=date_from)
        if date_to:
            workouts_qs = workouts_qs.filter(date__lte=date_to)

        # Categorize each workout by zone
        zone_totals = {zone.name: Decimal("0") for zone in zones}
        total_distance = Decimal("0")

        for workout in workouts_qs:
            if workout.actual_distance_km:
                zone_name = self._get_zone_for_pace(
                    workout.average_pace_min_per_km, zones
                )
                if zone_name and zone_name in zone_totals:
                    zone_totals[zone_name] += workout.actual_distance_km
                    total_distance += workout.actual_distance_km

        # Build distribution list
        distribution = []
        for zone in zones:
            distance = zone_totals.get(zone.name, Decimal("0"))
            pct = 0.0
            if total_distance > 0:
                pct = float(distance / total_distance) * 100

            distribution.append(
                ZoneDistribution(
                    zone_name=zone.get_name_display(),
                    zone_color=zone.color_hex,
                    distance_km=distance,
                    percentage=round(pct, 1),
                )
            )

        return distribution

    def get_weekly_trends(
        self,
        weeks: int = 12,
        plan: Optional[TrainingPlan] = None,
    ) -> list[WeeklyTrend]:
        """Get weekly distance and pace trends for charts."""
        today = date.today()
        start_date = today - timedelta(weeks=weeks)

        # Get completed workouts grouped by week
        workouts = (
            CompletedWorkout.objects.filter(
                user=self.user,
                date__gte=start_date,
            )
            .annotate(week=TruncWeek("date"))
            .values("week")
            .annotate(
                total_distance=Sum("actual_distance_km"),
                avg_pace=Avg("average_pace_min_per_km"),
                avg_hr=Avg("average_heart_rate"),
            )
            .order_by("week")
        )

        # TruncWeek may return date or datetime depending on DB backend
        workout_by_week = {}
        for w in workouts:
            week_val = w["week"]
            if hasattr(week_val, "date"):
                week_key = week_val.date()
            else:
                week_key = week_val
            workout_by_week[week_key] = w

        # Get plan info for planned distances
        active_plan = plan
        if not active_plan:
            active_plan = (
                TrainingPlan.objects.filter(
                    user=self.user,
                    is_template=False,
                )
                .order_by("-created_at")
                .first()
            )

        # Calculate plan start date and get weekly distances
        plan_start = None
        plan_end = None
        planned_weekly = {}
        if active_plan and active_plan.target_race_date and active_plan.duration_weeks:
            plan_start = active_plan.target_race_date - timedelta(
                weeks=active_plan.duration_weeks
            )
            # Align to Monday
            plan_start = plan_start - timedelta(days=plan_start.weekday())
            plan_end = active_plan.target_race_date

            # Get weekly distances keyed by week number
            weeks_data = TrainingWeek.objects.filter(plan=active_plan).values(
                "week_number", "total_distance_km"
            )
            planned_weekly = {w["week_number"]: w["total_distance_km"] for w in weeks_data}

        # Build weekly data
        trends = []
        current = start_date - timedelta(days=start_date.weekday())  # Monday

        while current <= today:
            week_data = workout_by_week.get(current, {})

            actual = Decimal(str(week_data.get("total_distance", 0) or 0))

            # Only show planned if this week falls within the plan period
            planned = None
            if plan_start and plan_end and plan_start <= current <= plan_end:
                training_week_num = (current - plan_start).days // 7 + 1
                planned = planned_weekly.get(training_week_num)

            # Get average HR, round to int if present
            avg_hr = week_data.get("avg_hr")
            if avg_hr is not None:
                avg_hr = int(round(avg_hr))

            trends.append(
                WeeklyTrend(
                    week_start=current,
                    week_label=current.strftime("%b %d"),
                    actual_distance_km=actual,
                    planned_distance_km=planned,
                    average_pace=week_data.get("avg_pace"),
                    average_heart_rate=avg_hr,
                )
            )

            current += timedelta(weeks=1)

        return trends

    def _get_scheduled_for_week(self, week_start: date, week_end: date) -> dict:
        """Get scheduled workout data for a calendar week."""
        active_plan = (
            TrainingPlan.objects.filter(
                user=self.user,
                is_template=False,
            )
            .order_by("-created_at")
            .first()
        )

        if not active_plan:
            return {"planned_distance": None, "scheduled_count": 0}

        # Calculate which training week this corresponds to
        # Start date = target_race_date - duration_weeks
        plan_start = None
        if active_plan.target_race_date and active_plan.duration_weeks:
            plan_start = active_plan.target_race_date - timedelta(
                weeks=active_plan.duration_weeks
            )

        if plan_start and week_start >= plan_start:
            weeks_elapsed = (week_start - plan_start).days // 7 + 1

            # Get the training week
            training_week = TrainingWeek.objects.filter(
                plan=active_plan, week_number=weeks_elapsed
            ).first()

            if training_week:
                scheduled_count = (
                    ScheduledWorkout.objects.filter(week=training_week)
                    .exclude(workout_type="rest")
                    .count()
                )
                return {
                    "planned_distance": training_week.total_distance_km,
                    "scheduled_count": scheduled_count,
                }

        # Fallback: average from plan
        total_scheduled = (
            ScheduledWorkout.objects.filter(week__plan=active_plan)
            .exclude(workout_type="rest")
            .count()
        )
        total_distance = TrainingWeek.objects.filter(plan=active_plan).aggregate(
            total=Sum("total_distance_km")
        )["total"]

        duration = active_plan.duration_weeks or 1
        weekly_avg_scheduled = total_scheduled / duration
        weekly_avg_distance = total_distance / duration if total_distance else None

        return {
            "planned_distance": weekly_avg_distance,
            "scheduled_count": int(weekly_avg_scheduled),
        }

    def _get_zone_for_pace(self, pace: Optional[Decimal], zones) -> Optional[str]:
        """Determine which zone a pace falls into."""
        if pace is None:
            return None

        pace_float = float(pace)

        for zone in zones:
            min_pace = float(zone.min_pace_min_per_km)
            max_pace = float(zone.max_pace_min_per_km)

            # Slower pace = higher number, faster = lower
            if max_pace <= pace_float <= min_pace:
                return zone.name

        # Default to recovery if slower than all zones
        if zones.exists():
            slowest = zones.first()
            if pace_float > float(slowest.min_pace_min_per_km):
                return "recovery"

        return None
