"""
Bus Delay Module

Legacy wrapper around API service for backwards compatibility.
Direct use is deprecated - use services.api_service instead.
"""

from services import get_api_service


def get_waiting_times(stop_point_ref: str, limit: int = 5):
    """
    Fetch bus waiting times for a specific stop point.
    
    DEPRECATED: Use services.api_service.fetch_waiting_times() instead.
    This function is maintained for backwards compatibility only.
    
    Args:
        stop_point_ref: Stop point reference (e.g., 'STIF:StopPoint:Q:29631:')
        limit: Maximum number of results to return
        
    Returns:
        List of dictionaries containing departure information
    """
    api_service = get_api_service()
    return api_service.fetch_waiting_times(stop_point_ref, limit)
