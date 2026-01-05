"""Forms for training plan management."""

from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .generators import PlanGeneratorRegistry
from .models import CompletedWorkout, Goal, PaceZone, PersonalRecord, ScheduledWorkout, TrainingPlan, UserFitnessSettings


class PlanWizardStep1Form(forms.Form):
    """Step 1: Select distance and methodology."""

    plan_type = forms.ChoiceField(
        choices=TrainingPlan.PlanType.choices,
        widget=forms.RadioSelect(attrs={"class": "hidden peer"}),
        label="Race Distance",
    )
    methodology = forms.ChoiceField(
        choices=[],  # Populated dynamically in __init__
        widget=forms.RadioSelect(attrs={"class": "hidden peer"}),
        label="Training Methodology",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get methodology choices from registry
        choices = PlanGeneratorRegistry.get_choices()
        if choices:
            self.fields["methodology"].choices = choices
        else:
            # Fallback if no generators registered yet
            self.fields["methodology"].choices = [("custom", "Custom Plan")]


class PlanWizardStep2Form(forms.Form):
    """Step 2: Set race date and goal time."""

    name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g., Spring Marathon 2026",
            }
        ),
        label="Plan Name",
        help_text="Leave blank for auto-generated name",
    )
    race_date = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-input",
                "min": date.today().isoformat(),
            }
        ),
        label="Race Date",
    )
    goal_time_hours = forms.IntegerField(
        min_value=0,
        max_value=10,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "H",
            }
        ),
        label="Hours",
    )
    goal_time_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "MM",
            }
        ),
        label="Minutes",
    )
    goal_time_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
        label="Seconds",
    )

    def __init__(self, *args, plan_type=None, methodology=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan_type = plan_type
        self.methodology = methodology

    def clean_race_date(self):
        race_date = self.cleaned_data["race_date"]

        if race_date <= date.today():
            raise ValidationError("Race date must be in the future.")

        # Check minimum weeks based on methodology
        if self.methodology:
            generator = PlanGeneratorRegistry.get_generator(self.methodology)
            if generator:
                min_weeks = generator.min_weeks.get(self.plan_type, 8)
                weeks_until = (race_date - date.today()).days // 7
                if weeks_until < min_weeks:
                    raise ValidationError(
                        f"At least {min_weeks} weeks required for this plan. "
                        f"You have {weeks_until} weeks until race day."
                    )

        return race_date

    def clean(self):
        cleaned_data = super().clean()
        hours = cleaned_data.get("goal_time_hours") or 0
        minutes = cleaned_data.get("goal_time_minutes") or 0
        seconds = cleaned_data.get("goal_time_seconds") or 0

        # Only validate goal time if any component is provided
        if hours or minutes or seconds:
            goal_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
            cleaned_data["goal_time"] = goal_time

            # Sanity checks based on plan type
            plan_type = self.plan_type
            if plan_type == "half_marathon":
                if goal_time < timedelta(hours=1):
                    raise ValidationError(
                        "Half marathon goal under 1 hour is faster than the world record."
                    )
                if goal_time > timedelta(hours=4):
                    raise ValidationError(
                        "Half marathon goal over 4 hours exceeds typical race cutoffs."
                    )
            elif plan_type == "full_marathon":
                if goal_time < timedelta(hours=2):
                    raise ValidationError(
                        "Marathon goal under 2 hours is faster than the world record."
                    )
                if goal_time > timedelta(hours=7):
                    raise ValidationError(
                        "Marathon goal over 7 hours exceeds typical race cutoffs."
                    )
        else:
            cleaned_data["goal_time"] = None

        return cleaned_data


class WorkoutEditForm(forms.ModelForm):
    """Form for inline editing of scheduled workouts."""

    class Meta:
        model = ScheduledWorkout
        fields = [
            "workout_type",
            "target_distance_km",
            "target_duration",
            "target_pace_min_per_km",
            "description",
        ]
        widgets = {
            "workout_type": forms.Select(
                attrs={"class": "form-input"}
            ),
            "target_distance_km": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.1",
                    "placeholder": "km",
                }
            ),
            "target_duration": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "HH:MM:SS",
                }
            ),
            "target_pace_min_per_km": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.01",
                    "placeholder": "min/km",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 2,
                    "placeholder": "Workout notes...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional for flexibility
        for field in self.fields.values():
            field.required = False


