from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime
import json
import os
from pathlib import Path
import time

from app.data import LOCALITY_BOUNDS, LOCALITY_PLACES, PERSONAS


BASE_URL = "https://www.onemap.gov.sg"
CACHE_DIR = Path(".cache/onemap")


def search_place(search_value):
    params = urlencode({
        "searchVal": search_value,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": "1",
    })
    payload = _request_json(f"{BASE_URL}/api/common/elastic/search?{params}")
    results = payload.get("results", [])
    if not results:
        return None

    result = results[0]
    return {
        "search": search_value,
        "name": result.get("SEARCHVAL") or search_value,
        "address": result.get("ADDRESS"),
        "lat": _number(result.get("LATITUDE")),
        "lng": _number(result.get("LONGITUDE")),
        "postal": result.get("POSTAL"),
        "raw": result,
    }


def resolve_locality_places():
    resolved = []
    for place in LOCALITY_PLACES:
        match = search_place(place["query"])
        if match and not _inside_locality(match):
            match = None
        resolved.append({
            **place,
            "resolved": match,
        })
    return resolved


def route_between(origin, destination, mode="walk"):
    route_type = {
        "walk": "walk",
        "drive": "drive",
        "bus": "pt",
        "public_transport": "pt",
    }.get(mode, mode)

    params = {
        "start": f"{origin['lat']},{origin['lng']}",
        "end": f"{destination['lat']},{destination['lng']}",
        "routeType": route_type,
    }
    if route_type == "pt":
        params["mode"] = "BUS"
        params["date"] = os.getenv("ONEMAP_ROUTE_DATE") or datetime.now().strftime("%m-%d-%Y")
        params["time"] = os.getenv("ONEMAP_ROUTE_TIME") or "08:00:00"
        params["maxWalkDistance"] = os.getenv("ONEMAP_MAX_WALK_DISTANCE") or "1000"
        params["numItineraries"] = "1"

    headers = {}
    token = os.getenv("ONEMAP_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = token

    payload = _request_json(f"{BASE_URL}/api/public/routingsvc/route?{urlencode(params)}", headers=headers)
    return _normalize_route(payload, mode)


def locality_route(origin_id, destination_id, mode="walk"):
    places = {
        item["id"]: item["resolved"]
        for item in resolve_locality_places()
        if item["resolved"]
    }
    origin = places.get(origin_id)
    destination = places.get(destination_id)
    if not origin or not destination:
        missing = origin_id if not origin else destination_id
        raise ValueError(f"Unknown or unresolved OneMap place: {missing}")
    if not _inside_locality(origin) or not _inside_locality(destination):
        raise ValueError("Route endpoint is ringfenced to the MacPherson 5 km POC zone.")
    try:
        return route_between(origin, destination, mode)
    except RuntimeError as exc:
        if mode in ("bus", "public_transport"):
            fallback = route_between(origin, destination, "walk")
            fallback["mode_fallback"] = "walk"
            fallback["note"] = (
                "Bus route was unavailable, so the visual path uses OneMap walking geometry. "
                "Refresh ONEMAP_ACCESS_TOKEN to cache public transport routes."
            )
            return fallback
        raise exc


def route_matrix(limit=8):
    resolved = [item for item in resolve_locality_places() if item["resolved"]]
    shell = next((item for item in resolved if item["id"] == "shell_select"), None)
    if not shell:
        return {
            "places": resolved,
            "routes": [],
            "error": "selected store could not be resolved in OneMap.",
        }

    selected = [item for item in resolved if item["id"] != "shell_select"][:limit]
    routes = []

    for place in selected:
        for origin, destination in ((place, shell), (shell, place)):
            for mode in ("walk", "drive", "bus"):
                try:
                    route = route_between(origin["resolved"], destination["resolved"], mode)
                    routes.append({
                        "origin": origin["id"],
                        "destination": destination["id"],
                        "mode": mode,
                        **route,
                    })
                except Exception as exc:
                    routes.append({
                        "origin": origin["id"],
                        "destination": destination["id"],
                        "mode": mode,
                        "error": str(exc),
                    })

    return {
        "places": [shell, *selected],
        "routes": routes,
        "assumption": "For the POC, bus wait time is treated as 0 minutes.",
    }


def warm_locality_cache():
    places = resolve_locality_places()
    resolved = {item["id"]: item["resolved"] for item in places if item["resolved"]}
    routes = []
    errors = []

    for persona in PERSONAS:
        mode = _persona_route_mode(persona)
        previous = persona.get("home")
        for stop in persona["schedule"]:
            current = stop["place"]
            if previous and current and previous != current:
                if previous in resolved and current in resolved:
                    try:
                        route = locality_route(previous, current, mode)
                        routes.append({
                            "persona": persona["name"],
                            "origin": previous,
                            "destination": current,
                            "mode": mode,
                            "distance_m": route.get("distance_m"),
                            "duration_min": route.get("duration_min"),
                            "geometry_points": len(route.get("geometry", [])),
                        })
                    except Exception as exc:
                        errors.append({
                            "persona": persona["name"],
                            "origin": previous,
                            "destination": current,
                            "mode": mode,
                            "error": str(exc),
                        })
                else:
                    errors.append({
                        "persona": persona["name"],
                        "origin": previous,
                        "destination": current,
                        "mode": mode,
                        "error": "Origin or destination is unresolved.",
                    })
            previous = current

    return {
        "place_count": len(places),
        "resolved_place_count": len(resolved),
        "route_count": len(routes),
        "error_count": len(errors),
        "routes": routes,
        "errors": errors,
        "cache_dir": str(CACHE_DIR),
    }


def _request_json(url, headers=None):
    cache_path = _cache_path(url)
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    live_onemap = os.getenv("ONEMAP_LIVE_CALLS", "true").lower() == "true"
    if not live_onemap:
        raise RuntimeError("OneMap live calls are disabled and this response is not cached yet.")

    request = Request(url, headers=headers or {})
    try:
        time.sleep(0.35)
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, indent=2))
            return payload
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OneMap HTTP {exc.code}: {body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"OneMap request failed: {exc.reason}") from exc


