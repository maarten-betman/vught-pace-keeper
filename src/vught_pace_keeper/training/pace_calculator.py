"""
Pace zone calculator based on Jack Daniels' VDOT methodology.

Calculates training pace zones from race results or threshold pace tests.
"""

import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


class PaceCalculationError(Exception):
    """Exception raised when pace calculation fails."""

    pass


# Standard race distances in kilometers
RACE_DISTANCES: dict[str, float] = {
    "5k": 5.0,
    "10k": 10.0,
    "half_marathon": 21.0975,
    "marathon": 42.195,
}

# Zone definitions with effort percentages relative to VO2max pace
# and default colors matching the PaceZone model choices
ZONE_DEFINITIONS: dict[str, dict] = {
    "recovery": {
        "effort_pct": (59, 65),
        "description": "Very easy, conversational pace",
        "color_hex": "#9CA3AF",  # gray-400
    },
    "easy": {
        "effort_pct": (65, 75),
        "description": "Comfortable, could hold a conversation",
        "color_hex": "#22C55E",  # green-500
    },
    "tempo": {
        "effort_pct": (80, 85),
        "description": "Comfortably hard, marathon effort",
        "color_hex": "#EAB308",  # yellow-500
    },
    "threshold": {
        "effort_pct": (85, 90),
        "description": "Hard but sustainable for ~1 hour",
        "color_hex": "#F97316",  # orange-500
    },
    "interval": {
        "effort_pct": (95, 100),
        "description": "Hard, 3-5 minute repeats at VO2max",
        "color_hex": "#EF4444",  # red-500
    },
    "repetition": {
        "effort_pct": (105, 115),
        "description": "Very hard, short fast bursts",
        "color_hex": "#A855F7",  # purple-500
    },
}

# VDOT to training pace lookup table (from Jack Daniels' tables)
# Format: VDOT -> {zone: pace_min_per_km}
# These are interpolated for values between table entries
VDOT_PACE_TABLE: dict[int, dict[str, float]] = {
    30: {"easy": 7.47, "threshold": 6.38, "interval": 5.85, "repetition": 5.42},
    35: {"easy": 6.85, "threshold": 5.85, "interval": 5.35, "repetition": 4.95},
    40: {"easy": 6.30, "threshold": 5.38, "interval": 4.92, "repetition": 4.55},
    45: {"easy": 5.85, "threshold": 5.00, "interval": 4.55, "repetition": 4.22},
    50: {"easy": 5.47, "threshold": 4.67, "interval": 4.23, "repetition": 3.92},
    55: {"easy": 5.13, "threshold": 4.38, "interval": 3.97, "repetition": 3.67},
    60: {"easy": 4.85, "threshold": 4.13, "interval": 3.73, "repetition": 3.45},
    65: {"easy": 4.60, "threshold": 3.92, "interval": 3.53, "repetition": 3.27},
    70: {"easy": 4.38, "threshold": 3.73, "interval": 3.37, "repetition": 3.12},
    75: {"easy": 4.18, "threshold": 3.57, "interval": 3.22, "repetition": 2.98},
    80: {"easy": 4.00, "threshold": 3.42, "interval": 3.08, "repetition": 2.85},
}


@dataclass
class ZoneResult:
    """Result of a pace zone calculation."""

    name: str
    min_pace_min_per_km: Decimal
    max_pace_min_per_km: Decimal
    description: str
    color_hex: str


@dataclass
class CalculationResult:
    """Complete result of a VDOT-based calculation."""

    vdot: float
    zones: list[ZoneResult]
    source_description: str  # e.g., "5K in 22:00" or "Threshold pace 5:00/km"


