import os
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import requests
from dateutil import parser as dtparser
from fastapi import FastAPI, HTTPException, Query

# ============================================================
# Configuration
# ============================================================

PRIM_API_KEY = os.getenv("PRIM_API_KEY")  # à fournir via variable d'env
PRIM_BASE_URL = os.getenv("PRIM_BASE_URL", "https://prim.iledefrance-mobilites.fr/marketplace")

# Endpoint "requête globale": GET /estimated-timetable + param LineRef=ALL :contentReference[oaicite:2]{index=2}
ESTIMATED_TIMETABLE_URL = f"{PRIM_BASE_URL}/estimated-timetable"
LINE_REF_ALL = "ALL"

# Cache: la donnée est mise à jour environ chaque minute :contentReference[oaicite:3]{index=3}
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", ""))

# Timeout HTTP (sec)
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "20"))

app = FastAPI(title="IDFM Waiting Time Service", version="1.0.0")

# Cache simple en mémoire
_cache: Dict[str, Any] = {
    "ts": 0.0,
    "payload": None,   # response JSON (dict) ou bytes, selon stratégie
    "etag": None,
}


# ============================================================
# Utilitaires
# ============================================================

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _minutes_until(dt: datetime, now: Optional[datetime] = None) -> int:
    now = now or _now_utc()
    delta = dt - now
    # on arrondit à la minute supérieure pour un rendu "temps d'attente" pratique
    minutes = int((delta.total_seconds() + 59) // 60)
    return max(minutes, 0)

def _parse_dt(value: str) -> datetime:
    """
    Les timestamps sont généralement ISO8601, souvent en 'Z' (UTC) côté JSON. :contentReference[oaicite:4]{index=4}
    """
    dt = dtparser.isoparse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ============================================================
# Fetch + cache
# ============================================================

def _fetch_estimated_timetable_all() -> Any:
    """
    Appelle /estimated-timetable?LineRef=ALL avec header apikey (PRIM). :contentReference[oaicite:5]{index=5}
    Retourne du JSON (dict) si possible.
    """
    if not PRIM_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="PRIM_API_KEY manquant (variable d'environnement)."
        )

    headers = {
        "apikey": PRIM_API_KEY,  # header utilisé dans les exemples PRIM :contentReference[oaicite:6]{index=6}
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }

    params = {"LineRef": LINE_REF_ALL}

    resp = requests.get(
        ESTIMATED_TIMETABLE_URL,
        headers=headers,
        params=params,
        timeout=HTTP_TIMEOUT,
    )

    if resp.status_code == 401 or resp.status_code == 403:
        raise HTTPException(status_code=502, detail="Auth PRIM refusée (apikey invalide ?).")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erreur PRIM {resp.status_code}: {resp.text[:500]}")

    # PRIM renvoie souvent du JSON sur cet endpoint (ex. cité avec du JSON) :contentReference[oaicite:7]{index=7}
    try:
        return resp.json()
    except Exception:
        # fallback brut (au cas où content-type pas JSON)
        return resp.content


def _get_cached_or_fetch() -> Any:
    now = time.time()
    if _cache["payload"] is not None and (now - _cache["ts"]) < CACHE_TTL_SECONDS:
        return _cache["payload"]

    payload = _fetch_estimated_timetable_all()
    _cache["payload"] = payload
    _cache["ts"] = now
    return payload


# ============================================================
# Parsing (stratégie robuste)
# ============================================================

