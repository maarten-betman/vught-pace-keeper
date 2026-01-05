"""Views for the accounts app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from vught_pace_keeper.training.models import TrainingPlan
from vught_pace_keeper.training.services.analytics import TrainingAnalyticsService
from vught_pace_keeper.training.services.matching import WorkoutMatchingService


def landing_page(request):
    """Public landing page with Strava connect button."""
    if request.user.is_authenticated:
        return render(request, "landing.html", {"user": request.user})
    return render(request, "landing.html")


@login_required
def dashboard(request):
    """User dashboard showing training plans and Strava connection status."""
    training_plans = TrainingPlan.objects.filter(user=request.user).order_by(
        "-created_at"
    )
    template_plans = TrainingPlan.objects.filter(is_template=True).order_by("name")

    # Get weekly summary for quick stats
    analytics = TrainingAnalyticsService(request.user)
    weekly_summary = analytics.get_weekly_summary()

    # Get unmatched workout count
    matching_service = WorkoutMatchingService(request.user)
    unmatched_count = matching_service.get_unmatched_count()

    context = {
        "training_plans": training_plans,
        "template_plans": template_plans,
        "strava_connected": bool(request.user.strava_athlete_id),
        "weekly_summary": weekly_summary,
        "unmatched_count": unmatched_count,
    }
    return render(request, "dashboard.html", context)
