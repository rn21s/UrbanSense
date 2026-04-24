from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
import hashlib
import json
import os
import time


BASE_URL = "https://maps.grab.com"
MCP_URL = "https://maps.grab.com/api/v1/mcp"
CACHE_DIR = Path(".cache/grab_maps")
DEFAULT_GRAB_MAPS_API_KEY = "bm_1776994844_2qikI3c3qYAZ6L11cUIKpOAGk5wbb180"
DEFAULT_GRAB_MAPS_MCP_TOKEN = "mcp_1776994819_c1cTtQh9rYFLEtLuFlnS4rY5"
DEFAULT_CENTER = {
    "latitude": 1.33118,
    "longitude": 103.87776,
}


def search_places(keyword, limit=8, country="SGP", location=None):
    keyword = (keyword or "").strip()
    if len(keyword) < 2:
        return {"places": [], "is_confident": False}

    params = {
        "keyword": keyword,
        "country": country,
        "limit": max(1, min(12, int(limit or 8))),
    }
    search_location = location or DEFAULT_CENTER
    params["location"] = f"{search_location['latitude']},{search_location['longitude']}"

    cache_key = _cache_key(keyword, country, search_location, params["limit"])
    try:
        payload = _request_json(f"{BASE_URL}/api/v1/maps/poi/v1/search?{urlencode(params)}")
    except RuntimeError:
        try:
            payload = _mcp_search(keyword, country, search_location, params["limit"])
        except RuntimeError as exc:
            cached = _read_cache(cache_key)
            if cached:
                cached["from_cache"] = True
                cached["warning"] = str(exc)
                return cached
            return {
                "places": [],
                "is_confident": False,
                "warning": str(exc),
            }
    places = payload.get("places", [])[:params["limit"]]
    result = {
        "places": [_normalize_place(place) for place in places],
        "is_confident": bool(payload.get("is_confident")),
        "uuid": payload.get("uuid"),
    }
    _write_cache(cache_key, result)
    return result


def nearby_places(latitude, longitude, radius_km=1.0, limit=50):
    radius_km = max(0.2, min(3.0, float(radius_km or 1.0)))
    limit = max(10, min(80, int(limit or 50)))
    params = {
        "location": f"{latitude},{longitude}",
        "radius": radius_km,
        "limit": limit,
        "rankBy": "distance",
    }
    cache_key = _cache_key("nearby", "SGP", {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}, limit)
    try:
        payload = _request_json(f"{BASE_URL}/api/v1/maps/place/v2/nearby?{urlencode(params)}")
    except RuntimeError as exc:
        cached = _read_cache(cache_key)
        if cached:
            cached["from_cache"] = True
            cached["warning"] = str(exc)
            return cached
        return {"places": [], "warning": str(exc)}

    result = {
        "places": [_normalize_place(place) for place in payload.get("places", [])[:limit]],
        "uuid": payload.get("uuid"),
        "radius_km": radius_km,
    }
    _write_cache(cache_key, result)
    return result


def locality_insights(latitude, longitude, product=None, radius_km=1.0):
    nearby = nearby_places(latitude, longitude, radius_km=radius_km, limit=60)
    places = nearby.get("places", [])
    product_text = f"{(product or {}).get('name', '')} {(product or {}).get('category', '')} {(product or {}).get('notes', '')}".lower()
    target = _target_business(product_text)
    competitors = [place for place in places if _is_competitor(place, target)]
    anchors = {
        "education": [place for place in places if _has_any(place, ["school", "college", "university", "polytechnic", "preschool", "tuition"])],
        "food_and_beverage": [place for place in places if _has_any(place, ["food and beverage", "restaurant", "fast food", "cafe", "coffee"])],
        "retail": [place for place in places if _has_any(place, ["shopping", "general merchandise", "mall", "retail"])],
        "transport": [place for place in places if _has_any(place, ["travel", "station", "mrt", "bus"])],
        "health": [place for place in places if _has_any(place, ["healthcare", "pharmacy", "clinic", "beauty"])],
        "office_services": [place for place in places if _has_any(place, ["financial", "office", "service"])],
        "residential": [place for place in places if _has_any(place, ["residential", "apartment", "hdb", "condominium", "estate"])],
    }
    crowding = _crowding_level(len(competitors), target)
    concept = _concept_profile(target, product_text)
    active_revenue = _active_revenue_signal(target, len(competitors), anchors)
    persona_fit = _persona_fit_signal(concept, anchors)
    return {
        "radius_km": radius_km,
        "poi_count": len(places),
        "product_concept": concept,
        "target_business": target,
        "competitor_count": len(competitors),
        "competitor_label": _competitor_label(target),
        "cannibalisation_risk": crowding,
        "competitor_examples": [_place_brief(place) for place in competitors[:10]],
        "anchor_counts": {key: len(value) for key, value in anchors.items()},
        "anchor_examples": {key: [_place_brief(place) for place in value[:6]] for key, value in anchors.items() if value},
        "active_revenue_potential": active_revenue,
        "persona_fit": persona_fit,
        "map_pois": _map_pois(competitors, anchors),
        "crowding": crowding,
        "places_source": "Grab Maps nearby places",
        "warning": nearby.get("warning"),
    }


