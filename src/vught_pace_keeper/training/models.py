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


class ActivityStream(models.Model):
    """Time-series data for a completed workout (pace, HR, elevation over distance/time)."""

    workout = models.OneToOneField(
        CompletedWorkout,
        on_delete=models.CASCADE,
        related_name="stream",
    )
    # Store as JSON arrays - efficient for time-series data
    time_data = models.JSONField(default=list, help_text="Seconds from start")
    distance_data = models.JSONField(default=list, help_text="Meters")
    heartrate_data = models.JSONField(default=list, help_text="BPM (may contain nulls)")
    velocity_data = models.JSONField(default=list, help_text="Meters per second")
    altitude_data = models.JSONField(default=list, help_text="Meters elevation")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Activity Stream"
        verbose_name_plural = "Activity Streams"

    def __str__(self):
        return f"Stream for {self.workout}"

    @property
    def point_count(self):
        """Number of data points in the stream."""
        return len(self.time_data)


class UserFitnessSettings(TimestampedModel):
    """
    User-specific fitness settings for training load calculations.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fitness_settings",
    )
    threshold_hr = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Lactate threshold heart rate in BPM",
    )
    threshold_pace = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Threshold pace in minutes per kilometer (e.g., 4.50 = 4:30/km)",
    )
    target_weekly_tss = models.PositiveIntegerField(
        default=300,
        help_text="Target weekly Training Stress Score",
    )
    recovery_tsb_threshold = models.IntegerField(
        default=-20,
        help_text="TSB threshold below which recovery is recommended",
    )

    class Meta:
        verbose_name = "User Fitness Settings"
        verbose_name_plural = "User Fitness Settings"

    def __str__(self):
        return f"Fitness settings for {self.user.username}"


class TrainingLoad(TimestampedModel):
    """
    Daily training load metrics for a user.

    TSS (Training Stress Score) measures workout intensity relative to threshold.
    ATL (Acute Training Load) = 7-day exponentially weighted average of TSS.
    CTL (Chronic Training Load) = 42-day exponentially weighted average of TSS.
    TSB (Training Stress Balance) = CTL - ATL (positive = fresh, negative = fatigued).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="training_loads",
    )
    date = models.DateField()
    daily_tss = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Training Stress Score for this day",
    )
    atl = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Acute Training Load (7-day exponentially weighted)",
    )
    ctl = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Chronic Training Load (42-day exponentially weighted)",
    )
    tsb = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Training Stress Balance (CTL - ATL)",
    )

    class Meta:
        ordering = ["-date"]
        unique_together = ["user", "date"]
        indexes = [
            models.Index(fields=["user", "-date"]),
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.date} - TSS: {self.daily_tss}"

    @property
    def form_status(self) -> str:
        """Return a human-readable form status based on TSB."""
        if self.tsb >= 25:
            return "Very Fresh"
        elif self.tsb >= 10:
            return "Fresh"
        elif self.tsb >= -10:
            return "Neutral"
        elif self.tsb >= -25:
            return "Tired"
        else:
            return "Very Tired"

    @property
    def form_color(self) -> str:
        """Return a color code based on TSB."""
        if self.tsb >= 25:
            return "#22c55e"  # green
        elif self.tsb >= 10:
            return "#84cc16"  # lime
        elif self.tsb >= -10:
            return "#eab308"  # yellow
        elif self.tsb >= -25:
            return "#f97316"  # orange
        else:
            return "#ef4444"  # red