class ManualWorkoutForm(forms.ModelForm):
    """Form for manually logging a completed workout."""

    duration_hours = forms.IntegerField(
        min_value=0,
        max_value=23,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "H",
            }
        ),
    )
    duration_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "MM",
            }
        ),
    )
    duration_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
    )

    class Meta:
        model = CompletedWorkout
        fields = [
            "date",
            "actual_distance_km",
            "average_heart_rate",
            "perceived_effort",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-input",
                    "max": date.today().isoformat(),
                }
            ),
            "actual_distance_km": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.01",
                    "placeholder": "e.g., 10.5",
                }
            ),
            "average_heart_rate": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g., 150",
                    "min": "40",
                    "max": "220",
                }
            ),
            "perceived_effort": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": "1",
                    "max": "10",
                    "placeholder": "1-10",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "How did the run feel?",
                }
            ),
        }

    def __init__(self, *args, scheduled_workout=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheduled_workout = scheduled_workout

        # Pre-fill from scheduled workout if provided
        if scheduled_workout and not self.data:
            if scheduled_workout.target_distance_km:
                self.fields["actual_distance_km"].initial = scheduled_workout.target_distance_km

            # Calculate the actual date this workout should be done
            plan = scheduled_workout.week.plan
            if plan.target_race_date:
                plan_start = plan.target_race_date - timedelta(weeks=plan.duration_weeks)
                week_start = plan_start + timedelta(weeks=scheduled_workout.week.week_number - 1)
                workout_date = week_start + timedelta(days=scheduled_workout.day_of_week - 1)
                self.fields["date"].initial = workout_date.isoformat()

    def clean(self):
        cleaned_data = super().clean()

        # Combine duration fields
        hours = cleaned_data.get("duration_hours") or 0
        minutes = cleaned_data.get("duration_minutes") or 0
        seconds = cleaned_data.get("duration_seconds") or 0

        if not (hours or minutes or seconds):
            raise ValidationError("Duration is required.")

        actual_duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        cleaned_data["actual_duration"] = actual_duration

        # Calculate pace if distance and duration provided
        distance = cleaned_data.get("actual_distance_km")
        if distance and distance > 0:
            duration_minutes_total = actual_duration.total_seconds() / 60
            pace = Decimal(str(round(duration_minutes_total / float(distance), 2)))
            cleaned_data["average_pace_min_per_km"] = pace
        else:
            raise ValidationError("Distance must be greater than 0.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.actual_duration = self.cleaned_data["actual_duration"]
        instance.average_pace_min_per_km = self.cleaned_data["average_pace_min_per_km"]
        instance.source = CompletedWorkout.Source.MANUAL

        if self.scheduled_workout:
            instance.scheduled_workout = self.scheduled_workout

        if commit:
            instance.save()
        return instance


class GPXUploadForm(forms.Form):
    """Form for uploading a GPX file."""

    gpx_file = forms.FileField(
        widget=forms.FileInput(
            attrs={
                "accept": ".gpx",
                "class": "hidden",
                "hx-post": "",  # Set dynamically in template
                "hx-target": "#gpx-preview",
                "hx-trigger": "change",
                "hx-encoding": "multipart/form-data",
            }
        ),
        help_text="Upload a .gpx file (max 10MB)",
    )

    def clean_gpx_file(self):
        gpx_file = self.cleaned_data["gpx_file"]

        # Check file extension
        if not gpx_file.name.lower().endswith(".gpx"):
            raise ValidationError("File must be a .gpx file.")

        # Check file size (10MB limit)
        max_size = 10 * 1024 * 1024
        if gpx_file.size > max_size:
            raise ValidationError("File size must be under 10MB.")

        return gpx_file


class GPXConfirmForm(forms.ModelForm):
    """Form for confirming/editing GPX-parsed workout data."""

    duration_hours = forms.IntegerField(
        min_value=0,
        max_value=23,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
            }
        ),
    )
    duration_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
            }
        ),
    )
    duration_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
            }
        ),
    )

    class Meta:
        model = CompletedWorkout
        fields = [
            "date",
            "actual_distance_km",
            "elevation_gain_m",
            "average_heart_rate",
            "perceived_effort",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-input",
                }
            ),
            "actual_distance_km": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.01",
                }
            ),
            "elevation_gain_m": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.1",
                }
            ),
            "average_heart_rate": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": "40",
                    "max": "220",
                }
            ),
            "perceived_effort": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": "1",
                    "max": "10",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                }
            ),
        }

    def __init__(self, *args, gpx_data=None, scheduled_workout=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.gpx_data = gpx_data
        self.scheduled_workout = scheduled_workout

        # Pre-fill from GPX data if provided
        if gpx_data and not self.data:
            self.fields["actual_distance_km"].initial = gpx_data.distance_km
            self.fields["elevation_gain_m"].initial = gpx_data.elevation_gain_m

            # Set date from GPX start time
            if gpx_data.start_time:
                self.fields["date"].initial = gpx_data.start_time.date().isoformat()

            # Set duration fields
            total_seconds = int(gpx_data.duration.total_seconds())
            self.fields["duration_hours"].initial = total_seconds // 3600
            self.fields["duration_minutes"].initial = (total_seconds % 3600) // 60
            self.fields["duration_seconds"].initial = total_seconds % 60

    def clean(self):
        cleaned_data = super().clean()

        # Combine duration fields
        hours = cleaned_data.get("duration_hours") or 0
        minutes = cleaned_data.get("duration_minutes") or 0
        seconds = cleaned_data.get("duration_seconds") or 0

        if not (hours or minutes or seconds):
            raise ValidationError("Duration is required.")

        actual_duration = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        cleaned_data["actual_duration"] = actual_duration

        # Calculate pace
        distance = cleaned_data.get("actual_distance_km")
        if distance and distance > 0:
            duration_minutes_total = actual_duration.total_seconds() / 60
            pace = Decimal(str(round(duration_minutes_total / float(distance), 2)))
            cleaned_data["average_pace_min_per_km"] = pace
        else:
            raise ValidationError("Distance must be greater than 0.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.actual_duration = self.cleaned_data["actual_duration"]
        instance.average_pace_min_per_km = self.cleaned_data["average_pace_min_per_km"]
        instance.source = CompletedWorkout.Source.GPX_UPLOAD

        # Set route from GPX data if available
        if self.gpx_data and self.gpx_data.route:
            instance.route = self.gpx_data.route

        if self.scheduled_workout:
            instance.scheduled_workout = self.scheduled_workout

        if commit:
            instance.save()
        return instance


# Pace Zone Calculator Forms


RACE_DISTANCE_CHOICES = [
    ("5k", "5K"),
    ("10k", "10K"),
    ("half_marathon", "Half Marathon"),
    ("marathon", "Marathon"),
    ("custom", "Custom Distance"),
]


class RaceResultForm(forms.Form):
    """Form for calculating pace zones from a race result."""

    distance = forms.ChoiceField(
        choices=RACE_DISTANCE_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "hidden peer"}),
        label="Race Distance",
    )
    custom_distance_km = forms.DecimalField(
        required=False,
        min_value=Decimal("1"),
        max_value=Decimal("100"),
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "placeholder": "Distance in km",
                "step": "0.01",
            }
        ),
        label="Custom Distance (km)",
    )
    time_hours = forms.IntegerField(
        min_value=0,
        max_value=10,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "H",
            }
        ),
    )
    time_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "MM",
            }
        ),
    )
    time_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        distance = cleaned_data.get("distance")
        custom_distance = cleaned_data.get("custom_distance_km")

        # Validate custom distance if selected
        if distance == "custom":
            if not custom_distance:
                raise ValidationError("Please enter a custom distance.")
            cleaned_data["distance_value"] = float(custom_distance)
        else:
            cleaned_data["distance_value"] = distance

        # Combine time fields
        hours = cleaned_data.get("time_hours") or 0
        minutes = cleaned_data.get("time_minutes") or 0
        seconds = cleaned_data.get("time_seconds") or 0

        if not (hours or minutes or seconds):
            raise ValidationError("Please enter a race time.")

        race_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        cleaned_data["race_time"] = race_time

        # Basic sanity check
        if race_time.total_seconds() < 60:
            raise ValidationError("Race time must be at least 1 minute.")

        return cleaned_data


