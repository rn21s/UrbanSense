from app.crew_service import analyze_with_crewai
from app.data import PERSONAS, PLACES, ROUTES
from app.strategy_service import summarize_strategy_with_openai


def run_product_simulation(product, agent_count=None, selected_persona_ids=None, locality=None):
    if selected_persona_ids:
        selected = set(selected_persona_ids)
        personas = [persona for persona in PERSONAS if persona["id"] in selected]
    else:
        personas = _best_fit_personas(product, agent_count=agent_count)
    if not personas:
        personas = _best_fit_personas(product, agent_count=agent_count)
    place_by_id = {place["id"]: place for place in PLACES}
    route_by_pair = {
        (route["origin"], route["destination"]): route
        for route in ROUTES
    }

    outcomes = [
        _persona_outcome(persona, product, place_by_id, route_by_pair, locality=locality)
        for persona in personas
    ]
    buyers = [outcome for outcome in outcomes if outcome["will_buy"]]
    maybe = [outcome for outcome in outcomes if outcome["purchase_probability"] >= 45 and not outcome["will_buy"]]

    recommendation = _recommendation(product, outcomes, locality=locality)
    recommendation_insights = _recommendation_insights(product, outcomes, locality)
    strategy_summary = summarize_strategy_with_openai(
        product,
        outcomes,
        locality,
        recommendation,
        recommendation_insights,
    )
    if strategy_summary:
        recommendation = strategy_summary["recommendation"]
        recommendation_insights = strategy_summary["insights"]
    scenario_facts = {
        "shell_store": place_by_id["shell_select"],
        "competitor": place_by_id["pharmacy"],
        "route_count": len(ROUTES),
        "persona_count": len(personas),
    }
    crew_report = analyze_with_crewai(product, outcomes, scenario_facts)

    return {
        "product": product,
        "timeline": _timeline(personas),
        "outcomes": outcomes,
        "summary": {
            "recommendation": recommendation,
            "buyer_count": len(buyers),
            "maybe_count": len(maybe),
            "persona_count": len(outcomes),
            "best_windows": _best_windows(outcomes),
            "top_reasons": _top_reasons(outcomes),
            "recommendation_insights": recommendation_insights,
            "recommendation_source": strategy_summary["source"] if strategy_summary else "deterministic_strategy_fallback",
            "crew_report": crew_report,
            "engine": "CrewAI" if crew_report else "deterministic_poc_fallback",
            "locality": locality,
        },
    }


