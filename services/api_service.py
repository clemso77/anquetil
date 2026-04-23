"""
API Service Module

Centralizes all network calls (fetch) for the application.
Handles timeouts, per-item parse errors, and automatic retries with
exponential back-off on transient network failures.
"""

import logging
import os
import time
from typing import List, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

from .time_utils import parse_utc_datetime

logger = logging.getLogger(__name__)


class APIService:
    """
    Service responsible for all external API calls.

    Provides methods to fetch bus waiting times with proper error handling,
    automatic retries, and per-item parse tolerance.
    """

    #: Number of automatic retries on transient failures (5xx / connection errors).
    MAX_RETRIES = 3
    #: Initial back-off between retries (seconds).
    BACKOFF_FACTOR = 1.0

    def __init__(self):
        """Initialise the API service and configure a retry-enabled session."""
        self.api_key = os.getenv("PRIM_API_KEY")
        self.base_url = (
            "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring"
        )

        retry_policy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.BACKOFF_FACTOR,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods={"GET"},
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        self._session = requests.Session()
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def fetch_waiting_times(
        self,
        stop_point_ref: str,
        limit: int = 5,
        timeout: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Fetch bus waiting times for a specific stop point.

        Individual departures that carry malformed timestamps are silently
        skipped so that one bad entry never discards the entire response.

        Args:
            stop_point_ref: Stop point reference (e.g. 'STIF:StopPoint:Q:29631:').
            limit: Maximum number of results to return.
            timeout: Request timeout in seconds.

        Returns:
            List of dictionaries, each containing:
                - ``expected_departure_utc``: ISO-format UTC departure time.
                - ``line_ref``: Bus line reference.
                - ``destination_ref``: Destination reference.
                - ``status``: Departure status string.

        Raises:
            RuntimeError: If the API key is missing or the request fails.
        """
        if not self.api_key:
            raise RuntimeError("PRIM_API_KEY environment variable is not set")

        headers = {
            "apikey": self.api_key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        params = {"MonitoringRef": stop_point_ref}

        try:
            response = self._session.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.Timeout:
            raise RuntimeError(f"Request timeout after {timeout} seconds")
        except requests.RequestException as exc:
            raise RuntimeError(f"Network error: {exc}") from exc

        data = response.json()
        deliveries = (
            data.get("Siri", {})
            .get("ServiceDelivery", {})
            .get("StopMonitoringDelivery", [])
        )
        results: List[Dict[str, Any]] = []

        for delivery in deliveries:
            for visit in delivery.get("MonitoredStopVisit", []) or []:
                mr = visit.get("MonitoringRef", {})
                ref_value = mr.get("value") if isinstance(mr, dict) else mr
                if ref_value != stop_point_ref:
                    continue

                mvj = visit.get("MonitoredVehicleJourney", {}) or {}
                call = mvj.get("MonitoredCall", {}) or {}
                ts = call.get("ExpectedDepartureTime") or call.get(
                    "AimedDepartureTime"
                )
                if not ts:
                    continue

                try:
                    dt = parse_utc_datetime(ts)
                except (ValueError, TypeError) as exc:
                    logger.warning("Skipping departure with unparseable timestamp %r: %s", ts, exc)
                    continue

                results.append(
                    {
                        "expected_departure_utc": dt.isoformat(),
                        "line_ref": (mvj.get("LineRef") or {}).get("value"),
                        "destination_ref": (mvj.get("DestinationRef") or {}).get(
                            "value"
                        ),
                        "status": call.get("DepartureStatus"),
                    }
                )

        results.sort(key=lambda x: x["expected_departure_utc"])
        return results[:limit]

    def close(self):
        """Close the underlying HTTP session and release connections."""
        self._session.close()


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_api_service_instance: Optional[APIService] = None


def get_api_service() -> APIService:
    """Return the singleton :class:`APIService` instance (created on first call)."""
    global _api_service_instance
    if _api_service_instance is None:
        _api_service_instance = APIService()
    return _api_service_instance