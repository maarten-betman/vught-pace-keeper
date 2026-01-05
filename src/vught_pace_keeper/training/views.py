"""Views for training plan management."""

import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import (
    GPXConfirmForm,
    GPXUploadForm,
    ManualWorkoutForm,
    PlanWizardStep1Form,
    PlanWizardStep2Form,
    RaceResultForm,
    ThresholdPaceForm,
    WorkoutEditForm,
    ZoneOverrideForm,
)
from .generators import PlanGeneratorRegistry
from .generators.base import PlanConfig
from .gpx_utils import GPXParseError, parse_gpx_file
from .models import CompletedWorkout, PaceZone, ScheduledWorkout, TrainingPlan, TrainingWeek
from .pace_calculator import PaceCalculationError, PaceZoneCalculator


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
@require_GET
def workout_stream_data(request, pk):
    """Return activity stream data as JSON for charts."""
    workout = get_object_or_404(
        CompletedWorkout,
        pk=pk,
        user=request.user,
    )

    if not hasattr(workout, "stream"):
        return JsonResponse({"error": "No stream data available"}, status=404)

    stream = workout.stream

    # Convert velocity (m/s) to pace (min/km)
    # pace = minutes per km = 1 / (m/s * 0.001 km/m * 60 s/min) = 1000 / (60 * v) = 16.667 / v
    pace_data = []
    for v in stream.velocity_data:
        if v and v > 0:
            pace = 16.6667 / v  # minutes per km
            pace_data.append(round(pace, 2))
        else:
            pace_data.append(None)

    # Convert distance from meters to km for x-axis
    distance_km = [round(d / 1000, 2) for d in stream.distance_data] if stream.distance_data else []

    return JsonResponse({
        "time": stream.time_data,
        "distance": stream.distance_data,
        "distance_km": distance_km,
        "heartrate": stream.heartrate_data,
        "pace": pace_data,
        "altitude": stream.altitude_data,
    })


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


# Pace Zone Views

ZONES_SESSION_KEY = "calculated_zones"


@login_required
def pace_zone_list(request):
    """Display user's current pace zones."""
    zones = PaceZone.objects.filter(user=request.user).order_by("min_pace_min_per_km")

    return render(
        request,
        "training/pace_zones/zone_list.html",
        {"zones": zones},
    )


@login_required
@require_http_methods(["GET", "POST"])
def pace_zone_calculator(request):
    """Calculate pace zones from race result or threshold pace."""
    race_form = RaceResultForm()
    threshold_form = ThresholdPaceForm()
    result = None
    active_tab = request.POST.get("tab", "race")

    if request.method == "POST":
        calculator = PaceZoneCalculator()

        if active_tab == "race":
            race_form = RaceResultForm(request.POST)
            if race_form.is_valid():
                try:
                    result = calculator.from_race_result(
                        distance=race_form.cleaned_data["distance_value"],
                        time=race_form.cleaned_data["race_time"],
                    )
                    # Store in session for save action
                    _store_zones_in_session(request, result)
                except PaceCalculationError as e:
                    messages.error(request, str(e))

        elif active_tab == "threshold":
            threshold_form = ThresholdPaceForm(request.POST)
            if threshold_form.is_valid():
                try:
                    result = calculator.from_threshold_pace(
                        threshold_pace=threshold_form.cleaned_data["threshold_pace"],
                    )
                    _store_zones_in_session(request, result)
                except PaceCalculationError as e:
                    messages.error(request, str(e))

        # Return partial for HTMX
        if request.htmx and result:
            # Get existing zones for comparison
            existing_zones = PaceZone.objects.filter(user=request.user)
            return render(
                request,
                "training/pace_zones/zone_results.html",
                {
                    "result": result,
                    "existing_zones": existing_zones,
                },
            )

    return render(
        request,
        "training/pace_zones/calculator.html",
        {
            "race_form": race_form,
            "threshold_form": threshold_form,
            "active_tab": active_tab,
            "result": result,
        },
    )


def _store_zones_in_session(request, result):
    """Store calculated zones in session for later save."""
    session_data = {
        "vdot": result.vdot,
        "source_description": result.source_description,
        "zones": [
            {
                "name": z.name,
                "min_pace": str(z.min_pace_min_per_km),
                "max_pace": str(z.max_pace_min_per_km),
                "description": z.description,
                "color_hex": z.color_hex,
            }
            for z in result.zones
        ],
    }
    request.session[ZONES_SESSION_KEY] = session_data


