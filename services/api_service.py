"""
API Service Module

Centralizes all network calls (fetch) for the application.
Handles timeouts, retries, and request cancellation.
"""

import os
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dateutil import parser as dtparser
import requests


class APIService:
    """
    Service responsible for all external API calls.
    Provides methods to fetch bus waiting times with proper error handling.
    """

    def __init__(self):
        """Initialize the API service."""
        self.api_key = os.getenv("PRIM_API_KEY")
        self.base_url = "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring"
        self._current_request: Optional[threading.Thread] = None
        self._cancel_requested = False
        
    def _parse_datetime(self, value: str) -> datetime:
        """
        Parse an ISO datetime string to UTC datetime object.
        
        Args:
            value: ISO format datetime string
            
        Returns:
            datetime: UTC datetime object
        """
        dt = dtparser.isoparse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _calculate_wait_minutes(self, dt: datetime) -> int:
        """
        Calculate minutes until the given datetime.
        
        Args:
            dt: Target datetime in UTC
            
        Returns:
            int: Minutes until target time (minimum 0)
        """
        now = datetime.now(timezone.utc)
        seconds = (dt - now).total_seconds()
        return max(0, int((seconds + 59) // 60))

    def cancel_current_request(self):
        """
        Cancel any ongoing request.
        Note: requests library doesn't support true cancellation,
        but we can flag it to ignore the result.
        """
        self._cancel_requested = True

    def fetch_waiting_times(
        self, 
        stop_point_ref: str, 
        limit: int = 5,
        timeout: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Fetch bus waiting times for a specific stop point.
        
        Args:
            stop_point_ref: Stop point reference (e.g., 'STIF:StopPoint:Q:29631:')
            limit: Maximum number of results to return
            timeout: Request timeout in seconds
            
        Returns:
            List of dictionaries containing:
                - expected_departure_utc: ISO format departure time
                - wait_minutes: Minutes until departure
                - line_ref: Bus line reference
                - destination_ref: Destination reference
                - status: Departure status
                
        Raises:
            RuntimeError: If API key is missing
            requests.RequestException: If network request fails
        """
        self._cancel_requested = False
        
        if not self.api_key:
            raise RuntimeError("PRIM_API_KEY environment variable is not set")

        headers = {
            "apikey": self.api_key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }

        params = {"MonitoringRef": stop_point_ref}

        try:
            response = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            print("[DEBUG] URL:", response.url)
            print("[DEBUG] Status:", response.status_code)
            print("[DEBUG] Content-Type:", response.headers.get("Content-Type"))
            print("[DEBUG] Content-Encoding:", response.headers.get("Content-Encoding"))
            
            # Check if cancellation was requested
            if self._cancel_requested:
                return []
            
            data = response.json()
            print("[DEBUG] Top-level keys:", list(data.keys())[:10])
            deliveries = data.get("Siri", {}).get("ServiceDelivery", {}).get("StopMonitoringDelivery", [])
            results = []

            for d in deliveries:
                for visit in d.get("MonitoredStopVisit", []) or []:
                    mr = visit.get("MonitoringRef", {})
                    if (mr.get("value") if isinstance(mr, dict) else mr) != stop_point_ref:
                        continue

                    mvj = visit.get("MonitoredVehicleJourney", {}) or {}
                    call = mvj.get("MonitoredCall", {}) or {}
                    ts = call.get("ExpectedDepartureTime") or call.get("AimedDepartureTime")
                    if not ts:
                        continue

                    dt = self._parse_datetime(ts)
                    results.append({
                        "expected_departure_utc": dt.isoformat(),
                        "wait_minutes": self._calculate_wait_minutes(dt),
                        "line_ref": (mvj.get("LineRef") or {}).get("value"),
                        "destination_ref": (mvj.get("DestinationRef") or {}).get("value"),
                        "status": call.get("DepartureStatus"),
                    })

            print(results)
            results.sort(key=lambda x: x["expected_departure_utc"])
            print(results)
            return results[:limit]

        except requests.Timeout:
            raise RuntimeError(f"Request timeout after {timeout} seconds")
        except requests.RequestException as e:
            raise RuntimeError(f"Network error: {str(e)}")


# Singleton instance
_api_service_instance: Optional[APIService] = None


def get_api_service() -> APIService:
    """
    Get the singleton API service instance.
    
    Returns:
        APIService: The API service instance
    """
    global _api_service_instance
    if _api_service_instance is None:
        _api_service_instance = APIService()
    return _api_service_instance