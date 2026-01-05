"""Training plan generators package."""

from .base import (
    BasePlanGenerator,
    FitnessProfile,
    GeneratedPlan,
    GeneratedWeek,
    GeneratedWorkout,
    PlanConfig,
)
from .registry import PlanGeneratorRegistry, register_generator

# Import generators to trigger registration via @register_generator decorator
from . import custom  # noqa: F401

__all__ = [
    "BasePlanGenerator",
    "FitnessProfile",
    "GeneratedPlan",
    "GeneratedWeek",
    "GeneratedWorkout",
    "PlanConfig",
    "PlanGeneratorRegistry",
    "register_generator",
]
