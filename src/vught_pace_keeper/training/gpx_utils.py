"""
GPX file parsing utilities for extracting workout data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import IO

import gpxpy
import gpxpy.gpx
from django.contrib.gis.geos import LineString


@dataclass
class GPXData:
    """Parsed data from a GPX file."""

    distance_km: Decimal
    duration: timedelta
    pace_min_per_km: Decimal
    elevation_gain_m: Decimal | None
    elevation_loss_m: Decimal | None
    route: LineString | None
    start_time: datetime | None
    end_time: datetime | None
    points_count: int
    name: str | None


class GPXParseError(Exception):
    """Exception raised when GPX parsing fails."""

    pass


def parse_gpx_file(file: IO[bytes]) -> GPXData:
    """
    Parse a GPX file and extract workout metrics.

    Args:
        file: A file-like object containing GPX data

    Returns:
        GPXData with extracted metrics

    Raises:
        GPXParseError: If the file cannot be parsed or contains no valid data
    """
    try:
        gpx = gpxpy.parse(file)
    except Exception as e:
        raise GPXParseError(f"Failed to parse GPX file: {e}") from e

    # Collect all points from all tracks/segments
    all_points: list[gpxpy.gpx.GPXTrackPoint] = []
    for track in gpx.tracks:
        for segment in track.segments:
            all_points.extend(segment.points)

    if not all_points:
        raise GPXParseError("GPX file contains no track points")

    # Calculate distance using gpxpy's built-in method (uses haversine)
    # length_3d accounts for elevation, length_2d is just horizontal
    distance_m = gpx.length_3d() or gpx.length_2d()
    if distance_m is None or distance_m <= 0:
        raise GPXParseError("Could not calculate distance from GPX file")

    distance_km = Decimal(str(round(distance_m / 1000, 2)))

    # Calculate duration using moving time (excludes pauses)
    moving_data = gpx.get_moving_data()
    if moving_data and moving_data.moving_time > 0:
        duration_seconds = moving_data.moving_time
    else:
        # Fall back to total time if moving data unavailable
        time_bounds = gpx.get_time_bounds()
        if time_bounds.start_time and time_bounds.end_time:
            duration_seconds = (
                time_bounds.end_time - time_bounds.start_time
            ).total_seconds()
        else:
            raise GPXParseError("GPX file has no timestamp data")

    duration = timedelta(seconds=int(duration_seconds))

    # Calculate pace (min/km)
    if float(distance_km) > 0:
        pace_seconds = duration_seconds / float(distance_km)
        pace_min_per_km = Decimal(str(round(pace_seconds / 60, 2)))
    else:
        pace_min_per_km = Decimal("0")

    # Calculate elevation
    elevation_data = gpx.get_uphill_downhill()
    elevation_gain_m = None
    elevation_loss_m = None
    if elevation_data:
        if elevation_data.uphill is not None:
            elevation_gain_m = Decimal(str(round(elevation_data.uphill, 2)))
        if elevation_data.downhill is not None:
            elevation_loss_m = Decimal(str(round(elevation_data.downhill, 2)))

    # Build LineString from track points
    route = _build_linestring(all_points)

    # Get time bounds
    time_bounds = gpx.get_time_bounds()
    start_time = time_bounds.start_time
    end_time = time_bounds.end_time

    # Get track name
    name = None
    if gpx.tracks:
        name = gpx.tracks[0].name

    return GPXData(
        distance_km=distance_km,
        duration=duration,
        pace_min_per_km=pace_min_per_km,
        elevation_gain_m=elevation_gain_m,
        elevation_loss_m=elevation_loss_m,
        route=route,
        start_time=start_time,
        end_time=end_time,
        points_count=len(all_points),
        name=name,
    )


def _build_linestring(points: list[gpxpy.gpx.GPXTrackPoint]) -> LineString | None:
    """
    Build a PostGIS LineString from GPX track points.

    Args:
        points: List of GPX track points

    Returns:
        LineString geometry or None if insufficient points
    """
    if len(points) < 2:
        return None

    # Extract coordinates as (longitude, latitude) tuples
    # PostGIS uses (x, y) which maps to (lon, lat)
    coords = [(point.longitude, point.latitude) for point in points if point.longitude is not None and point.latitude is not None]

    if len(coords) < 2:
        return None

    # Simplify route if too many points (keep it manageable for storage/display)
    max_points = 1000
    if len(coords) > max_points:
        # Sample every nth point to reduce to max_points
        step = len(coords) // max_points
        coords = coords[::step]
        # Always include the last point
        if coords[-1] != (points[-1].longitude, points[-1].latitude):
            coords.append((points[-1].longitude, points[-1].latitude))

    return LineString(coords, srid=4326)


def format_pace_from_decimal(pace_decimal: Decimal) -> str:
    """
    Format pace from decimal minutes to MM:SS string.

    Args:
        pace_decimal: Pace in decimal minutes (e.g., 5.50 = 5:30)

    Returns:
        Formatted pace string (e.g., "5:30")
    """
    total_seconds = int(float(pace_decimal) * 60)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def format_duration(duration: timedelta) -> str:
    """
    Format duration as H:MM:SS or MM:SS string.

    Args:
        duration: timedelta object

    Returns:
        Formatted duration string
    """
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
