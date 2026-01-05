"""Views for training plan management."""

import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import (
    GPXConfirmForm,
    GPXUploadForm,
    ManualWorkoutForm,
    PlanWizardStep1Form,
    PlanWizardStep2Form,
    WorkoutEditForm,
)
from .generators import PlanGeneratorRegistry
from .generators.base import PlanConfig
from .gpx_utils import GPXParseError, parse_gpx_file
from .models import CompletedWorkout, ScheduledWorkout, TrainingPlan, TrainingWeek


WIZARD_SESSION_KEY = "plan_wizard_data"


@login_required
def plan_list(request):
    """List user's training plans and available templates."""
    plans = TrainingPlan.objects.filter(user=request.user).select_related("user")
    templates = TrainingPlan.objects.filter(is_template=True).select_related("user")

    return render(
        request,
        "training/plan_list.html",
        {
            "plans": plans,
            "templates": templates,
        },
    )


@login_required
def plan_detail(request, pk):
    """View a training plan with all weeks and workouts."""
    plan = get_object_or_404(
        TrainingPlan.objects.prefetch_related(
            "weeks__scheduled_workouts__completions"
        ),
        pk=pk,
    )

    # Check ownership or template status
    if not plan.is_template and plan.user != request.user:
        return redirect("training:plan_list")

    # Determine if user can edit this plan
    can_edit = plan.user == request.user and not plan.is_template

    return render(
        request,
        "training/plan_detail.html",
        {
            "plan": plan,
            "can_edit": can_edit,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def plan_create_wizard(request):
    """
    Multi-step wizard for creating a training plan.

    Steps:
    1. Select distance and methodology
    2. Set race date and goal time
    3. Preview generated plan and confirm
    """
    # Get current step from POST or default to 1
    step = int(request.POST.get("step", request.GET.get("step", 1)))

    # Get wizard data from session
    wizard_data = request.session.get(WIZARD_SESSION_KEY, {})

    # Handle template pre-population
    template_id = request.GET.get("template_id")
    if template_id and not wizard_data:
        template = get_object_or_404(TrainingPlan, pk=template_id, is_template=True)
        wizard_data = {
            "plan_type": template.plan_type,
            "methodology": template.methodology,
            "template_id": template_id,
        }
        request.session[WIZARD_SESSION_KEY] = wizard_data
        step = 2  # Skip to step 2 when copying from template

    # Handle POST requests
    if request.method == "POST":
        action = request.POST.get("action", "next")

        if action == "back":
            step = max(1, step - 1)
        elif action == "next":
            # Process current step
            if step == 1:
                form = PlanWizardStep1Form(request.POST)
                if form.is_valid():
                    wizard_data.update(form.cleaned_data)
                    request.session[WIZARD_SESSION_KEY] = wizard_data
                    step = 2
                else:
                    return _render_wizard_step(request, step, form, wizard_data)

            elif step == 2:
                form = PlanWizardStep2Form(
                    request.POST,
                    plan_type=wizard_data.get("plan_type"),
                    methodology=wizard_data.get("methodology"),
                )
                if form.is_valid():
                    wizard_data.update(
                        {
                            "name": form.cleaned_data["name"],
                            "race_date": form.cleaned_data["race_date"].isoformat(),
                            "goal_time": (
                                str(form.cleaned_data["goal_time"])
                                if form.cleaned_data["goal_time"]
                                else None
                            ),
                        }
                    )
                    request.session[WIZARD_SESSION_KEY] = wizard_data
                    step = 3
                else:
                    return _render_wizard_step(request, step, form, wizard_data)

            elif step == 3:
                # Create the plan
                plan = _create_plan_from_wizard(request.user, wizard_data)

                # Clear wizard data from session
                if WIZARD_SESSION_KEY in request.session:
                    del request.session[WIZARD_SESSION_KEY]

                # Return HTMX redirect or regular redirect
                if request.htmx:
                    response = HttpResponse()
                    response["HX-Redirect"] = f"/training/plans/{plan.pk}/"
                    return response
                return redirect("training:plan_detail", pk=plan.pk)

        elif action == "cancel":
            # Clear wizard data and redirect to list
            if WIZARD_SESSION_KEY in request.session:
                del request.session[WIZARD_SESSION_KEY]
            return redirect("training:plan_list")

    # Render appropriate step
    return _render_wizard_step(request, step, None, wizard_data)


def _render_wizard_step(request, step, form, wizard_data):
    """Render a specific wizard step."""
    step_names = {1: "methodology", 2: "race_details", 3: "preview"}
    step_name = step_names.get(step, "methodology")
    template_name = f"training/plan_create_wizard/step{step}_{step_name}.html"

    context = {
        "step": step,
        "total_steps": 3,
        "wizard_data": wizard_data,
    }

    if step == 1:
        context["form"] = form or PlanWizardStep1Form(initial=wizard_data)

    elif step == 2:
        if form is None:
            # Parse race_date if coming back from step 3
            initial = wizard_data.copy()
            if "race_date" in initial and isinstance(initial["race_date"], str):
                initial["race_date"] = date.fromisoformat(initial["race_date"])
            form = PlanWizardStep2Form(
                initial=initial,
                plan_type=wizard_data.get("plan_type"),
                methodology=wizard_data.get("methodology"),
            )
        context["form"] = form

    elif step == 3:
        # Generate preview
        context["preview"] = _generate_preview(request.user, wizard_data)

    # Return partial for HTMX, full page otherwise
    if request.htmx:
        return render(request, template_name, context)

    return render(
        request,
        "training/plan_create_wizard/wizard_base.html",
        {
            **context,
            "step_template": template_name,
        },
    )


def _generate_preview(user, wizard_data):
    """Generate plan preview from wizard data."""
    methodology = wizard_data.get("methodology", "custom")
    generator = PlanGeneratorRegistry.get_generator(methodology)

    if not generator:
        return None

    race_date = date.fromisoformat(wizard_data["race_date"])
    goal_time = None
    if wizard_data.get("goal_time"):
        # Parse "H:MM:SS" format
        parts = wizard_data["goal_time"].split(":")
        if len(parts) == 3:
            goal_time = timedelta(
                hours=int(parts[0]),
                minutes=int(parts[1]),
                seconds=int(parts[2]),
            )

    config = PlanConfig(
        user=user,
        plan_type=wizard_data["plan_type"],
        race_date=race_date,
        goal_time=goal_time,
        name=wizard_data.get("name", ""),
    )

    return generator.generate_plan(config)


def _create_plan_from_wizard(user, wizard_data):
    """Create actual plan from wizard data and save to database."""
    preview = _generate_preview(user, wizard_data)

    race_date = date.fromisoformat(wizard_data["race_date"])
    goal_time = None
    if wizard_data.get("goal_time"):
        parts = wizard_data["goal_time"].split(":")
        if len(parts) == 3:
            goal_time = timedelta(
                hours=int(parts[0]),
                minutes=int(parts[1]),
                seconds=int(parts[2]),
            )

    with transaction.atomic():
        plan = TrainingPlan.objects.create(
            user=user,
            name=preview.name,
            description=preview.description,
            plan_type=preview.plan_type,
            methodology=preview.methodology,
            duration_weeks=preview.duration_weeks,
            target_race_date=race_date,
            goal_time=goal_time,
            is_template=False,
        )

        for week_data in preview.weeks:
            week = TrainingWeek.objects.create(
                plan=plan,
                week_number=week_data.week_number,
                focus=week_data.focus,
                total_distance_km=week_data.total_distance_km,
                notes=week_data.notes,
            )

            for workout_data in week_data.workouts:
                ScheduledWorkout.objects.create(
                    week=week,
                    day_of_week=workout_data.day_of_week,
                    workout_type=workout_data.workout_type,
                    target_distance_km=workout_data.target_distance_km,
                    target_duration=workout_data.target_duration,
                    target_pace_min_per_km=workout_data.target_pace_min_per_km,
                    description=workout_data.description,
                )

    return plan


@login_required
def plan_copy(request, pk):
    """Start wizard with template pre-populated."""
    # Clear any existing wizard data
    if WIZARD_SESSION_KEY in request.session:
        del request.session[WIZARD_SESSION_KEY]
    return redirect(f"/training/plans/create/?template_id={pk}")


# Workout editing views


@login_required
@require_GET
def workout_detail(request, pk):
    """Return workout row partial (for cancel action)."""
    workout = get_object_or_404(
        ScheduledWorkout.objects.select_related("week__plan"),
        pk=pk,
    )

    # Check ownership
    if workout.week.plan.user != request.user:
        return HttpResponse(status=403)

    return render(
        request,
        "training/partials/workout_row.html",
        {"workout": workout, "can_edit": True},
    )


@login_required
@require_GET
def workout_edit(request, pk):
    """Return workout edit form partial."""
    workout = get_object_or_404(
        ScheduledWorkout.objects.select_related("week__plan"),
        pk=pk,
    )

    # Check ownership
    if workout.week.plan.user != request.user:
        return HttpResponse(status=403)

    form = WorkoutEditForm(instance=workout)

    return render(
        request,
        "training/partials/workout_edit_form.html",
        {"workout": workout, "form": form},
    )


@login_required
@require_POST
def workout_update(request, pk):
    """Update workout and return updated row partial."""
    workout = get_object_or_404(
        ScheduledWorkout.objects.select_related("week__plan"),
        pk=pk,
    )

    # Check ownership
    if workout.week.plan.user != request.user:
        return HttpResponse(status=403)

    form = WorkoutEditForm(request.POST, instance=workout)

    if form.is_valid():
        form.save()
        return render(
            request,
            "training/partials/workout_row.html",
            {"workout": workout, "can_edit": True},
        )

    # Return form with errors
    return render(
        request,
        "training/partials/workout_edit_form.html",
        {"workout": workout, "form": form},
    )


# Workout Log Views

GPX_SESSION_KEY = "gpx_preview_data"


@login_required
def workout_log_list(request):
    """List user's completed workouts with filtering."""
    workouts = CompletedWorkout.objects.filter(user=request.user).select_related(
        "scheduled_workout__week__plan"
    )

    # Apply filters
    source_filter = request.GET.get("source")
    if source_filter and source_filter in dict(CompletedWorkout.Source.choices):
        workouts = workouts.filter(source=source_filter)

    date_from = request.GET.get("date_from")
    if date_from:
        try:
            workouts = workouts.filter(date__gte=date.fromisoformat(date_from))
        except ValueError:
            pass

    date_to = request.GET.get("date_to")
    if date_to:
        try:
            workouts = workouts.filter(date__lte=date.fromisoformat(date_to))
        except ValueError:
            pass

    # Pagination
    paginator = Paginator(workouts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "training/workouts/workout_list.html",
        {
            "page_obj": page_obj,
            "source_choices": CompletedWorkout.Source.choices,
            "current_source": source_filter,
            "current_date_from": date_from,
            "current_date_to": date_to,
        },
    )


@login_required
def workout_log_detail(request, pk):
    """View details of a completed workout."""
    workout = get_object_or_404(
        CompletedWorkout.objects.select_related("scheduled_workout__week__plan"),
        pk=pk,
        user=request.user,
    )

    # Get route as GeoJSON for Leaflet
    route_geojson = None
    if workout.route:
        route_geojson = json.dumps(
            {
                "type": "Feature",
                "geometry": json.loads(workout.route.geojson),
                "properties": {},
            }
        )

    return render(
        request,
        "training/workouts/workout_detail.html",
        {
            "workout": workout,
            "route_geojson": route_geojson,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def workout_log_manual(request, scheduled_workout_pk=None):
    """Log a workout manually."""
    scheduled_workout = None
    if scheduled_workout_pk:
        scheduled_workout = get_object_or_404(
            ScheduledWorkout.objects.select_related("week__plan"),
            pk=scheduled_workout_pk,
            week__plan__user=request.user,
        )

    if request.method == "POST":
        form = ManualWorkoutForm(request.POST, scheduled_workout=scheduled_workout)
        if form.is_valid():
            workout = form.save(commit=False)
            workout.user = request.user
            workout.save()
            messages.success(request, "Workout logged successfully!")
            return redirect("training:workout_log_detail", pk=workout.pk)
    else:
        form = ManualWorkoutForm(scheduled_workout=scheduled_workout)

    return render(
        request,
        "training/workouts/workout_log_form.html",
        {
            "form": form,
            "mode": "manual",
            "scheduled_workout": scheduled_workout,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def workout_log_gpx(request, scheduled_workout_pk=None):
    """Log a workout via GPX file upload."""
    scheduled_workout = None
    if scheduled_workout_pk:
        scheduled_workout = get_object_or_404(
            ScheduledWorkout.objects.select_related("week__plan"),
            pk=scheduled_workout_pk,
            week__plan__user=request.user,
        )

    # Check if we have GPX data in session (confirmation step)
    gpx_session = request.session.get(GPX_SESSION_KEY)
    gpx_data = None

    if request.method == "POST":
        # Check if this is the confirmation form
        if gpx_session and "confirm" in request.POST:
            # Reconstruct GPX data from session for route
            from .gpx_utils import GPXData
            from django.contrib.gis.geos import LineString
            from decimal import Decimal

            route = None
            if gpx_session.get("route_wkt"):
                route = LineString.from_ewkt(gpx_session["route_wkt"])

            gpx_data = GPXData(
                distance_km=Decimal(gpx_session["distance_km"]),
                duration=timedelta(seconds=gpx_session["duration_seconds"]),
                pace_min_per_km=Decimal(gpx_session["pace_min_per_km"]),
                elevation_gain_m=Decimal(gpx_session["elevation_gain_m"]) if gpx_session.get("elevation_gain_m") else None,
                elevation_loss_m=Decimal(gpx_session["elevation_loss_m"]) if gpx_session.get("elevation_loss_m") else None,
                route=route,
                start_time=None,
                end_time=None,
                points_count=gpx_session.get("points_count", 0),
                name=gpx_session.get("name"),
            )

            form = GPXConfirmForm(
                request.POST,
                gpx_data=gpx_data,
                scheduled_workout=scheduled_workout,
            )
            if form.is_valid():
                workout = form.save(commit=False)
                workout.user = request.user
                workout.save()

                # Clear session data
                if GPX_SESSION_KEY in request.session:
                    del request.session[GPX_SESSION_KEY]

                messages.success(request, "Workout logged successfully!")
                return redirect("training:workout_log_detail", pk=workout.pk)

            return render(
                request,
                "training/workouts/workout_log_form.html",
                {
                    "form": form,
                    "mode": "gpx_confirm",
                    "gpx_data": gpx_data,
                    "scheduled_workout": scheduled_workout,
                },
            )

        # Handle new GPX file upload
        upload_form = GPXUploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            gpx_file = upload_form.cleaned_data["gpx_file"]
            try:
                gpx_data = parse_gpx_file(gpx_file)

                # Store GPX data in session for confirmation step
                session_data = {
                    "distance_km": str(gpx_data.distance_km),
                    "duration_seconds": int(gpx_data.duration.total_seconds()),
                    "pace_min_per_km": str(gpx_data.pace_min_per_km),
                    "elevation_gain_m": str(gpx_data.elevation_gain_m) if gpx_data.elevation_gain_m else None,
                    "elevation_loss_m": str(gpx_data.elevation_loss_m) if gpx_data.elevation_loss_m else None,
                    "points_count": gpx_data.points_count,
                    "name": gpx_data.name,
                }
                if gpx_data.route:
                    session_data["route_wkt"] = gpx_data.route.ewkt

                request.session[GPX_SESSION_KEY] = session_data

                # Show confirmation form with pre-filled data
                form = GPXConfirmForm(
                    gpx_data=gpx_data,
                    scheduled_workout=scheduled_workout,
                )

                # Get route as GeoJSON for preview
                route_geojson = None
                if gpx_data.route:
                    route_geojson = json.dumps(
                        {
                            "type": "Feature",
                            "geometry": json.loads(gpx_data.route.geojson),
                            "properties": {},
                        }
                    )

                return render(
                    request,
                    "training/workouts/workout_log_form.html",
                    {
                        "form": form,
                        "mode": "gpx_confirm",
                        "gpx_data": gpx_data,
                        "route_geojson": route_geojson,
                        "scheduled_workout": scheduled_workout,
                    },
                )

            except GPXParseError as e:
                messages.error(request, f"Failed to parse GPX file: {e}")

    # Show upload form
    upload_form = GPXUploadForm()

    return render(
        request,
        "training/workouts/workout_log_form.html",
        {
            "upload_form": upload_form,
            "mode": "gpx_upload",
            "scheduled_workout": scheduled_workout,
        },
    )


@login_required
@require_POST
def gpx_preview(request):
    """HTMX endpoint for GPX file preview."""
    form = GPXUploadForm(request.POST, request.FILES)

    if form.is_valid():
        gpx_file = form.cleaned_data["gpx_file"]
        try:
            gpx_data = parse_gpx_file(gpx_file)

            # Get route as GeoJSON for preview
            route_geojson = None
            if gpx_data.route:
                route_geojson = json.dumps(
                    {
                        "type": "Feature",
                        "geometry": json.loads(gpx_data.route.geojson),
                        "properties": {},
                    }
                )

            return render(
                request,
                "training/partials/gpx_preview.html",
                {
                    "gpx_data": gpx_data,
                    "route_geojson": route_geojson,
                },
            )

        except GPXParseError as e:
            return render(
                request,
                "training/partials/gpx_preview.html",
                {"error": str(e)},
            )

    return render(
        request,
        "training/partials/gpx_preview.html",
        {"error": "Invalid file upload."},
    )


@login_required
@require_POST
def workout_log_delete(request, pk):
    """Delete a completed workout."""
    workout = get_object_or_404(
        CompletedWorkout,
        pk=pk,
        user=request.user,
    )
    workout.delete()
    messages.success(request, "Workout deleted.")

    if request.htmx:
        return HttpResponse(status=200)
    return redirect("training:workout_log_list")
