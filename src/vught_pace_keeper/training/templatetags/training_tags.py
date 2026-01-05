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
