"""Views for the accounts app."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from vught_pace_keeper.training.models import TrainingPlan


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

    context = {
        "training_plans": training_plans,
        "template_plans": template_plans,
        "strava_connected": bool(request.user.strava_athlete_id),
    }
    return render(request, "dashboard.html", context)
