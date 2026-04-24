import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def summarize_strategy_with_openai(product, outcomes, locality, fallback_recommendation, fallback_insights):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    facts = _strategy_facts(product, outcomes, locality, fallback_recommendation, fallback_insights)
    prompt = (
        "You are a Grab-style location intelligence strategist. "
        "Write a concise business recommendation using only the JSON facts provided. "
        "Discuss direct competitors, locality demand anchors such as offices, schools, transit and residential density, "
        "persona fit, cannibalisation risk, and any missing data limitations. "
        "Do not invent revenue, profit, order volume, addresses, or POI counts. "
        "If Active revenue potential requires a database connection, say that metric is unavailable rather than estimating it. "
        "Return only valid JSON with this shape: "
        "{\"recommendation\":\"one paragraph, max 80 words\",\"insights\":[\"3-5 concise factual bullets\"]}.\n\n"
        f"Facts:\n{json.dumps(facts, ensure_ascii=False, sort_keys=True)}"
    )
    payload = {
        "model": os.getenv("OPENAI_STRATEGY_MODEL", "gpt-5.4-mini"),
        "input": prompt,
        "max_output_tokens": 450,
    }

    request = Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=18) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    try:
        parsed = json.loads(_response_text(body))
    except (TypeError, json.JSONDecodeError):
        return None

    recommendation = str(parsed.get("recommendation") or "").strip()
    insights = [
        str(item).strip()
        for item in parsed.get("insights", [])
        if str(item).strip()
    ][:5]
    if not recommendation or not insights:
        return None
    return {
        "recommendation": recommendation,
        "insights": insights,
        "source": f"OpenAI Responses API ({payload['model']})",
    }


def _strategy_facts(product, outcomes, locality, fallback_recommendation, fallback_insights):
    locality = locality or {}
    anchors = locality.get("anchor_counts") or {}
    active_revenue = locality.get("active_revenue_potential") or {}
    persona_fit = locality.get("persona_fit") or []
    competitors = locality.get("competitor_examples") or []
    return {
        "product": {
            "name": product.get("name"),
            "category": product.get("category"),
            "price_sgd": product.get("price_sgd"),
            "price_tier": product.get("price_tier"),
        },
        "locality": {
            "radius_km": locality.get("radius_km"),
            "poi_count": locality.get("poi_count"),
            "concept": (locality.get("product_concept") or {}).get("label"),
            "target_business": locality.get("target_business"),
            "direct_competitor_count": locality.get("competitor_count"),
            "competitor_label": locality.get("competitor_label"),
            "cannibalisation_risk": locality.get("cannibalisation_risk") or locality.get("crowding"),
            "anchor_counts": anchors,
            "active_revenue_metric_status": "unavailable; requires connection to Grab Purchase Metrics DB",
            "active_revenue_proxy": active_revenue,
            "persona_fit": persona_fit,
            "competitor_examples": competitors[:5],
        },
        "simulation": {
            "persona_count": len(outcomes),
            "buyer_count": len([item for item in outcomes if item.get("will_buy")]),
            "average_purchase_probability": _average_probability(outcomes),
            "top_personas": _top_personas(outcomes),
        },
        "fallback_recommendation": fallback_recommendation,
        "fallback_insights": fallback_insights,
    }


def _average_probability(outcomes):
    if not outcomes:
        return 0
    return round(sum(item.get("purchase_probability", 0) for item in outcomes) / len(outcomes))


def _top_personas(outcomes):
    ranked = sorted(outcomes, key=lambda item: item.get("purchase_probability", 0), reverse=True)
    return [
        {
            "name": item.get("agent_name") or item.get("name"),
            "persona": item.get("name"),
            "purchase_probability": item.get("purchase_probability"),
            "will_buy": item.get("will_buy"),
            "reasons": item.get("reasons", [])[:3],
        }
        for item in ranked[:4]
    ]


def _response_text(body):
    if body.get("output_text"):
        return body["output_text"]
    chunks = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "".join(chunks).strip()