def _extract_calls_from_json(payload: Any, stop_ref: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Essaie d'extraire des "EstimatedCalls" qui contiennent StopPointRef et ExpectedDepartureTime.
    La structure exacte peut varier; on parcourt récursivement.
    Exemple de champs rencontrés: StopPointRef.value, AimedDepartureTime, ExpectedDepartureTime. :contentReference[oaicite:8]{index=8}
    """
    results: List[Dict[str, Any]] = []

    def walk(obj: Any, context: Dict[str, Any]):
        nonlocal results
        if len(results) >= max_results:
            return

        if isinstance(obj, dict):
            # capture de certains champs contextuels si présents
            new_context = dict(context)
            for k in ("LineRef", "DirectionRef", "DestinationRef", "DatedVehicleJourneyRef", "VehicleJourneyRef"):
                if k in obj and isinstance(obj[k], (str, dict)):
                    new_context[k] = obj[k]

            # Si c'est un bloc "EstimatedCalls" ou un "EstimatedCall" on traite
            # On cherche StopPointRef + ExpectedDepartureTime (ou AimedDepartureTime)
            if "StopPointRef" in obj and ("ExpectedDepartureTime" in obj or "AimedDepartureTime" in obj):
                sp = obj.get("StopPointRef")
                # StopPointRef peut être {"value": "..."} :contentReference[oaicite:9]{index=9}
                if isinstance(sp, dict) and "value" in sp:
                    sp_val = sp["value"]
                else:
                    sp_val = sp

                if sp_val == stop_ref:
                    expected = obj.get("ExpectedDepartureTime") or obj.get("AimedDepartureTime")
                    aimed = obj.get("AimedDepartureTime")
                    results.append({
                        "stop_ref": sp_val,
                        "expected_departure_time": expected,
                        "aimed_departure_time": aimed,
                        "departure_status": obj.get("DepartureStatus"),
                        "arrival_status": obj.get("ArrivalStatus"),
                        "line_ref": new_context.get("LineRef"),
                        "direction_ref": new_context.get("DirectionRef"),
                        "destination_ref": new_context.get("DestinationRef"),
                        "journey_ref": new_context.get("DatedVehicleJourneyRef") or new_context.get("VehicleJourneyRef"),
                    })

            # Continuer la descente
            for v in obj.values():
                walk(v, new_context)

        elif isinstance(obj, list):
            for item in obj:
                if len(results) >= max_results:
                    return
                walk(item, context)

    walk(payload, context={})
    return results


# ============================================================
# API HTTP
# ============================================================

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/waiting-times")
def waiting_times(
    stop_ref: str = Query(..., description="Ex: STIF:StopPoint:Q:29631:"),
    limit: int = Query(6, ge=1, le=20),
):
    """
    Renvoie les prochains départs à stop_ref + attente en minutes.
    """
    payload = _get_cached_or_fetch()

    if isinstance(payload, (bytes, bytearray)):
        raise HTTPException(
            status_code=502,
            detail="Réponse PRIM non-JSON reçue (content brut). Ajuste Accept ou ajoute un parse XML si nécessaire."
        )

    calls = _extract_calls_from_json(payload, stop_ref=stop_ref, max_results=limit * 3)
    if not calls:
        # soit arrêt non couvert par la donnée TR, soit stop_ref incorrect
        return {
            "stop_ref": stop_ref,
            "count": 0,
            "items": [],
            "note": "Aucun passage trouvé. Vérifie stop_ref (StopPointRef) et la couverture temps réel."
        }

    now = _now_utc()
    items: List[Dict[str, Any]] = []

    for c in calls:
        expected_str = c.get("expected_departure_time")
        if not expected_str:
            continue
        try:
            expected_dt = _parse_dt(expected_str)
        except Exception:
            continue

        items.append({
            "line_ref": c.get("line_ref"),
            "journey_ref": c.get("journey_ref"),
            "expected_departure_time_utc": expected_dt.isoformat(),
            "wait_minutes": _minutes_until(expected_dt, now=now),
            "departure_status": c.get("departure_status"),
            "destination_ref": c.get("destination_ref"),
        })

    # Trier par temps de départ
    items.sort(key=lambda x: x["expected_departure_time_utc"])
    items = items[:limit]

    return {
        "stop_ref": stop_ref,
        "generated_at_utc": now.isoformat(),
        "count": len(items),
        "items": items,
        "cache": {
            "ttl_seconds": CACHE_TTL_SECONDS,
            "age_seconds": int(time.time() - _cache["ts"]) if _cache["ts"] else None,
        }
    }
