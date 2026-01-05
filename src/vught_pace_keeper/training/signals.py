"""Signal handlers for training app."""

from datetime import date, timedelta

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import CompletedWorkout


@receiver(post_save, sender=CompletedWorkout)
def update_training_load_on_workout_save(sender, instance, created, **kwargs):
    """Recalculate training load when a workout is saved."""
    from .services.training_load import TrainingLoadService

    service = TrainingLoadService(instance.user)

    # Update training load for the workout date
    service.update_training_load(instance.date)

    # Also update subsequent days up to today (to maintain ATL/CTL continuity)
    current = instance.date + timedelta(days=1)
    today = date.today()

    while current <= today:
        service.update_training_load(current)
        current += timedelta(days=1)


@receiver(post_save, sender=CompletedWorkout)
def check_for_new_pr_on_workout_save(sender, instance, created, **kwargs):
    """Check for new personal records when a workout is saved."""
    if not created:
        return  # Only check on new workouts

    from .services.records import PersonalRecordService

    service = PersonalRecordService(instance.user)
    pr_results = service.check_for_pr(instance)

    # Create records for any new PRs
    for result in pr_results:
        if result.is_new_pr:
            service.create_record(instance, result.distance, result.time)


@receiver(post_save, sender=CompletedWorkout)
def update_goals_on_workout_save(sender, instance, **kwargs):
    """Update goal progress when a workout is saved."""
    from .services.goals import GoalTrackingService

    service = GoalTrackingService(instance.user)
    service.check_all_goals()


@receiver(post_delete, sender=CompletedWorkout)
def update_training_load_on_workout_delete(sender, instance, **kwargs):
    """Recalculate training load when a workout is deleted."""
    from .services.training_load import TrainingLoadService

    service = TrainingLoadService(instance.user)

    # Recalculate from the deleted workout's date
    service.recalculate_from_date(instance.date)
