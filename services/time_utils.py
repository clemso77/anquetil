"""
Time Utilities Module

Shared utilities for parsing and calculating time-related values.
Uses only Python stdlib — no third-party date libraries required.
"""

from datetime import datetime, timezone


def parse_utc_datetime(iso_string: str) -> datetime:
    """
    Parse an ISO datetime string to a UTC-aware datetime object.

    Accepts any ISO 8601 string handled by ``datetime.fromisoformat``.
    Trailing "Z" (Zulu) is normalised to "+00:00" for Python < 3.11
    compatibility.

    Args:
        iso_string: ISO 8601 datetime string (e.g. "2024-06-01T14:30:00+02:00").

    Returns:
        datetime: UTC-aware datetime object.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    normalised = (iso_string or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalised)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_wait_minutes(utc_iso_string: str) -> int:
    """
    Calculate minutes until departure from UTC ISO timestamp.
    This is called dynamically on every render to ensure accurate display.
    
    Args:
        utc_iso_string: ISO format UTC timestamp
        
    Returns:
        int: Minutes until departure (minimum 0)
    """
    try:
        dt = parse_utc_datetime(utc_iso_string)
        now = datetime.now(timezone.utc)
        seconds = (dt - now).total_seconds()
        return max(0, int((seconds + 59) // 60))
    except (ValueError, TypeError, AttributeError):
        # Return 0 if parsing fails or invalid data
        return 0