def _request_json(url):
    api_key = os.getenv("GRAB_MAPS_API_KEY") or DEFAULT_GRAB_MAPS_API_KEY
    last_error = None
    for attempt in range(4):
        request = Request(url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urlopen(request, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"Grab Maps HTTP {exc.code}: {body[:240]}")
        except URLError as exc:
            last_error = RuntimeError(f"Grab Maps request failed: {exc.reason}")
        time.sleep(0.2 * (attempt + 1))
    raise last_error


def _mcp_search(keyword, country, location, limit):
    last_error = None
    for attempt in range(6):
        try:
            session_id = _mcp_initialize()
            _mcp_post({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }, session_id=session_id, expect_response=False)
            response = _mcp_post({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search",
                    "arguments": {
                        "keyword": keyword,
                        "country": country,
                        "location": location,
                        "limit": limit,
                    },
                },
            }, session_id=session_id)
            result = response.get("result") or {}
            structured = result.get("structuredContent")
            if structured:
                return structured

            content = result.get("content") or []
            if content and content[0].get("text"):
                return json.loads(content[0]["text"])
        except (HTTPError, URLError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"Grab Maps MCP search failed: {last_error}")


def _mcp_initialize():
    response = _mcp_post({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "demandlab-local", "version": "0.1"},
        },
    }, include_headers=True)
    session_id = response["headers"].get("mcp-session-id")
    if not session_id:
        raise RuntimeError("Grab Maps MCP did not return a session id.")
    return session_id


def _mcp_post(payload, session_id=None, include_headers=False, expect_response=True):
    token = os.getenv("GRAB_MAPS_MCP_TOKEN") or DEFAULT_GRAB_MAPS_MCP_TOKEN
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "UrbanSense AI/0.1",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    request = Request(MCP_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=12) as response:
        body = response.read().decode("utf-8")
        if include_headers:
            return {"headers": {key.lower(): value for key, value in response.headers.items()}, "body": body}
        if not expect_response or not body:
            return {}
        return _parse_sse_json(body)


def _parse_sse_json(body):
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    return json.loads(body)


