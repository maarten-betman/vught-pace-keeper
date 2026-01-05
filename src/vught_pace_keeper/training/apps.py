from django.apps import AppConfig


class TrainingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vught_pace_keeper.training"
    verbose_name = "Training Plans"

    def ready(self):
        # Import generators to trigger registration via @register_generator decorator
        from vught_pace_keeper.training import generators  # noqa: F401

        # Import signals to register handlers
        from vught_pace_keeper.training import signals  # noqa: F401
