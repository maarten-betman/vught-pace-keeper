from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from vught_pace_keeper.core.models import TimestampedModel


class PaceZone(TimestampedModel):
    """
    User-specific pace zones for training intensity classification.
    """

    class ZoneName(models.TextChoices):
        RECOVERY = "recovery", "Recovery"
        EASY = "easy", "Easy"
        TEMPO = "tempo", "Tempo"
        THRESHOLD = "threshold", "Threshold"
        INTERVAL = "interval", "Interval"
        REPETITION = "repetition", "Repetition"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pace_zones",
    )
    name = models.CharField(
        max_length=20,
        choices=ZoneName.choices,
    )
    min_pace_min_per_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Minimum pace in minutes per kilometer (e.g., 5.50 = 5:30/km)",
    )
    max_pace_min_per_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum pace in minutes per kilometer",
    )
    description = models.TextField(blank=True)
    color_hex = models.CharField(
        max_length=7,
        default="#808080",
        help_text="Hex color code for calendar display (e.g., #FF5733)",
    )

    class Meta:
        ordering = ["min_pace_min_per_km"]
        unique_together = ["user", "name"]
        indexes = [
            models.Index(fields=["user", "name"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_name_display()}"


class TrainingPlan(TimestampedModel):
    """
    A marathon/half-marathon training plan with configurable methodology.
    """

    class PlanType(models.TextChoices):
        HALF_MARATHON = "half_marathon", "Half Marathon"
        FULL_MARATHON = "full_marathon", "Full Marathon"

    class Methodology(models.TextChoices):
        CUSTOM = "custom", "Custom"
        PFITZINGER = "pfitzinger", "Pfitzinger"
        HANSON = "hanson", "Hanson"
        EIGHTY_TWENTY = "80_20", "80/20"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="training_plans",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
    )
    methodology = models.CharField(
        max_length=20,
        choices=Methodology.choices,
        default=Methodology.CUSTOM,
    )
    duration_weeks = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(52)],
    )
    target_race_date = models.DateField(null=True, blank=True)
    goal_time = models.DurationField(
        null=True,
        blank=True,
        help_text="Target finish time (e.g., 3:30:00 for 3h 30m)",
    )
    is_template = models.BooleanField(
        default=False,
        help_text="If True, this plan can be used as a template for others",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["is_template"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_plan_type_display()})"


class TrainingWeek(TimestampedModel):
    """
    A single week within a training plan.
    """

    class WeekFocus(models.TextChoices):
        BASE = "base", "Base Building"
        BUILD = "build", "Build Phase"
        PEAK = "peak", "Peak Phase"
        TAPER = "taper", "Taper"

    plan = models.ForeignKey(
        TrainingPlan,
        on_delete=models.CASCADE,
        related_name="weeks",
    )
    week_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    focus = models.CharField(
        max_length=10,
        choices=WeekFocus.choices,
    )
    total_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Planned total distance for the week in kilometers",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["plan", "week_number"]
        unique_together = ["plan", "week_number"]
        indexes = [
            models.Index(fields=["plan", "week_number"]),
        ]

    def __str__(self):
        return f"{self.plan.name} - Week {self.week_number}"


class ScheduledWorkout(TimestampedModel):
    """
    A planned workout within a training week.
    """

    class WorkoutType(models.TextChoices):
        EASY = "easy", "Easy Run"
        LONG = "long", "Long Run"
        TEMPO = "tempo", "Tempo Run"
        INTERVAL = "interval", "Interval Training"
        RECOVERY = "recovery", "Recovery Run"
        REST = "rest", "Rest Day"

    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, "Monday"
        TUESDAY = 2, "Tuesday"
        WEDNESDAY = 3, "Wednesday"
        THURSDAY = 4, "Thursday"
        FRIDAY = 5, "Friday"
        SATURDAY = 6, "Saturday"
        SUNDAY = 7, "Sunday"

    week = models.ForeignKey(
        TrainingWeek,
        on_delete=models.CASCADE,
        related_name="scheduled_workouts",
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=DayOfWeek.choices,
    )
    workout_type = models.CharField(
        max_length=20,
        choices=WorkoutType.choices,
    )
    target_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    target_duration = models.DurationField(
        null=True,
        blank=True,
        help_text="Target workout duration",
    )
    target_pace_min_per_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target pace in minutes per kilometer",
    )
    pace_zone = models.ForeignKey(
        PaceZone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_workouts",
    )
    description = models.TextField(blank=True)
    order_in_day = models.PositiveSmallIntegerField(
        default=1,
        help_text="Order if multiple workouts on same day",
    )

    class Meta:
        ordering = ["week", "day_of_week", "order_in_day"]
        indexes = [
            models.Index(fields=["week", "day_of_week"]),
        ]

    def __str__(self):
        return f"{self.week} - {self.get_day_of_week_display()} - {self.get_workout_type_display()}"


class CompletedWorkout(TimestampedModel):
    """
    An actual completed workout, optionally linked to a scheduled workout.
    """

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual Entry"
        GPX_UPLOAD = "gpx_upload", "GPX Upload"
        STRAVA = "strava", "Strava Import"

    scheduled_workout = models.ForeignKey(
        ScheduledWorkout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completions",
        help_text="Linked scheduled workout (null for unplanned runs)",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="completed_workouts",
    )
    date = models.DateField()
    actual_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )
    actual_duration = models.DurationField()
    average_pace_min_per_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Average pace in minutes per kilometer",
    )
    average_heart_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Average heart rate in BPM",
    )
    elevation_gain_m = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total elevation gain in meters",
    )
    # GeoDjango field for route geometry
    route = gis_models.LineStringField(
        srid=4326,  # WGS84 - standard GPS coordinate system
        null=True,
        blank=True,
        help_text="GPS route as LineString geometry",
    )
    gpx_file = models.FileField(
        upload_to="gpx_files/%Y/%m/",
        null=True,
        blank=True,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    strava_activity_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        help_text="Strava activity ID for deduplication",
    )
    perceived_effort = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Perceived effort on 1-10 scale",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-date"]),
            models.Index(fields=["user", "date"]),
            models.Index(fields=["strava_activity_id"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.actual_distance_km}km"