def _cache_key(keyword, country, location, limit):
    raw = json.dumps({
        "keyword": keyword.lower().strip(),
        "country": country,
        "location": location,
        "limit": limit,
    }, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(cache_key):
    return CACHE_DIR / f"{cache_key}.json"


def _read_cache(cache_key):
    path = _cache_path(cache_key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(cache_key, payload):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(cache_key).write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _normalize_place(place):
    location = place.get("location") or {}
    categories = place.get("categories") or []
    category_names = [
        item.get("category_name", "")
        for item in categories
        if isinstance(item, dict)
    ]
    category = place.get("category") or " ".join(category_names) or place.get("business_type") or ""
    return {
        "id": place.get("poi_id"),
        "name": place.get("name") or "Unnamed place",
        "address": place.get("formatted_address") or place.get("street") or "",
        "category": category,
        "business_type": place.get("business_type") or "",
        "lat": location.get("latitude"),
        "lng": location.get("longitude"),
        "postcode": place.get("postcode") or "",
        "distance_km": place.get("distance"),
    }


def _target_business(product_text):
    if any(word in product_text for word in ("coffee shop", "cafe", "café", "fancy coffee", "specialty coffee", "espresso", "coffee")):
        return "cafe"
    if any(word in product_text for word in ("restaurant", "meal", "lunch", "dinner", "food")):
        return "food"
    if any(word in product_text for word in ("pharmacy", "medicine", "health", "clinic")):
        return "health"
    if any(word in product_text for word in ("gym", "fitness", "protein")):
        return "fitness"
    if any(word in product_text for word in ("shop", "retail", "store")):
        return "retail"
    return "convenience"


def _is_competitor(place, target):
    text = _place_text(place)
    rules = {
        "cafe": ["cafe", "coffee", "espresso", "starbucks", "kopi", "toast", "bakery", "tea"],
        "food": ["food", "restaurant", "fast food", "burger", "sandwich", "cafe", "hawker", "bakery"],
        "health": ["healthcare", "pharmacy", "clinic", "medical", "guardian", "watsons"],
        "fitness": ["fitness", "gym", "sport", "protein", "health"],
        "retail": ["shopping", "general merchandise", "retail", "mall", "store"],
        "convenience": ["convenience", "general merchandise", "supermarket", "grocery", "7-eleven", "cheers"],
    }
    return any(token in text for token in rules.get(target, []))


def _has_any(place, tokens):
    text = _place_text(place)
    return any(token in text for token in tokens)


def _place_text(place):
    return " ".join([
        str(place.get("name", "")),
        str(place.get("category", "")),
        str(place.get("business_type", "")),
        str(place.get("address", "")),
    ]).lower()


def _crowding_level(count, target):
    high_threshold = 8 if target in ("cafe", "food") else 6
    medium_threshold = 4 if target in ("cafe", "food") else 3
    if count >= high_threshold:
        return "high"
    if count >= medium_threshold:
        return "medium"
    return "low"


def _place_brief(place):
    return {
        "id": place.get("id"),
        "name": place.get("name"),
        "address": place.get("address"),
        "category": place.get("category"),
        "business_type": place.get("business_type"),
        "distance_km": place.get("distance_km"),
        "lat": place.get("lat"),
        "lng": place.get("lng"),
    }


def _competitor_label(target):
    labels = {
        "cafe": "coffee/cafe competitors",
        "food": "food competitors",
        "health": "health competitors",
        "fitness": "fitness competitors",
        "retail": "retail competitors",
        "convenience": "convenience competitors",
    }
    return labels.get(target, "direct competitors")


def _concept_profile(target, product_text):
    profiles = {
        "cafe": {
            "label": "Coffee / cafe",
            "primary_personas": ["office workers", "students", "commuters", "delivery buyers"],
            "anchor_keys": ["office_services", "education", "transport", "residential"],
        },
        "food": {
            "label": "Food service",
            "primary_personas": ["office workers", "residents", "commuters", "delivery buyers"],
            "anchor_keys": ["office_services", "residential", "transport", "food_and_beverage"],
        },
        "health": {
            "label": "Health / pharmacy",
            "primary_personas": ["residents", "parents", "elderly visitors", "clinic visitors"],
            "anchor_keys": ["health", "residential", "education"],
        },
        "fitness": {
            "label": "Fitness / wellness",
            "primary_personas": ["office workers", "students", "active residents"],
            "anchor_keys": ["office_services", "education", "residential"],
        },
        "retail": {
            "label": "Retail shop",
            "primary_personas": ["residents", "commuters", "mall visitors"],
            "anchor_keys": ["retail", "residential", "transport"],
        },
        "convenience": {
            "label": "Convenience retail",
            "primary_personas": ["residents", "commuters", "shift workers", "parents"],
            "anchor_keys": ["residential", "transport", "education", "office_services"],
        },
    }
    profile = profiles.get(target, profiles["convenience"]).copy()
    profile["keyword_match"] = product_text[:120]
    return profile


def _active_revenue_signal(target, competitor_count, anchors):
    weighted_demand = (
        len(anchors.get("office_services", [])) * 2.0
        + len(anchors.get("education", [])) * 1.8
        + len(anchors.get("transport", [])) * 1.5
        + len(anchors.get("residential", [])) * 1.4
        + len(anchors.get("food_and_beverage", [])) * (1.2 if target != "food" else 0.7)
        + len(anchors.get("retail", []))
    )
    peer_activity = min(competitor_count, 12) * (1.8 if target in ("cafe", "food") else 1.2)
    score = round(min(100, 22 + weighted_demand * 3.2 + peer_activity * 2.4))
    if score >= 72:
        level = "high"
    elif score >= 48:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "score": score,
        "label": level.title(),
        "explanation": "Proxy based on nearby peer activity, office/school/transit anchors, and residential density signals.",
    }


def _persona_fit_signal(concept, anchors):
    fit = []
    anchor_counts = {key: len(anchors.get(key, [])) for key in concept.get("anchor_keys", [])}
    for persona in concept.get("primary_personas", []):
        if persona == "office workers":
            count = anchor_counts.get("office_services", 0)
        elif persona == "students":
            count = anchor_counts.get("education", 0)
        elif persona == "commuters":
            count = anchor_counts.get("transport", 0)
        elif persona in ("residents", "parents", "active residents", "shift workers", "delivery buyers"):
            count = anchor_counts.get("residential", 0) + anchor_counts.get("transport", 0)
        else:
            count = max(anchor_counts.values() or [0])
        strength = "strong" if count >= 4 else "moderate" if count >= 1 else "weak"
        fit.append({"persona": persona, "strength": strength, "anchor_count": count})
    return fit


def _map_pois(competitors, anchors):
    items = []
    for place in competitors[:14]:
        brief = _place_brief(place)
        if brief.get("lat") and brief.get("lng"):
            brief["kind"] = "competitor"
            items.append(brief)

    anchor_labels = {
        "education": "school",
        "office_services": "office",
        "transport": "transport",
        "residential": "residential",
    }
    for key, label in anchor_labels.items():
        for place in anchors.get(key, [])[:6]:
            brief = _place_brief(place)
            if brief.get("lat") and brief.get("lng"):
                brief["kind"] = label
                items.append(brief)
    return items[:28]
