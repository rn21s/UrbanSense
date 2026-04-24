# UrbanSense AI Locality Simulator POC

A small proof of concept for testing whether a new product or store concept is likely to work in a local Singapore catchment area.

The POC keeps geography deterministic and structured, then uses persona-style reasoning to explain who would buy, why, and when. CrewAI is wired as an optional analysis layer, with a local fallback so the app can run without installing anything.

## What It Does

- Shows a sample Singapore locality with homes, school, hospital, offices, competitor retail, and a selected test location.
- Simulates a 24-hour day for several personas.
- Tests a proposed product, such as paracetamol, baby wipes, protein bars, or ready meals.
- Produces a route-grounded summary using walking/driving distance, detour, timing, and persona needs.
- Supports a future CrewAI implementation path for richer multi-agent reports.

## Market Intelligence Methodology

The simulator now combines persona simulation with a locality market-intelligence layer. The goal is to approximate how suitable a selected location is for a product or store concept before launch.

### 1. Product Concept Detection

The app reads the product name, category, and notes to infer the likely business concept.

Examples:

- `coffee shop`, `coffee`, `cafe`, `espresso` -> coffee / cafe concept
- `restaurant`, `meal`, `lunch`, `food` -> food service concept
- `medicine`, `health`, `pharmacy`, `clinic` -> health / pharmacy concept
- `gym`, `fitness`, `protein` -> fitness / wellness concept
- `shop`, `store`, `retail` -> retail concept

This concept is used to decide which competitors and locality demand anchors matter most.

### 2. Competitor Cannibalisation

For the selected location, the backend calls Grab Maps nearby-place data and classifies direct competitors based on the detected concept.

For a coffee / cafe concept, direct competitors include signals such as:

- cafes
- coffee shops
- espresso / specialty coffee places
- bakeries and toast shops
- tea shops
- nearby F&B concepts that compete for the same purchase occasion

The simulator returns:

- direct competitor count
- competitor examples
- cannibalisation risk: `Low`, `Medium`, or `High`
- competitor POIs for map markers

Cannibalisation risk is based on competitor count thresholds. Food and cafe concepts use slightly higher thresholds because dense F&B clusters can also indicate demand.

### 3. Active Revenue Potential

The app does not claim actual merchant profitability. Instead, it uses an `Active revenue potential` proxy.

This proxy estimates whether the locality has enough demand density and peer activity to support the concept. It is based on:

- nearby peer/competitor activity
- office and service anchors
- school / college anchors
- transit nodes
- residential density signals
- nearby F&B and retail clusters

The result is shown as:

- `Low`
- `Medium`
- `High`

If real Grab merchant order or revenue data is connected later, this block can be replaced or calibrated with actual internal activity data.

### 4. Persona Fit

The concept is matched to likely demand personas.

For example, a coffee / cafe concept looks for:

- office workers
- students
- commuters
- delivery buyers

The app checks whether the locality has matching anchors such as offices, schools, transit points, and residential density. Persona fit is labelled as `weak`, `moderate`, or `strong`.

### 5. Locality Demand Signals

After the simulation runs, the map area shows a locality signal block below the map. It summarizes:

- direct competitors
- cannibalisation risk
- active revenue potential
- schools / colleges
- offices / services
- transit nodes
- residential density
- POIs scanned

The map also receives additional markers for direct competitors and demand anchors such as schools, offices, transit, and residential signals.

### 6. Recommendation Logic

The final recommendation combines:

- persona purchase probability from `app/simulation.py`
- route convenience and detour friction
- selected location context
- competitor cannibalisation risk
- active revenue potential
- demand-anchor fit

The recommendation intentionally avoids inventing unavailable facts. When a signal is a proxy, the UI labels it as a proxy rather than profitability.

### 7. OpenAI Strategy Summary

If `OPENAI_API_KEY` is present, the backend sends the factual simulation summary to OpenAI through the Responses API and asks for a concise business-strategist recommendation. The prompt requires the model to use only provided facts, including:

- direct competitor count and cannibalisation risk
- office, school, transit, residential, F&B, and retail anchor counts
- persona fit and simulated purchase probabilities
- missing-data limitations such as the unavailable Grab Purchase Metrics DB

By default, the strategy model is `gpt-5.4-mini`. Override it with:

```env
OPENAI_STRATEGY_MODEL=gpt-5.4-mini
```

If `OPENAI_API_KEY` is missing or the request fails, the app falls back to the deterministic recommendation logic.

## Run The POC

This repo currently uses only Python standard library modules for the runnable POC.

```bash
python3 server.py
```

Then open:

```text
http://localhost:8000
```

## OneMap POC

Paste your OneMap token into `.env`:

```env
ONEMAP_ACCESS_TOKEN=your_token_here
```

Then run the app and test these URLs:

```text
http://localhost:8000/api/onemap/places
http://localhost:8000/api/onemap/routes
```

`/api/onemap/places` resolves the MacPherson locality anchors into OneMap coordinates.

`/api/onemap/routes` calculates walking, driving, and bus route facts between the first few places. For this POC, bus wait time is assumed to be 0 minutes.

## CrewAI Path

CrewAI currently requires Python `>=3.10 and <3.14`. The local machine used to create this POC has Python `3.9.6`, so the app ships with a deterministic fallback report.

To enable CrewAI later:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[crewai]"
cp .env.example .env
```

Add your API key to `.env`, then run:

```bash
python server.py
```

The app will still work without CrewAI installed.

## Data Model

The sample geography lives in [app/data.py](app/data.py). For the next version, replace this with imported CSV or GeoJSON:

- `places`: residential, school, hospital, office, competitor, selected test location
- `routes`: distance, duration, mode, selected-location detour
- `personas`: home, work/school, transport, schedule, purchase drivers

The critical rule: the LLM should explain only from these facts. It should not invent distances, routes, or locality claims.