class ThresholdPaceForm(forms.Form):
    """Form for calculating pace zones from threshold pace."""

    pace_minutes = forms.IntegerField(
        min_value=2,
        max_value=15,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "M",
            }
        ),
        label="Minutes",
    )
    pace_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
        label="Seconds",
    )

    def clean(self):
        cleaned_data = super().clean()
        minutes = cleaned_data.get("pace_minutes")
        seconds = cleaned_data.get("pace_seconds") or 0

        if minutes is None:
            raise ValidationError("Please enter pace minutes.")

        # Convert to decimal min/km (e.g., 5:30 -> 5.50)
        pace_decimal = Decimal(str(minutes)) + Decimal(str(seconds)) / Decimal("60")
        cleaned_data["threshold_pace"] = pace_decimal.quantize(Decimal("0.01"))

        return cleaned_data


class ZoneOverrideForm(forms.ModelForm):
    """Form for manually overriding a pace zone's pace range."""

    min_pace_minutes = forms.IntegerField(
        min_value=2,
        max_value=15,
        widget=forms.NumberInput(
            attrs={"class": "form-input w-16 text-center"}
        ),
    )
    min_pace_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-input w-16 text-center"}
        ),
    )
    max_pace_minutes = forms.IntegerField(
        min_value=2,
        max_value=15,
        widget=forms.NumberInput(
            attrs={"class": "form-input w-16 text-center"}
        ),
    )
    max_pace_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-input w-16 text-center"}
        ),
    )

    class Meta:
        model = PaceZone
        fields: list[str] = []  # We use custom fields instead

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-fill from instance
        if self.instance and self.instance.pk:
            min_pace = float(self.instance.min_pace_min_per_km)
            max_pace = float(self.instance.max_pace_min_per_km)

            self.fields["min_pace_minutes"].initial = int(min_pace)
            self.fields["min_pace_seconds"].initial = int((min_pace % 1) * 60)
            self.fields["max_pace_minutes"].initial = int(max_pace)
            self.fields["max_pace_seconds"].initial = int((max_pace % 1) * 60)

    def clean(self):
        cleaned_data = super().clean()

        # Convert to decimal
        min_minutes = cleaned_data.get("min_pace_minutes")
        min_seconds = cleaned_data.get("min_pace_seconds") or 0
        max_minutes = cleaned_data.get("max_pace_minutes")
        max_seconds = cleaned_data.get("max_pace_seconds") or 0

        if min_minutes is None or max_minutes is None:
            raise ValidationError("Please enter both min and max pace.")

        min_pace = Decimal(str(min_minutes)) + Decimal(str(min_seconds)) / Decimal("60")
        max_pace = Decimal(str(max_minutes)) + Decimal(str(max_seconds)) / Decimal("60")

        # Note: slower pace = higher number, so min_pace should be > max_pace
        if min_pace <= max_pace:
            raise ValidationError(
                "Min pace (slower) must be greater than max pace (faster)."
            )

        cleaned_data["min_pace_min_per_km"] = min_pace.quantize(Decimal("0.01"))
        cleaned_data["max_pace_min_per_km"] = max_pace.quantize(Decimal("0.01"))

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.min_pace_min_per_km = self.cleaned_data["min_pace_min_per_km"]
        instance.max_pace_min_per_km = self.cleaned_data["max_pace_min_per_km"]

        if commit:
            instance.save()
        return instance