class PersonalRecord(TimestampedModel):
    """
    Personal best times for standard distances.
    """

    class Distance(models.TextChoices):
        ONE_K = "1k", "1K"
        FIVE_K = "5k", "5K"
        TEN_K = "10k", "10K"
        HALF_MARATHON = "half", "Half Marathon"
        MARATHON = "full", "Marathon"
        CUSTOM = "custom", "Custom Distance"

    # Standard distances in km for matching
    DISTANCE_KM = {
        "1k": 1.0,
        "5k": 5.0,
        "10k": 10.0,
        "half": 21.0975,
        "full": 42.195,
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_records",
    )
    distance = models.CharField(
        max_length=10,
        choices=Distance.choices,
    )
    custom_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance in km for custom records",
    )
    time = models.DurationField(
        help_text="Personal record time",
    )
    date = models.DateField()
    pace_min_per_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Average pace in minutes per kilometer",
    )
    source_workout = models.ForeignKey(
        CompletedWorkout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_records",
        help_text="Workout that set this record",
    )
    is_manual = models.BooleanField(
        default=False,
        help_text="True if manually entered (not auto-detected)",
    )

    class Meta:
        ordering = ["distance", "-created_at"]
        indexes = [
            models.Index(fields=["user", "distance"]),
            models.Index(fields=["user", "-date"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_distance_display()} - {self.time}"

    @property
    def distance_km(self) -> float:
        """Get distance in km."""
        if self.distance == "custom":
            return float(self.custom_distance_km) if self.custom_distance_km else 0
        return self.DISTANCE_KM.get(self.distance, 0)

    @property
    def formatted_time(self) -> str:
        """Return time formatted as H:MM:SS or MM:SS."""
        total_seconds = int(self.time.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def formatted_pace(self) -> str:
        """Return pace formatted as M:SS/km."""
        pace = float(self.pace_min_per_km)
        minutes = int(pace)
        seconds = int((pace % 1) * 60)
        return f"{minutes}:{seconds:02d}/km"


class Goal(TimestampedModel):
    """
    User training goals with progress tracking.
    """

    class GoalType(models.TextChoices):
        RACE_TIME = "race_time", "Race Time"
        WEEKLY_DISTANCE = "weekly_km", "Weekly Distance"
        MONTHLY_DISTANCE = "monthly_km", "Monthly Distance"
        PACE_IMPROVEMENT = "pace", "Pace Improvement"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ACHIEVED = "achieved", "Achieved"
        EXPIRED = "expired", "Expired"
        ABANDONED = "abandoned", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goals",
    )
    goal_type = models.CharField(
        max_length=20,
        choices=GoalType.choices,
    )
    title = models.CharField(
        max_length=200,
        help_text="Goal title (e.g., 'Sub-4 Marathon')",
    )
    # Race time goal fields
    race_distance = models.CharField(
        max_length=10,
        choices=PersonalRecord.Distance.choices,
        null=True,
        blank=True,
    )
    target_time = models.DurationField(
        null=True,
        blank=True,
        help_text="Target time for race goals",
    )
    # Distance goal fields
    target_distance_km = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target distance in km",
    )
    # Pace goal fields
    target_pace = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target pace in min/km",
    )
    # Dates
    start_date = models.DateField()
    target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Target completion date",
    )
    # Progress tracking
    current_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current progress value",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    @property
    def progress_percent(self) -> int:
        """Calculate progress percentage towards goal."""
        if self.goal_type == "race_time":
            # For race time, we compare current PR to target
            # Progress is inverse (lower time = more progress)
            return 0  # Handled by service

        if self.goal_type in ["weekly_km", "monthly_km"]:
            if self.target_distance_km and self.current_value:
                return min(int((self.current_value / self.target_distance_km) * 100), 100)
            return 0

        if self.goal_type == "pace":
            # For pace, lower is better
            return 0  # Handled by service

        return 0

    @property
    def days_remaining(self) -> int | None:
        """Days until target date."""
        if not self.target_date:
            return None
        from datetime import date
        delta = self.target_date - date.today()
        return max(0, delta.days)

    @property
    def is_overdue(self) -> bool:
        """Check if goal is past target date."""
        if not self.target_date:
            return False
        from datetime import date
        return date.today() > self.target_date and self.status == "active"

    @property
    def formatted_target_time(self) -> str:
        """Return target time formatted as H:MM:SS."""
        if not self.target_time:
            return ""
        total_seconds = int(self.target_time.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"