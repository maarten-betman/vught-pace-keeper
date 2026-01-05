"""Registry for training plan generators."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BasePlanGenerator


class PlanGeneratorRegistry:
    """
    Registry for training plan generators.

    Generators are registered using the @register_generator decorator.
    The registry is populated when the training app is ready.
    """

    _generators: dict[str, "BasePlanGenerator"] = {}

    @classmethod
    def register(cls, generator: "BasePlanGenerator") -> None:
        """Register a generator instance."""
        cls._generators[generator.methodology_name] = generator

    @classmethod
    def get_generator(cls, methodology: str) -> "BasePlanGenerator | None":
        """Get a generator by methodology name."""
        return cls._generators.get(methodology)

    @classmethod
    def get_all_generators(cls) -> dict[str, "BasePlanGenerator"]:
        """Get all registered generators."""
        return cls._generators.copy()

    @classmethod
    def get_choices(cls) -> list[tuple[str, str]]:
        """
        Get choices for form select fields.

        Returns list of (methodology_name, display_name) tuples.
        """
        return [
            (name, gen.display_name) for name, gen in cls._generators.items()
        ]

    @classmethod
    def get_for_distance(cls, plan_type: str) -> list["BasePlanGenerator"]:
        """Get generators supporting a specific distance."""
        return [
            gen
            for gen in cls._generators.values()
            if plan_type in gen.supported_distances
        ]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered generators. Useful for testing."""
        cls._generators.clear()


def register_generator(cls):
    """
    Class decorator to register a plan generator.

    Usage:
        @register_generator
        class MyGenerator(BasePlanGenerator):
            methodology_name = "my_method"
            ...
    """
    PlanGeneratorRegistry.register(cls())
    return cls