@login_required
@require_POST
def pace_zone_save(request):
    """Save calculated zones to database."""
    session_data = request.session.get(ZONES_SESSION_KEY)

    if not session_data:
        messages.error(request, "No zones to save. Please calculate zones first.")
        return redirect("training:pace_zone_calculator")

    from decimal import Decimal

    with transaction.atomic():
        # Delete existing zones
        PaceZone.objects.filter(user=request.user).delete()

        # Create new zones
        for zone_data in session_data["zones"]:
            PaceZone.objects.create(
                user=request.user,
                name=zone_data["name"],
                min_pace_min_per_km=Decimal(zone_data["min_pace"]),
                max_pace_min_per_km=Decimal(zone_data["max_pace"]),
                description=zone_data["description"],
                color_hex=zone_data["color_hex"],
            )

    # Clear session
    if ZONES_SESSION_KEY in request.session:
        del request.session[ZONES_SESSION_KEY]

    messages.success(
        request,
        f"Pace zones saved! (VDOT: {session_data['vdot']})",
    )
    return redirect("training:pace_zone_list")


@login_required
@require_http_methods(["GET", "POST"])
def pace_zone_override(request, pk):
    """Override a single pace zone's values."""
    zone = get_object_or_404(PaceZone, pk=pk, user=request.user)

    if request.method == "POST":
        form = ZoneOverrideForm(request.POST, instance=zone)
        if form.is_valid():
            form.save()
            messages.success(request, f"{zone.get_name_display()} zone updated.")

            if request.htmx:
                return render(
                    request,
                    "training/pace_zones/zone_card.html",
                    {"zone": zone},
                )
            return redirect("training:pace_zone_list")
    else:
        form = ZoneOverrideForm(instance=zone)

    return render(
        request,
        "training/pace_zones/zone_edit.html",
        {"form": form, "zone": zone},
    )


# Analytics Views


@login_required
def analytics_dashboard(request):
    """Main analytics dashboard view."""
    from .services.analytics import TrainingAnalyticsService

    analytics = TrainingAnalyticsService(request.user)

    # Get filter parameters
    plan_id = request.GET.get("plan")
    date_range = request.GET.get("range", "12w")

    # Resolve date range
    date_from, date_to = _resolve_date_range(date_range)

    # Get selected plan or default to most recent
    plan = None
    if plan_id:
        plan = TrainingPlan.objects.filter(pk=plan_id, user=request.user).first()

    # Fetch analytics data
    weekly_summary = analytics.get_weekly_summary()
    plan_adherence = analytics.get_plan_adherence(
        plan=plan, date_from=date_from, date_to=date_to
    )
    zone_distribution = analytics.get_zone_distribution(
        date_from=date_from, date_to=date_to
    )
    weekly_trends = analytics.get_weekly_trends(
        weeks=_weeks_from_range(date_range), plan=plan
    )

    # User's plans for filter dropdown
    user_plans = TrainingPlan.objects.filter(
        user=request.user, is_template=False
    ).order_by("-created_at")

    context = {
        "weekly_summary": weekly_summary,
        "plan_adherence": plan_adherence,
        "zone_distribution": zone_distribution,
        "weekly_trends": weekly_trends,
        "user_plans": user_plans,
        "selected_plan": plan,
        "selected_range": date_range,
        "range_choices": [
            ("4w", "Last 4 weeks"),
            ("8w", "Last 8 weeks"),
            ("12w", "Last 12 weeks"),
            ("all", "All time"),
        ],
    }

    return render(request, "training/analytics/dashboard.html", context)


@login_required
@require_GET
def analytics_weekly_summary(request):
    """HTMX partial for weekly summary refresh."""
    from .services.analytics import TrainingAnalyticsService

    analytics = TrainingAnalyticsService(request.user)

    week_offset = int(request.GET.get("week_offset", 0))
    today = date.today()
    week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)

    summary = analytics.get_weekly_summary(week_start=week_start)

    return render(
        request,
        "training/analytics/partials/weekly_summary.html",
        {
            "summary": summary,
            "week_offset": week_offset,
        },
    )


def _resolve_date_range(range_str: str) -> tuple:
    """Convert range string to date tuple."""
    today = date.today()

    if range_str == "4w":
        return today - timedelta(weeks=4), today
    elif range_str == "8w":
        return today - timedelta(weeks=8), today
    elif range_str == "12w":
        return today - timedelta(weeks=12), today
    else:  # 'all'
        return None, None


