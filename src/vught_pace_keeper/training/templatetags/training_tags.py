"""Template tags and filters for training app."""

from django import template

register = template.Library()


DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}


@register.filter
def day_name(day_number):
    """
    Convert day number (1-7) to day name.

    Usage: {{ workout.day_of_week|day_name }}
    """
    try:
        return DAY_NAMES.get(int(day_number), str(day_number))
    except (ValueError, TypeError):
        return str(day_number)


@register.filter
def format_pace(pace_decimal):
    """
    Format pace decimal as M:SS/km.

    Usage: {{ workout.target_pace_min_per_km|format_pace }}

    Example: 5.50 -> "5:30/km"
    """
    if pace_decimal is None:
        return "-"
    try:
        minutes = int(pace_decimal)
        seconds = int((float(pace_decimal) - minutes) * 60)
        return f"{minutes}:{seconds:02d}/km"
    except (ValueError, TypeError):
        return str(pace_decimal)


@register.filter
def format_duration(duration):
    """
    Format timedelta as H:MM:SS or MM:SS.

    Usage: {{ workout.target_duration|format_duration }}
    """
    if duration is None:
        return "-"
    try:
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    except (AttributeError, TypeError):
        return str(duration)


@register.filter
def format_elevation(elevation_m):
    """
    Format elevation in meters.

    Usage: {{ workout.elevation_gain_m|format_elevation }}

    Example: 156.5 -> "157m", 1250 -> "1.25km"
    """
    if elevation_m is None:
        return "-"
    try:
        meters = float(elevation_m)
        if meters >= 1000:
            return f"{meters / 1000:.2f}km"
        return f"{int(round(meters))}m"
    except (ValueError, TypeError):
        return str(elevation_m)


@register.filter
def format_effort(effort):
    """
    Format perceived effort (1-10) with color class.

    Usage: {{ workout.perceived_effort|format_effort }}

    Returns tuple (display_text, css_class)
    """
    if effort is None:
        return "-"
    try:
        effort_int = int(effort)
        return str(effort_int)
    except (ValueError, TypeError):
        return str(effort)


@register.filter
def effort_color(effort):
    """
    Get Tailwind color class for effort level.

    Usage: <span class="{{ workout.perceived_effort|effort_color }}">
    """
    if effort is None:
        return "text-gray-400"
    try:
        effort_int = int(effort)
        if effort_int <= 3:
            return "text-green-600"
        elif effort_int <= 5:
            return "text-yellow-600"
        elif effort_int <= 7:
            return "text-orange-600"
        else:
            return "text-red-600"
    except (ValueError, TypeError):
        return "text-gray-400"


@register.filter
def format_distance(distance_km):
    """
    Format distance in kilometers with 2 decimal places.

    Usage: {{ workout.actual_distance_km|format_distance }}

    Example: 10.5 -> "10.50 km"
    """
    if distance_km is None:
        return "-"
    try:
        return f"{float(distance_km):.2f} km"
    except (ValueError, TypeError):
        return str(distance_km)


@register.filter
def source_badge_class(source):
    """
    Get Tailwind classes for workout source badge.

    Usage: <span class="{{ workout.source|source_badge_class }}">
    """
    classes = {
        "manual": "bg-blue-100 text-blue-700",
        "gpx_upload": "bg-purple-100 text-purple-700",
        "strava": "bg-orange-100 text-orange-700",
    }
    return classes.get(source, "bg-gray-100 text-gray-700")
