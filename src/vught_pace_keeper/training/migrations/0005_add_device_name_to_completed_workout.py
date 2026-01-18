# Generated manually for Strava API compliance (Garmin attribution)

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add device_name field to CompletedWorkout for Garmin attribution.

    Per Strava API Agreement (Nov 2025 update), applications must display
    attribution to Garmin when displaying Garmin-sourced activity data.
    This field stores the recording device name (e.g., "Garmin Forerunner 265")
    fetched from Strava's DetailedActivity endpoint.
    """

    dependencies = [
        ("training", "0004_add_records_and_goals"),
    ]

    operations = [
        migrations.AddField(
            model_name="completedworkout",
            name="device_name",
            field=models.CharField(
                blank=True,
                help_text="Recording device name (e.g., 'Garmin Forerunner 265')",
                max_length=100,
            ),
        ),
    ]