def _weeks_from_range(range_str: str) -> int:
    """Get number of weeks from range string."""
    mapping = {"4w": 4, "8w": 8, "12w": 12, "all": 52}
    return mapping.get(range_str, 12)


# Calendar Views


@login_required
def training_calendar(request):
    """Main training calendar view with month navigation."""
    from .services.calendar import CalendarService

    # Get year and month from query params, default to current
    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    # Validate and clamp
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    calendar_service = CalendarService(request.user)
    weeks = calendar_service.get_month_data(year, month)

    # Calculate prev/next month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        "weeks": weeks,
        "year": year,
        "month": month,
        "month_name": date(year, month, 1).strftime("%B"),
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today": today,
    }

    # Return partial for HTMX requests
    if request.htmx:
        return render(request, "training/calendar/partials/month_view.html", context)

    return render(request, "training/calendar/calendar.html", context)


@login_required
@require_GET
def calendar_day_detail(request, date_str):
    """HTMX endpoint for day detail modal."""
    from .services.calendar import CalendarService

    try:
        day_date = date.fromisoformat(date_str)
    except ValueError:
        return HttpResponse("Invalid date", status=400)

    calendar_service = CalendarService(request.user)
    day_data = calendar_service.get_day_data(day_date)

    return render(
        request,
        "training/calendar/partials/day_popup.html",
        {"day": day_data},
    )


# ============================================================================
# Training Load Views
# ============================================================================