class FitnessSettingsForm(forms.ModelForm):
    """Form for user fitness settings (threshold pace, HR, targets)."""

    threshold_pace_minutes = forms.IntegerField(
        min_value=2,
        max_value=15,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "M",
            }
        ),
        label="Minutes",
    )
    threshold_pace_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
        label="Seconds",
    )

    class Meta:
        model = UserFitnessSettings
        fields = [
            "threshold_hr",
            "target_weekly_tss",
            "recovery_tsb_threshold",
        ]
        widgets = {
            "threshold_hr": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g., 165",
                    "min": "100",
                    "max": "220",
                }
            ),
            "target_weekly_tss": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g., 300",
                    "min": "0",
                    "max": "1000",
                }
            ),
            "recovery_tsb_threshold": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g., -20",
                    "min": "-100",
                    "max": "0",
                }
            ),
        }
        help_texts = {
            "threshold_hr": "Your lactate threshold heart rate in BPM",
            "target_weekly_tss": "Your weekly Training Stress Score target",
            "recovery_tsb_threshold": "TSB level below which recovery is recommended",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-fill threshold pace if set
        if self.instance and self.instance.pk and self.instance.threshold_pace:
            pace = float(self.instance.threshold_pace)
            self.fields["threshold_pace_minutes"].initial = int(pace)
            self.fields["threshold_pace_seconds"].initial = int((pace % 1) * 60)

    def clean(self):
        cleaned_data = super().clean()

        # Convert threshold pace to decimal if provided
        minutes = cleaned_data.get("threshold_pace_minutes")
        seconds = cleaned_data.get("threshold_pace_seconds") or 0

        if minutes:
            pace_decimal = Decimal(str(minutes)) + Decimal(str(seconds)) / Decimal("60")
            cleaned_data["threshold_pace"] = pace_decimal.quantize(Decimal("0.01"))
        else:
            cleaned_data["threshold_pace"] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.threshold_pace = self.cleaned_data.get("threshold_pace")

        if commit:
            instance.save()
        return instance


class ManualRecordForm(forms.Form):
    """Form for manually adding a personal record."""

    distance = forms.ChoiceField(
        choices=PersonalRecord.Distance.choices,
        widget=forms.RadioSelect(attrs={"class": "hidden peer"}),
        label="Distance",
    )
    custom_distance_km = forms.DecimalField(
        required=False,
        min_value=Decimal("0.1"),
        max_value=Decimal("200"),
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "placeholder": "Distance in km",
                "step": "0.01",
            }
        ),
        label="Custom Distance (km)",
    )
    time_hours = forms.IntegerField(
        min_value=0,
        max_value=24,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "H",
            }
        ),
    )
    time_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=True,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "MM",
            }
        ),
    )
    time_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
    )
    record_date = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-input",
                "max": date.today().isoformat(),
            }
        ),
        label="Date",
    )

    def clean(self):
        cleaned_data = super().clean()
        distance = cleaned_data.get("distance")
        custom_distance = cleaned_data.get("custom_distance_km")

        if distance == "custom" and not custom_distance:
            raise ValidationError("Please enter a custom distance.")

        # Combine time fields
        hours = cleaned_data.get("time_hours") or 0
        minutes = cleaned_data.get("time_minutes") or 0
        seconds = cleaned_data.get("time_seconds") or 0

        if not (hours or minutes or seconds):
            raise ValidationError("Please enter a time.")

        record_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        cleaned_data["record_time"] = record_time

        return cleaned_data


