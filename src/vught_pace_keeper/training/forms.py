"""Forms for training plan management."""

from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError

from .generators import PlanGeneratorRegistry
from .models import ScheduledWorkout, TrainingPlan


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
