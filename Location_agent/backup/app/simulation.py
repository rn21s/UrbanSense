from app.crew_service import analyze_with_crewai
from app.data import PERSONAS, PLACES, ROUTES


def run_product_simulation(product):
    place_by_id = {place["id"]: place for place in PLACES}
    route_by_pair = {
        (route["origin"], route["destination"]): route
        for route in ROUTES
    }

    outcomes = [
        _persona_outcome(persona, product, place_by_id, route_by_pair)
        for persona in PERSONAS
    ]
    buyers = [outcome for outcome in outcomes if outcome["will_buy"]]
    maybe = [outcome for outcome in outcomes if outcome["purchase_probability"] >= 45 and not outcome["will_buy"]]

    recommendation = _recommendation(product, outcomes)
    scenario_facts = {
        "shell_store": place_by_id["shell_select"],
        "competitor": place_by_id["pharmacy"],
        "route_count": len(ROUTES),
        "persona_count": len(PERSONAS),
    }
    crew_report = analyze_with_crewai(product, outcomes, scenario_facts)

    return {
        "product": product,
        "timeline": _timeline(),
        "outcomes": outcomes,
        "summary": {
            "recommendation": recommendation,
            "buyer_count": len(buyers),
            "maybe_count": len(maybe),
            "persona_count": len(outcomes),
            "best_windows": _best_windows(outcomes),
            "top_reasons": _top_reasons(outcomes),
            "crew_report": crew_report,
            "engine": "CrewAI" if crew_report else "deterministic_poc_fallback",
        },
    }


def _persona_outcome(persona, product, place_by_id, route_by_pair):
    category = product["category"].lower()
    tags = persona["need_tags"]
    score = 18
    reasons = []

    if category in tags:
        score += 34
        reasons.append(f"{persona['type']} has a direct need for {category}.")
    elif category in ("medicine", "health") and "healthcare" in tags:
        score += 26
        reasons.append("Healthcare context raises trust and relevance for OTC medicine.")
    elif category in ("snacks", "food", "grocery") and any(tag in tags for tag in ["snacks", "family"]):
        score += 24
        reasons.append("The product fits an existing convenience shopping habit.")

    route_facts = _route_facts(persona, route_by_pair)
    if route_facts["passes_shell"]:
        score += 24
        reasons.append(
            f"Shell Select is on a regular route with only {route_facts['shell_detour_m']}m detour."
        )
    elif route_facts["shell_detour_m"] <= 150:
        score += 14
        reasons.append(f"Shell Select is close enough as a {route_facts['shell_detour_m']}m detour.")
    else:
        score -= 12
        reasons.append(f"The nearest routine route needs a {route_facts['shell_detour_m']}m detour.")

    if product["price_sgd"] <= 5:
        score += 8
        reasons.append("The price is low enough for an unplanned convenience purchase.")
    elif persona["price_sensitivity"] == "high":
        score -= 16
        reasons.append("High price sensitivity makes pharmacy comparison more likely.")

    if "late_shift" in tags or any(stop["time"] >= "21:00" for stop in persona["schedule"]):
        score += 10
        reasons.append("24-hour availability matters for this persona.")

    score = max(5, min(95, score))
    will_buy = score >= 58
    quote = _quote(persona, product, route_facts, will_buy)

    return {
        "persona_id": persona["id"],
        "name": persona["name"],
        "type": persona["type"],
        "purchase_probability": score,
        "will_buy": will_buy,
        "route_fact": route_facts,
        "reasons": reasons,
        "quote": quote,
        "schedule": persona["schedule"],
    }


def _route_facts(persona, route_by_pair):
    candidates = []
    home = persona.get("home")
    work = persona.get("work")
    if home and work:
        candidates.append(route_by_pair.get((home, work)))
        candidates.append(route_by_pair.get((work, home)))
    valid = [candidate for candidate in candidates if candidate]
    if valid:
        return sorted(valid, key=lambda item: item["shell_detour_m"])[0]

    for stop in persona["schedule"]:
        if stop["place"] == "shell_select":
            candidates.append({
                "origin": stop["place"],
                "destination": "shell_select",
                "mode": persona["transport"],
                "distance_m": 0,
                "duration_min": 0,
                "passes_shell": True,
                "shell_detour_m": 0,
            })

    valid = [candidate for candidate in candidates if candidate]
    if not valid:
        return {
            "mode": persona["transport"],
            "distance_m": None,
            "duration_min": None,
            "passes_shell": False,
            "shell_detour_m": 999,
        }

    return sorted(valid, key=lambda item: item["shell_detour_m"])[0]


def _timeline():
    events = []
    for persona in PERSONAS:
        for stop in persona["schedule"]:
            event = dict(stop)
            event["persona"] = persona["name"]
            event["persona_type"] = persona["type"]
            events.append(event)
    return sorted(events, key=lambda item: item["time"])


def _recommendation(product, outcomes):
    avg = round(sum(item["purchase_probability"] for item in outcomes) / len(outcomes))
    if avg >= 65:
        return f"Stock {product['name']} as a strong convenience product; start with visible shelf placement near checkout."
    if avg >= 48:
        return f"Run a limited test of {product['name']} for two weeks and track evening and after-shift purchases."
    return f"Do not prioritize {product['name']} yet; current locality demand is too narrow."


def _best_windows(outcomes):
    shell_stops = []
    for outcome in outcomes:
        if outcome["purchase_probability"] < 45:
            continue
        for stop in outcome["schedule"]:
            if stop["place"] == "shell_select":
                shell_stops.append(stop["time"])
    return sorted(shell_stops) or ["18:00-20:00"]


def _top_reasons(outcomes):
    reasons = []
    for outcome in outcomes:
        reasons.extend(outcome["reasons"][:2])
    return reasons[:5]


def _quote(persona, product, route, will_buy):
    if will_buy and route["passes_shell"]:
        return (
            f"{persona['name']}: I would buy {product['name']} from Shell Select because it is on "
            f"my regular {route['mode']} route and the detour is only {route['shell_detour_m']}m."
        )
    if will_buy:
        return (
            f"{persona['name']}: I would consider {product['name']} when I need it urgently, "
            "especially because the store is open late."
        )
    if not route["passes_shell"]:
        return (
            f"{persona['name']}: I may skip {product['name']} because Shell Select needs a "
            f"{route['shell_detour_m']}m detour from my regular {route['mode']} route."
        )
    return (
        f"{persona['name']}: I may skip {product['name']} here because it is not a strong need "
        "for my usual Shell Select visit."
    )