def _best_fit_personas(product, agent_count=None):
    count = max(3, min(6, int(agent_count or 5)))
    ranked = sorted(
        (
            (_persona_fit_score(persona, product), persona)
            for persona in PERSONAS
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = [persona for score, persona in ranked if score > 0][:count]
    return selected or [persona for _, persona in ranked[:count]]


def _persona_fit_score(persona, product):
    category = (product.get("category") or "").lower()
    name = (product.get("name") or "").lower()
    notes = (product.get("notes") or "").lower()
    text = f"{category} {name} {notes}"
    tags = set(persona.get("need_tags", []))
    score = 0

    category_aliases = {
        "drinks": ["drinks", "drink", "water", "hydration", "isotonic", "energy_drinks", "coffee"],
        "beverage": ["drinks", "drink", "water", "hydration", "isotonic", "energy_drinks", "coffee"],
        "snacks": ["snacks", "ice_cream", "novelty", "family", "child"],
        "food": ["food", "meal", "quick_meal", "lunch", "dessert"],
        "grocery": ["household", "daily_necessities", "family", "convenience"],
        "medicine": ["medicine", "health", "healthcare", "daily_necessities"],
        "health": ["health", "hydration", "protein", "low_sugar", "medicine"],
        "household": ["household", "daily_necessities", "family"],
    }
    for tag in category_aliases.get(category, [category]):
        if tag in tags:
            score += 18

    keyword_tags = {
        "coke": ["drinks", "snacks", "speed"],
        "cola": ["drinks", "snacks", "speed"],
        "coffee": ["coffee", "speed", "dwell_time"],
        "energy": ["energy_drinks", "late_shift", "speed"],
        "100plus": ["isotonic", "hydration", "fitness", "drinks"],
        "isotonic": ["isotonic", "hydration", "fitness"],
        "water": ["water", "hydration", "health"],
        "protein": ["protein", "health", "fitness"],
        "bar": ["protein", "snacks", "speed"],
        "sandwich": ["food", "meal", "quick_meal", "lunch"],
        "meal": ["meal", "quick_meal", "lunch"],
        "ice cream": ["ice_cream", "family", "novelty"],
        "paracetamol": ["medicine", "health", "healthcare", "family"],
        "panadol": ["medicine", "health", "healthcare", "family"],
        "wipes": ["child", "family", "household"],
        "diaper": ["child", "family", "household"],
        "toiletries": ["toiletries", "clear_packaging"],
    }
    for keyword, needed_tags in keyword_tags.items():
        if keyword in text:
            score += sum(14 for tag in needed_tags if tag in tags)

    if product.get("price_sgd", 0) <= 5 and any(tag in tags for tag in ("speed", "value", "snacks", "drinks")):
        score += 8
    if any(word in text for word in ("premium", "craft", "imported")) and "premium" in tags:
        score += 10
    if any(word in text for word in ("family", "kids", "child")) and any(tag in tags for tag in ("family", "child")):
        score += 12
    if any(word in text for word in ("late", "night", "energy")) and "late_shift" in tags:
        score += 10
    if any(word in text for word in ("healthy", "low sugar", "zero", "protein")) and any(tag in tags for tag in ("health", "low_sugar", "protein")):
        score += 12

    shell_visit = _shell_visit_context(persona)
    if shell_visit:
        score += 4
    return score


def _persona_outcome(persona, product, place_by_id, route_by_pair, locality=None):
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
    shell_visit = _shell_visit_context(persona)
    if route_facts["passes_shell"]:
        score += 24
        reasons.append(
            f"The selected location is on a regular route with only {route_facts['shell_detour_m']}m detour."
        )
    elif route_facts["shell_detour_m"] is not None and route_facts["shell_detour_m"] <= 150:
        score += 14
        reasons.append(f"The selected location is close enough as a {route_facts['shell_detour_m']}m detour.")
    elif route_facts["shell_detour_m"] is not None:
        score -= 12
        reasons.append(f"The nearest routine route needs a {route_facts['shell_detour_m']}m detour.")
    else:
        reasons.append("Route convenience will be judged from the live OneMap path in the map layer.")

    if product["price_sgd"] <= 5:
        score += 8
        reasons.append("The price is low enough for an unplanned convenience purchase.")
    elif persona["price_sensitivity"] == "high":
        score -= 16
        reasons.append("High price sensitivity makes pharmacy comparison more likely.")

    if "late_shift" in tags or any(stop["time"] >= "21:00" for stop in persona["schedule"]):
        score += 10
        reasons.append("24-hour availability matters for this persona.")

    if shell_visit:
        score += 8
        reasons.append(f"This persona reaches the selected location around {shell_visit['time']} during the day.")

    score += _locality_score_adjustment(persona, product, locality, reasons)

    score = max(5, min(95, score))
    will_buy = score >= 58
    quote = _quote(persona, product, route_facts, shell_visit, will_buy)

    return {
        "persona_id": persona["id"],
        "name": persona["name"],
        "agent_name": persona.get("agent_name"),
        "type": persona["type"],
        "age_range": persona.get("age_range"),
        "peak_hours": persona.get("peak_hours"),
        "frequency": persona.get("frequency"),
        "current_behaviour": persona.get("current_behaviour"),
        "purchase_trigger": persona.get("purchase_trigger"),
        "singapore_context": persona.get("singapore_context"),
        "purchase_probability": score,
        "will_buy": will_buy,
        "route_fact": route_facts,
        "shell_visit": shell_visit,
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

    return {
        "mode": persona["transport"],
        "distance_m": None,
        "duration_min": None,
        "passes_shell": False,
        "shell_detour_m": None,
    }


def _shell_visit_context(persona):
    for index, stop in enumerate(persona["schedule"]):
        if stop["place"] != "shell_select":
            continue
        previous_stop = persona["schedule"][index - 1] if index > 0 else None
        next_stop = persona["schedule"][index + 1] if index + 1 < len(persona["schedule"]) else None
        return {
            "time": stop["time"],
            "activity": stop["activity"],
            "from": previous_stop["place"] if previous_stop else None,
            "to": next_stop["place"] if next_stop else None,
        }
    return None


def _timeline(personas):
    events = []
    for persona in personas:
        for stop in persona["schedule"]:
            event = dict(stop)
            event["persona"] = persona["name"]
            event["agent_name"] = persona.get("agent_name")
            event["persona_type"] = persona["type"]
            events.append(event)
    return sorted(events, key=lambda item: item["time"])


def _recommendation(product, outcomes, locality=None):
    avg = round(sum(item["purchase_probability"] for item in outcomes) / len(outcomes))
    if locality:
        crowding = locality.get("crowding")
        competitor_count = locality.get("competitor_count", 0)
        target = locality.get("target_business", "business")
        opportunity = _locality_opportunity_score(locality, avg)
        if crowding == "high":
            return (
                f"Be cautious launching {product['name']} here: Grab Maps shows {competitor_count} nearby "
                f"{target} competitors within {locality.get('radius_km', 1)} km, so differentiation must be very clear."
            )
        if opportunity >= 62 and crowding in ("low", "medium"):
            return (
                f"Prioritize a focused test of {product['name']} here. Locality signals are supportive, with relevant demand anchors "
                f"and {competitor_count} nearby {target} competitors, so validate offer, price, and operating hours before scaling."
            )
        if crowding == "medium":
            return (
                f"Run a focused test of {product['name']} here. Demand signals exist, but Grab Maps shows "
                f"{competitor_count} nearby {target} competitors, so positioning and visibility matter."
            )
        if crowding == "low" and avg >= 40:
            return (
                f"{product['name']} has a promising locality opening: relevant personas are present and Grab Maps shows "
                f"limited direct {target} competition nearby."
            )
    if avg >= 65:
        return f"Stock {product['name']} as a strong convenience product; start with visible shelf placement near checkout."
    if avg >= 48:
        return f"Run a limited test of {product['name']} for two weeks and track evening and after-shift purchases."
    return f"Do not prioritize {product['name']} yet; current locality demand is too narrow."


def _locality_opportunity_score(locality, avg_probability):
    anchors = locality.get("anchor_counts", {})
    risk = locality.get("cannibalisation_risk") or locality.get("crowding")
    score = avg_probability
    score += min(18, anchors.get("office_services", 0) * 1.4)
    score += min(10, anchors.get("transport", 0) * 1.2)
    score += min(8, anchors.get("education", 0) * 1.2)
    score += min(8, anchors.get("residential", 0) * 1.2)
    score += {"low": 8, "medium": 0, "high": -16}.get(risk, 0)
    strong_fit_count = sum(1 for item in locality.get("persona_fit", []) if item.get("strength") == "strong")
    score += min(8, strong_fit_count * 2)
    return round(score)


def _recommendation_insights(product, outcomes, locality=None):
    insights = []
    if locality:
        anchors = locality.get("anchor_counts", {})
        concept = locality.get("product_concept", {})
        competitor_count = locality.get("competitor_count", 0)
        competitor_label = locality.get("competitor_label", "direct competitors")
        risk = locality.get("cannibalisation_risk") or locality.get("crowding")
        target = locality.get("target_business")

        if anchors.get("office_services", 0) >= 3:
            insights.append(
                f"{anchors['office_services']} office/service anchors nearby can support weekday breakfast, lunch, and repeat workday demand."
            )
        if anchors.get("education", 0) >= 1:
            insights.append(
                f"{anchors['education']} school/college anchors nearby add student, parent, and staff demand occasions."
            )
        if anchors.get("transport", 0) >= 2:
            insights.append(
                f"{anchors['transport']} transit anchors nearby improve commuter visibility and short-stop purchase potential."
            )
        if anchors.get("residential", 0) >= 3:
            insights.append(
                f"Residential density looks supportive, with {anchors['residential']} residential signals around the catchment."
            )
        if target == "cafe" and anchors.get("office_services", 0) >= 3:
            insights.append(
                "For a coffee/cafe concept, the office cluster is especially useful because demand repeats across morning coffee and afternoon break routines."
            )

        if risk == "high":
            insights.append(
                f"Cannibalisation needs careful positioning: Grab Maps found {competitor_count} {competitor_label} nearby."
            )
        elif risk == "medium":
            insights.append(
                f"Competition is present but not saturated: {competitor_count} {competitor_label} nearby means differentiation still matters."
            )
        elif risk == "low":
            insights.append(
                f"Direct cannibalisation appears limited, with {competitor_count} {competitor_label} detected nearby."
            )

        strong_fit = [
            item.get("persona")
            for item in locality.get("persona_fit", [])
            if item.get("strength") == "strong"
        ]
        if strong_fit:
            insights.append(
                f"Persona fit is strongest for {', '.join(strong_fit[:3])}, based on the local anchor mix."
            )
        elif concept.get("primary_personas"):
            insights.append(
                f"The concept mainly depends on {', '.join(concept['primary_personas'][:3])}; monitor whether those groups are visible in the selected catchment."
            )

    buyers = [outcome for outcome in outcomes if outcome["will_buy"]]
    if buyers:
        top_buyer = max(buyers, key=lambda item: item["purchase_probability"])
        insights.append(
            f"Highest simulated pull comes from {top_buyer.get('agent_name') or top_buyer['name']} at {top_buyer['purchase_probability']}%, driven by route fit and need-state match."
        )
    avg = round(sum(item["purchase_probability"] for item in outcomes) / len(outcomes))
    insights.append(f"Average simulated purchase probability is {avg}% across {len(outcomes)} personas.")

    deduped = []
    for insight in insights:
        if insight not in deduped:
            deduped.append(insight)
    return deduped[:5]


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


def _locality_score_adjustment(persona, product, locality, reasons):
    if not locality:
        return 0
    adjustment = 0
    target = locality.get("target_business")
    anchors = locality.get("anchor_counts", {})
    competitor_count = locality.get("competitor_count", 0)
    crowding = locality.get("crowding")

    if target == "cafe":
        if persona["type"] in ("morning_rusher", "lunch_breaker", "cabbie_grab_driver", "ev_fuel_regular"):
            adjustment += 10
            reasons.append("Grab Maps locality has useful coffee footfall personas around commute, lunch, or driver dwell-time occasions.")
        if anchors.get("transport", 0) >= 2:
            adjustment += 6
            reasons.append(f"Grab Maps shows {anchors['transport']} nearby transport anchors, helping morning coffee demand.")
        if anchors.get("office_services", 0) >= 3:
            adjustment += 5
            reasons.append(f"Grab Maps shows {anchors['office_services']} office/service anchors that can support weekday cafe demand.")
    elif target == "food":
        if persona["type"] in ("lunch_breaker", "weekend_family_shopper", "late_night_lone_wolf"):
            adjustment += 8
        if anchors.get("food_and_beverage", 0) >= 4:
            adjustment += 4
            reasons.append("Nearby F&B density suggests food-seeking traffic, but also comparison shopping.")
    elif target == "health":
        if persona["type"] in ("elderly_neighbourhood_regular", "school_run_parent_car", "transient_traveller"):
            adjustment += 8
        if anchors.get("health", 0) >= 2:
            adjustment += 4
            reasons.append("Nearby health/beauty anchors suggest healthcare-oriented errands.")

    if crowding == "high":
        adjustment -= 16
        reasons.append(f"Grab Maps shows a crowded nearby competitor set ({competitor_count} direct matches).")
    elif crowding == "medium":
        adjustment -= 7
        reasons.append(f"Grab Maps shows moderate direct competition ({competitor_count} nearby matches).")
    elif crowding == "low":
        adjustment += 5
        reasons.append("Grab Maps shows limited direct nearby competition.")

    return adjustment


def _quote(persona, product, route, shell_visit, will_buy):
    label = _persona_label(persona)
    reason = _quote_reason(persona, product, route, shell_visit, will_buy)
    if will_buy and shell_visit and route["passes_shell"]:
        return (
            f"{label}: I would buy {product['name']} around {shell_visit['time']} because {reason}"
        )
    if will_buy and shell_visit:
        return (
            f"{label}: I would consider {product['name']} around {shell_visit['time']} because {reason}"
        )
    if will_buy:
        return (
            f"{label}: I would consider {product['name']} when the occasion fits because {reason}"
        )
    if route["shell_detour_m"] is not None and not route["passes_shell"]:
        return (
            f"{label}: I may skip {product['name']} because the selected location needs a "
            f"{route['shell_detour_m']}m detour from my regular {route['mode']} route, and {reason}"
        )
    return (
        f"{label}: I may skip {product['name']} here because {reason}"
    )


def _quote_reason(persona, product, route, shell_visit, will_buy):
    product_name = product.get("name", "this concept")
    persona_type = persona.get("type")
    trigger = (persona.get("purchase_trigger") or "").rstrip(".")
    behaviour = (persona.get("current_behaviour") or "").rstrip(".")
    if persona_type == "cabbie_grab_driver":
        return "driver demand depends on fast pickup, easy parking, and whether the offer fits between rides."
    if persona_type == "morning_rusher":
        return "morning demand is time-sensitive, so visibility and a fast queue matter more than browsing."
    if persona_type == "ev_fuel_regular":
        return "dwell time can help, but the offer has to suit a charging or refuelling stop."
    if persona_type == "fitness_regular":
        return f"{product_name} has to connect clearly to post-workout hydration, protein, or recovery needs."
    if persona_type == "lunch_breaker":
        return "weekday lunch traffic is promising, but the concept must compete with nearby F&B choices."
    if persona_type in ("school_run_parent_car", "school_run_parent_walking"):
        return "parent demand is strongest when the stop solves a family errand or child-related need."
    if persona_type == "elderly_neighbourhood_regular":
        return "off-peak neighbourhood demand depends on familiarity, accessibility, and everyday usefulness."
    if persona_type == "late_night_lone_wolf":
        return "late-night demand favours simple, available, low-effort purchases."
    if persona_type == "transient_traveller":
        return "traveller demand is opportunistic and depends on portability and immediate need."
    if will_buy and trigger:
        return trigger[0].lower() + trigger[1:] + "."
    if behaviour:
        return behaviour[0].lower() + behaviour[1:] + "."
    if shell_visit:
        return "the selected location already appears in my daily movement pattern."
    if route.get("shell_detour_m") is not None:
        return f"the detour is {route['shell_detour_m']}m and needs a clear reason to stop."
    return "the need-state is not strong enough for this persona."


def _persona_label(persona):
    agent_name = persona.get("agent_name")
    return f"{agent_name} ({persona['name']})" if agent_name else persona["name"]