class GoalForm(forms.ModelForm):
    """Form for creating/editing a goal."""

    target_time_hours = forms.IntegerField(
        min_value=0,
        max_value=24,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "H",
            }
        ),
    )
    target_time_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "MM",
            }
        ),
    )
    target_time_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
    )
    target_pace_minutes = forms.IntegerField(
        min_value=2,
        max_value=15,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "M",
            }
        ),
    )
    target_pace_seconds = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input w-16 text-center",
                "placeholder": "SS",
            }
        ),
    )

    class Meta:
        model = Goal
        fields = [
            "goal_type",
            "title",
            "race_distance",
            "target_distance_km",
            "target_date",
            "notes",
        ]
        widgets = {
            "goal_type": forms.RadioSelect(attrs={"class": "hidden peer"}),
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g., Sub-4 Marathon",
                }
            ),
            "race_distance": forms.Select(attrs={"class": "form-input"}),
            "target_distance_km": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.1",
                    "placeholder": "km",
                }
            ),
            "target_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-input",
                    "min": date.today().isoformat(),
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 2,
                    "placeholder": "Additional notes...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-fill time fields if editing
        if self.instance and self.instance.pk:
            if self.instance.target_time:
                total_seconds = int(self.instance.target_time.total_seconds())
                self.fields["target_time_hours"].initial = total_seconds // 3600
                self.fields["target_time_minutes"].initial = (total_seconds % 3600) // 60
                self.fields["target_time_seconds"].initial = total_seconds % 60

            if self.instance.target_pace:
                pace = float(self.instance.target_pace)
                self.fields["target_pace_minutes"].initial = int(pace)
                self.fields["target_pace_seconds"].initial = int((pace % 1) * 60)

    def clean(self):
        cleaned_data = super().clean()
        goal_type = cleaned_data.get("goal_type")

        # Validate based on goal type
        if goal_type == "race_time":
            if not cleaned_data.get("race_distance"):
                raise ValidationError("Please select a race distance.")

            hours = cleaned_data.get("target_time_hours") or 0
            minutes = cleaned_data.get("target_time_minutes") or 0
            seconds = cleaned_data.get("target_time_seconds") or 0

            if not (hours or minutes or seconds):
                raise ValidationError("Please enter a target time.")

            cleaned_data["target_time"] = timedelta(
                hours=hours, minutes=minutes, seconds=seconds
            )

        elif goal_type in ["weekly_km", "monthly_km"]:
            if not cleaned_data.get("target_distance_km"):
                raise ValidationError("Please enter a target distance.")

        elif goal_type == "pace":
            if not cleaned_data.get("race_distance"):
                raise ValidationError("Please select a race distance.")

            minutes = cleaned_data.get("target_pace_minutes")
            seconds = cleaned_data.get("target_pace_seconds") or 0

            if not minutes:
                raise ValidationError("Please enter a target pace.")

            pace_decimal = Decimal(str(minutes)) + Decimal(str(seconds)) / Decimal("60")
            cleaned_data["target_pace"] = pace_decimal.quantize(Decimal("0.01"))

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.start_date = date.today()

        # Set target time if provided
        if "target_time" in self.cleaned_data:
            instance.target_time = self.cleaned_data["target_time"]

        # Set target pace if provided
        if "target_pace" in self.cleaned_data:
            instance.target_pace = self.cleaned_data["target_pace"]

        if commit:
            instance.save()
        return instance
