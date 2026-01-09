"""
Time Utilities Module

Shared utilities for parsing and calculating time-related values.
"""

from datetime import datetime, timezone
from dateutil import parser as dtparser


def parse_utc_datetime(iso_string: str) -> datetime:
    """
    Parse an ISO datetime string to UTC datetime object.
    
    Args:
        iso_string: ISO format datetime string
        
    Returns:
        datetime: UTC datetime object
        
    Raises:
        ValueError: If string cannot be parsed
    """
    dt = dtparser.isoparse(iso_string)
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
