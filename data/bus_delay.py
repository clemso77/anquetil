import os
import time
import requests
from datetime import datetime, timezone
from dateutil import parser as dtparser


PRIM_API_KEY = os.getenv("PRIM_API_KEY")
PRIM_URL = "https://prim.iledefrance-mobilites.fr/marketplace/estimated-timetable"


def _parse_dt(value: str) -> datetime:
    dt = dtparser.isoparse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _minutes_until(dt: datetime) -> int:
    now = datetime.now(timezone.utc)
    seconds = (dt - now).total_seconds()
    return max(0, int((seconds + 59) // 60))


def get_waiting_times(stop_point_ref: str, limit: int = 5):
    """
    Retourne les prochains passages pour un arrêt donné.

    :param stop_point_ref: ex 'STIF:StopPoint:Q:29631:'
    :param limit: nombre de résultats max
    :return: liste de dict
    """

    if not PRIM_API_KEY:
        raise RuntimeError("PRIM_API_KEY manquant (variable d'environnement)")

    headers = {
        "apikey": PRIM_API_KEY,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }

    params = {"LineRef": "ALL"}

    response = requests.get(
        PRIM_URL,
        headers=headers,
        params=params,
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    results = []

    def walk(obj):
        nonlocal results
        if len(results) >= limit:
            return

        if isinstance(obj, dict):
            if (
                "StopPointRef" in obj
                and ("ExpectedDepartureTime" in obj or "AimedDepartureTime" in obj)
            ):
                sp = obj["StopPointRef"]
                sp_val = sp.get("value") if isinstance(sp, dict) else sp

                if sp_val == stop_point_ref:
                    ts = obj.get("ExpectedDepartureTime") or obj.get("AimedDepartureTime")
                    try:
                        dt = _parse_dt(ts)
                    except Exception:
                        return

                    results.append({
                        "expected_departure_utc": dt.isoformat(),
                        "wait_minutes": _minutes_until(dt),
                        "line_ref": obj.get("LineRef"),
                        "destination_ref": obj.get("DestinationRef"),
                        "status": obj.get("DepartureStatus"),
                    })

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for item in obj:
                if len(results) >= limit:
                    return
                walk(item)

    walk(data)

    results.sort(key=lambda x: x["expected_departure_utc"])
    return results
