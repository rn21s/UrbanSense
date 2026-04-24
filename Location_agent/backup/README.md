# Shell Select Locality Simulator POC

A small proof of concept for testing whether a new Shell Select product is likely to work in a local Singapore catchment area.

The POC keeps geography deterministic and structured, then uses persona-style reasoning to explain who would buy, why, and when. CrewAI is wired as an optional analysis layer, with a local fallback so the app can run without installing anything.

## What It Does

- Shows a sample Singapore locality with homes, school, hospital, offices, competitor pharmacy, and Shell Select.
- Simulates a 24-hour day for several personas.
- Tests a proposed product, such as paracetamol, baby wipes, protein bars, or ready meals.
- Produces a route-grounded summary using walking/driving distance, detour, timing, and persona needs.
- Supports a future CrewAI implementation path for richer multi-agent reports.

## Run The POC

This repo currently uses only Python standard library modules for the runnable POC.

```bash
python3 server.py
```

Then open:

```text
http://localhost:8000
```

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

- `places`: residential, school, hospital, office, competitor, Shell Select
- `routes`: distance, duration, mode, Shell detour
- `personas`: home, work/school, transport, schedule, purchase drivers

The critical rule: the LLM should explain only from these facts. It should not invent distances, routes, or locality claims.