class PaceZoneCalculator:
    """
    Calculator for training pace zones using Jack Daniels' VDOT methodology.

    Usage:
        calculator = PaceZoneCalculator()

        # From a race result
        result = calculator.from_race_result("5k", timedelta(minutes=22))

        # From threshold pace
        result = calculator.from_threshold_pace(Decimal("5.00"))
    """

    def from_race_result(
        self,
        distance: str | float,
        time: timedelta,
    ) -> CalculationResult:
        """
        Calculate pace zones from a race result.

        Args:
            distance: Race distance as string ("5k", "10k", "half_marathon", "marathon")
                     or distance in kilometers as float
            time: Race finish time

        Returns:
            CalculationResult with VDOT and pace zones

        Raises:
            PaceCalculationError: If inputs are invalid
        """
        # Resolve distance to kilometers
        if isinstance(distance, str):
            distance_km = RACE_DISTANCES.get(distance.lower())
            if distance_km is None:
                raise PaceCalculationError(f"Unknown race distance: {distance}")
            distance_label = distance.upper().replace("_", " ")
        else:
            distance_km = float(distance)
            distance_label = f"{distance_km:.2f}km"

        if distance_km <= 0:
            raise PaceCalculationError("Distance must be positive")

        total_seconds = time.total_seconds()
        if total_seconds <= 0:
            raise PaceCalculationError("Time must be positive")

        # Validate reasonable pace (between 2:00/km and 15:00/km)
        pace_min_per_km = (total_seconds / 60) / distance_km
        if pace_min_per_km < 2.0:
            raise PaceCalculationError(
                "Pace is faster than world record territory. Please check your input."
            )
        if pace_min_per_km > 15.0:
            raise PaceCalculationError(
                "Pace is very slow. Please check your input."
            )

        # Calculate VDOT
        vdot = self._calculate_vdot(distance_km, total_seconds)

        # Generate zones from VDOT
        zones = self._generate_zones(vdot)

        # Format time for description
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        if hours > 0:
            time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes}:{seconds:02d}"

        return CalculationResult(
            vdot=round(vdot, 1),
            zones=zones,
            source_description=f"{distance_label} in {time_str}",
        )

    def from_threshold_pace(
        self,
        threshold_pace: Decimal,
    ) -> CalculationResult:
        """
        Calculate pace zones from threshold (lactate threshold) pace.

        Args:
            threshold_pace: Threshold pace in min/km (decimal, e.g., 5.00 = 5:00/km)

        Returns:
            CalculationResult with VDOT and pace zones

        Raises:
            PaceCalculationError: If pace is out of valid range
        """
        pace_float = float(threshold_pace)

        if pace_float < 2.5:
            raise PaceCalculationError(
                "Threshold pace is faster than elite level. Please check your input."
            )
        if pace_float > 10.0:
            raise PaceCalculationError(
                "Threshold pace seems very slow. Please check your input."
            )

        # Derive VDOT from threshold pace by reverse lookup
        vdot = self._vdot_from_threshold(pace_float)

        # Generate zones
        zones = self._generate_zones(vdot)

        # Format pace for description
        pace_str = self._format_pace(threshold_pace)

        return CalculationResult(
            vdot=round(vdot, 1),
            zones=zones,
            source_description=f"Threshold pace {pace_str}/km",
        )

    def _calculate_vdot(self, distance_km: float, time_seconds: float) -> float:
        """
        Calculate VDOT from race performance using Jack Daniels' formula.

        The formula estimates VO2max (VDOT) based on:
        1. Oxygen cost of running at race pace
        2. Fraction of VO2max sustainable for that duration

        This is a simplified version that interpolates from the pace table.
        """
        # Calculate race pace in min/km
        pace = (time_seconds / 60) / distance_km

        # Find VDOT by interpolating threshold pace
        # (threshold is the most reliable predictor)
        return self._vdot_from_pace(pace, "threshold", offset=-0.15)

    def _vdot_from_threshold(self, threshold_pace: float) -> float:
        """Derive VDOT from threshold pace."""
        return self._vdot_from_pace(threshold_pace, "threshold")

    def _vdot_from_pace(
        self, pace: float, zone: str, offset: float = 0
    ) -> float:
        """
        Find VDOT that corresponds to a given pace for a zone.

        Uses linear interpolation between table entries.
        """
        vdot_values = sorted(VDOT_PACE_TABLE.keys())

        # Adjust pace for the offset (race pace is slightly faster than threshold)
        adjusted_pace = pace + offset

        # Find the two VDOT values that bracket this pace
        for i in range(len(vdot_values) - 1):
            lower_vdot = vdot_values[i]
            upper_vdot = vdot_values[i + 1]

            lower_pace = VDOT_PACE_TABLE[lower_vdot][zone]
            upper_pace = VDOT_PACE_TABLE[upper_vdot][zone]

            # Pace decreases as VDOT increases
            if lower_pace >= adjusted_pace >= upper_pace:
                # Linear interpolation
                fraction = (lower_pace - adjusted_pace) / (lower_pace - upper_pace)
                return lower_vdot + fraction * (upper_vdot - lower_vdot)

        # If pace is outside table range, clamp to nearest
        if adjusted_pace > VDOT_PACE_TABLE[vdot_values[0]][zone]:
            return float(vdot_values[0])
        return float(vdot_values[-1])

    def _generate_zones(self, vdot: float) -> list[ZoneResult]:
        """Generate pace zones from VDOT value."""
        # Interpolate paces for this VDOT
        paces = self._interpolate_paces(vdot)

        zones = []

        # Recovery zone: slightly slower than easy
        recovery_pace = paces["easy"] * 1.15  # ~15% slower than easy
        zones.append(
            ZoneResult(
                name="recovery",
                min_pace_min_per_km=Decimal(str(round(recovery_pace, 2))),
                max_pace_min_per_km=Decimal(str(round(paces["easy"] * 1.05, 2))),
                description=ZONE_DEFINITIONS["recovery"]["description"],
                color_hex=ZONE_DEFINITIONS["recovery"]["color_hex"],
            )
        )

        # Easy zone
        zones.append(
            ZoneResult(
                name="easy",
                min_pace_min_per_km=Decimal(str(round(paces["easy"] * 1.05, 2))),
                max_pace_min_per_km=Decimal(str(round(paces["easy"] * 0.95, 2))),
                description=ZONE_DEFINITIONS["easy"]["description"],
                color_hex=ZONE_DEFINITIONS["easy"]["color_hex"],
            )
        )

        # Tempo zone (marathon pace area)
        tempo_pace = (paces["easy"] + paces["threshold"]) / 2
        zones.append(
            ZoneResult(
                name="tempo",
                min_pace_min_per_km=Decimal(str(round(paces["easy"] * 0.95, 2))),
                max_pace_min_per_km=Decimal(str(round(tempo_pace, 2))),
                description=ZONE_DEFINITIONS["tempo"]["description"],
                color_hex=ZONE_DEFINITIONS["tempo"]["color_hex"],
            )
        )

        # Threshold zone
        zones.append(
            ZoneResult(
                name="threshold",
                min_pace_min_per_km=Decimal(str(round(tempo_pace, 2))),
                max_pace_min_per_km=Decimal(str(round(paces["threshold"], 2))),
                description=ZONE_DEFINITIONS["threshold"]["description"],
                color_hex=ZONE_DEFINITIONS["threshold"]["color_hex"],
            )
        )

        # Interval zone
        zones.append(
            ZoneResult(
                name="interval",
                min_pace_min_per_km=Decimal(str(round(paces["threshold"], 2))),
                max_pace_min_per_km=Decimal(str(round(paces["interval"], 2))),
                description=ZONE_DEFINITIONS["interval"]["description"],
                color_hex=ZONE_DEFINITIONS["interval"]["color_hex"],
            )
        )

        # Repetition zone
        zones.append(
            ZoneResult(
                name="repetition",
                min_pace_min_per_km=Decimal(str(round(paces["interval"], 2))),
                max_pace_min_per_km=Decimal(str(round(paces["repetition"], 2))),
                description=ZONE_DEFINITIONS["repetition"]["description"],
                color_hex=ZONE_DEFINITIONS["repetition"]["color_hex"],
            )
        )

        return zones

    def _interpolate_paces(self, vdot: float) -> dict[str, float]:
        """Interpolate training paces for a given VDOT value."""
        vdot_values = sorted(VDOT_PACE_TABLE.keys())

        # Clamp VDOT to table range
        if vdot <= vdot_values[0]:
            return VDOT_PACE_TABLE[vdot_values[0]].copy()
        if vdot >= vdot_values[-1]:
            return VDOT_PACE_TABLE[vdot_values[-1]].copy()

        # Find bracketing values
        for i in range(len(vdot_values) - 1):
            lower = vdot_values[i]
            upper = vdot_values[i + 1]

            if lower <= vdot <= upper:
                fraction = (vdot - lower) / (upper - lower)
                result = {}
                for zone in VDOT_PACE_TABLE[lower]:
                    lower_pace = VDOT_PACE_TABLE[lower][zone]
                    upper_pace = VDOT_PACE_TABLE[upper][zone]
                    result[zone] = lower_pace + fraction * (upper_pace - lower_pace)
                return result

        # Fallback (shouldn't reach here)
        return VDOT_PACE_TABLE[vdot_values[0]].copy()

    def _format_pace(self, pace_decimal: Decimal) -> str:
        """Format pace as M:SS string."""
        total_seconds = int(float(pace_decimal) * 60)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"


def get_zone_for_pace(pace: Decimal, zones: list[ZoneResult]) -> str | None:
    """
    Determine which zone a pace falls into.

    Args:
        pace: Pace in min/km
        zones: List of ZoneResult objects

    Returns:
        Zone name or None if pace doesn't fall into any zone
    """
    pace_float = float(pace)

    for zone in zones:
        min_pace = float(zone.min_pace_min_per_km)
        max_pace = float(zone.max_pace_min_per_km)

        # Note: slower pace = higher number, faster pace = lower number
        if max_pace <= pace_float <= min_pace:
            return zone.name

    # If pace is slower than recovery (min of slowest zone)
    if zones and pace_float > float(zones[0].min_pace_min_per_km):
        return "recovery"

    # If pace is faster than repetition (max of fastest zone)
    if zones and pace_float < float(zones[-1].max_pace_min_per_km):
        return "repetition"

    return None