@login_required
def training_load_dashboard(request):
    """Dashboard showing training load metrics (TSS, ATL, CTL, TSB)."""
    from .services.training_load import TrainingLoadService

    service = TrainingLoadService(request.user)
    summary = service.get_summary()
    chart_data = service.get_chart_data(days=42)
    history = service.get_load_history(days=14)

    return render(
        request,
        "training/load/dashboard.html",
        {
            "summary": summary,
            "chart_data": json.dumps(chart_data),
            "history": history,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def fitness_settings(request):
    """View/edit user fitness settings for training load calculations."""
    from .forms import FitnessSettingsForm
    from .models import UserFitnessSettings

    settings_obj, _ = UserFitnessSettings.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = FitnessSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Fitness settings saved.")
            return redirect("training:load_dashboard")
    else:
        form = FitnessSettingsForm(instance=settings_obj)

    return render(
        request,
        "training/load/settings.html",
        {"form": form},
    )


@login_required
@require_POST
def backfill_training_load(request):
    """Backfill training load data from historical workouts."""
    from .services.training_load import TrainingLoadService

    days = int(request.POST.get("days", 90))
    service = TrainingLoadService(request.user)
    count = service.backfill_historical_data(days_back=days)

    messages.success(request, f"Training load calculated for {count} days.")
    return redirect("training:load_dashboard")


@login_required
@require_GET
def training_load_chart_data(request):
    """JSON endpoint for training load chart data."""
    from .services.training_load import TrainingLoadService

    days = int(request.GET.get("days", 42))
    service = TrainingLoadService(request.user)
    chart_data = service.get_chart_data(days=days)

    return JsonResponse(chart_data)


# ============================================================================
# Personal Records Views
# ============================================================================


@login_required
def personal_records_list(request):
    """Display all personal records organized by distance."""
    from .services.records import PersonalRecordService

    service = PersonalRecordService(request.user)
    records = service.get_all_records()
    recent = service.get_recent_records(limit=5)

    return render(
        request,
        "training/records/list.html",
        {
            "records": records,
            "recent_records": recent,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def personal_record_add(request):
    """Add a manual personal record."""
    from .forms import ManualRecordForm
    from .services.records import PersonalRecordService

    if request.method == "POST":
        form = ManualRecordForm(request.POST)
        if form.is_valid():
            service = PersonalRecordService(request.user)
            service.add_manual_record(
                distance=form.cleaned_data["distance"],
                time=form.cleaned_data["record_time"],
                date=form.cleaned_data["record_date"],
                custom_distance_km=form.cleaned_data.get("custom_distance_km"),
            )
            messages.success(request, "Personal record added.")
            return redirect("training:records_list")
    else:
        form = ManualRecordForm()

    return render(
        request,
        "training/records/add_form.html",
        {"form": form},
    )


@login_required
@require_POST
def personal_record_delete(request, pk):
    """Delete a personal record."""
    from .services.records import PersonalRecordService

    service = PersonalRecordService(request.user)
    if service.delete_record(pk):
        messages.success(request, "Record deleted.")
    else:
        messages.error(request, "Record not found.")

    return redirect("training:records_list")


# ============================================================================
# Goals Views
# ============================================================================


@login_required
def goal_list(request):
    """Display all goals with progress."""
    from .services.goals import GoalTrackingService

    service = GoalTrackingService(request.user)
    goals = service.get_all_goals()

    # Calculate progress for each goal
    goals_with_progress = []
    for goal in goals:
        progress = service.calculate_progress(goal)
        goals_with_progress.append({
            "goal": goal,
            "progress": progress,
        })

    return render(
        request,
        "training/goals/list.html",
        {"goals_with_progress": goals_with_progress},
    )


@login_required
@require_http_methods(["GET", "POST"])
def goal_create(request):
    """Create a new goal."""
    from .forms import GoalForm

    if request.method == "POST":
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, "Goal created.")
            return redirect("training:goal_list")
    else:
        form = GoalForm()

    return render(
        request,
        "training/goals/form.html",
        {"form": form, "is_edit": False},
    )


@login_required
@require_http_methods(["GET", "POST"])
def goal_edit(request, pk):
    """Edit an existing goal."""
    from .forms import GoalForm
    from .models import Goal

    goal = get_object_or_404(Goal, pk=pk, user=request.user)

    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, "Goal updated.")
            return redirect("training:goal_list")
    else:
        form = GoalForm(instance=goal)

    return render(
        request,
        "training/goals/form.html",
        {"form": form, "goal": goal, "is_edit": True},
    )


@login_required
@require_POST
def goal_delete(request, pk):
    """Delete a goal."""
    from .models import Goal

    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    goal.delete()
    messages.success(request, "Goal deleted.")
    return redirect("training:goal_list")


@login_required
@require_POST
def goal_abandon(request, pk):
    """Mark a goal as abandoned."""
    from .models import Goal

    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    goal.status = Goal.Status.ABANDONED
    goal.save(update_fields=["status", "updated_at"])
    messages.success(request, "Goal marked as abandoned.")
    return redirect("training:goal_list")


# ============================================================================
# Workout Matching Views
# ============================================================================


@login_required
def unmatched_activities(request):
    """List unmatched completed workouts."""
    from .services.matching import WorkoutMatchingService

    service = WorkoutMatchingService(request.user)
    unmatched = service.get_unmatched_workouts()

    # Get best match candidate for each unmatched workout
    workouts_with_candidates = []
    for workout in unmatched:
        best_match = service.get_best_match(workout)
        workouts_with_candidates.append({
            "workout": workout,
            "best_match": best_match,
        })

    return render(
        request,
        "training/matching/list.html",
        {
            "workouts_with_candidates": workouts_with_candidates,
            "unmatched_count": len(unmatched),
        },
    )


@login_required
@require_GET
def match_candidates(request, pk):
    """HTMX endpoint to get match candidates for a workout."""
    from .services.matching import WorkoutMatchingService

    workout = get_object_or_404(CompletedWorkout, pk=pk, user=request.user)
    service = WorkoutMatchingService(request.user)
    candidates = service.find_candidates(workout, limit=5)

    return render(
        request,
        "training/matching/partials/candidate_list.html",
        {
            "workout": workout,
            "candidates": candidates,
        },
    )


@login_required
@require_POST
def match_workout(request, completed_pk, scheduled_pk):
    """Match a completed workout to a scheduled workout."""
    from .services.matching import WorkoutMatchingService

    service = WorkoutMatchingService(request.user)
    success, message = service.match_workout(completed_pk, scheduled_pk)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # If HTMX request, return empty response to remove the row
    if request.headers.get("HX-Request"):
        return HttpResponse("")

    return redirect("training:matching")


@login_required
@require_POST
def unmatch_workout(request, pk):
    """Remove the match between a completed and scheduled workout."""
    from .services.matching import WorkoutMatchingService

    service = WorkoutMatchingService(request.user)
    success, message = service.unmatch_workout(pk)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("training:workout_log_list")


@login_required
@require_POST
def auto_match_all(request):
    """Auto-match all unmatched workouts with high-confidence matches."""
    from .services.matching import WorkoutMatchingService

    service = WorkoutMatchingService(request.user)
    result = service.auto_match_all()

    if result.matched > 0:
        messages.success(request, f"Matched {result.matched} workouts automatically.")
    if result.skipped > 0:
        messages.info(request, f"{result.skipped} workouts could not be auto-matched.")
    if result.errors:
        for error in result.errors[:3]:  # Show first 3 errors
            messages.error(request, error)

    return redirect("training:matching")