def _normalize_route(payload, mode):
    if "plan" in payload:
        itineraries = payload.get("plan", {}).get("itineraries", [])
        first = itineraries[0] if itineraries else {}
        legs = first.get("legs", [])
        distance = sum(float(leg.get("distance") or 0) for leg in legs)
        duration = float(first.get("duration") or 0)
        geometry = []
        for leg in legs:
            points = leg.get("legGeometry", {}).get("points")
            if points:
                decoded = _decode_polyline(points)
                geometry.extend(decoded if not geometry else decoded[1:])
        return {
            "distance_m": int(distance) if distance else None,
            "duration_min": round(duration / 60) if duration else None,
            "geometry": geometry,
            "raw": payload,
            "note": "Bus wait time excluded by POC assumption." if mode == "bus" else None,
        }

    summary = payload.get("route_summary") or payload.get("routeSummary") or {}
    distance = (
        summary.get("total_distance")
        or summary.get("totalDistance")
        or payload.get("total_distance")
        or payload.get("distance")
    )
    duration = (
        summary.get("total_time")
        or summary.get("totalTime")
        or payload.get("total_time")
        or payload.get("duration")
    )

    distance_m = int(float(distance)) if distance is not None else None
    duration_min = round(float(duration) / 60) if duration is not None else None

    return {
        "distance_m": distance_m,
        "duration_min": duration_min,
        "geometry": _decode_polyline(payload.get("route_geometry")) if payload.get("route_geometry") else [],
        "raw": payload,
        "note": "Bus wait time excluded by POC assumption." if mode == "bus" else None,
    }


def _number(value):
    if value in (None, ""):
        return None
    return float(value)


def _cache_path(url):
    safe = "".join(char if char.isalnum() else "_" for char in url)
    return CACHE_DIR / f"{safe[:180]}.json"


def _persona_route_mode(persona):
    persona_type = persona.get("type")
    if persona_type in (
        "school_run_parent_car",
        "weekend_family_shopper",
        "ev_fuel_regular",
        "transient_traveller",
        "cabbie_grab_driver",
    ):
        return "drive"
    if persona_type in ("morning_rusher",):
        return "bus"
    return "walk"


def _inside_locality(place):
    lat = place.get("lat")
    lng = place.get("lng")
    if lat is None or lng is None:
        return False
    return (
        LOCALITY_BOUNDS["south"] <= lat <= LOCALITY_BOUNDS["north"]
        and LOCALITY_BOUNDS["west"] <= lng <= LOCALITY_BOUNDS["east"]
    )


def _decode_polyline(encoded):
    index = 0
    lat = 0
    lng = 0
    coordinates = []

    while index < len(encoded):
        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1

        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1

        coordinates.append([lat / 100000.0, lng / 100000.0])

    return coordinates
