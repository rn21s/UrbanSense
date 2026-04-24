# UrbanSense AI

UrbanSense AI is a locality intelligence application for evaluating whether a product, service, or store concept is suitable for a selected urban catchment. It combines map-based location search, nearby place intelligence, persona simulation, competitor analysis, and AI-generated strategy recommendations into a single decision workflow.

The application is designed for business teams testing concepts such as coffee shops, convenience products, food services, health products, retail ideas, and other hyperlocal demand opportunities.

## Core Capabilities

- Search and confirm a target location using Grab Maps.
- Simulate demand for a product or store concept against local personas.
- Detect the intended business concept from user input, such as coffee / cafe, food service, health, fitness, retail, or convenience.
- Measure direct competitor cannibalisation around the selected locality.
- Analyse demand anchors such as offices, schools, transit nodes, residential density, F&B clusters, and retail clusters.
- Visualise competitor and demand-anchor POIs on the map.
- Generate a strategist-style recommendation with factual supporting insights.
- Show persona-level outcomes in a horizontal results strip below the map.
- Keep revenue-sensitive claims explicit: active revenue is shown as unavailable unless connected to a real purchase metrics database.

## User Flow

1. Select a location from Grab Maps search.
2. Enter the product or concept the user intends to serve.
3. Choose category and market price positioning.
4. Run the simulation.
5. Review:
   - recommendation
   - locality demand signals
   - map markers
   - persona outcomes
   - competitor and cannibalisation context

## Tech Stack

### Backend

- Python standard library HTTP server
- Modular application code under `app/`
- Grab Maps API integration for POI search and nearby locality intelligence
- OneMap integration for route/locality support where available
- Optional CrewAI analysis layer
- Optional OpenAI Responses API strategy summarisation

### Frontend

- Static HTML, CSS, and JavaScript
- MapLibre GL through Grab Maps assets
- Responsive dashboard-style UI
- Client-side simulation playback, map overlays, timeline animation, and persona result rendering

### AI / Agent Layer

- `app/simulation.py` provides deterministic persona scoring and recommendation fallback.
- `app/crew_service.py` optionally uses CrewAI for an analyst-style report.
- `app/strategy_service.py` optionally uses OpenAI to summarise factual simulation results into a business-strategy recommendation.

The app runs without CrewAI or OpenAI configured. When AI services are unavailable, deterministic logic still produces a recommendation and insight bullets.

## Architecture

```text
User input
  -> static/app.js
  -> server.py
  -> app/grab_maps.py
  -> app/simulation.py
  -> optional app/strategy_service.py
  -> optional app/crew_service.py
  -> JSON result
  -> map overlays + recommendation UI + persona outcomes
```

## Methodology

### 1. Product Concept Detection

UrbanSense AI reads the product name, category, and notes to classify the tested concept.

Examples:

- `coffee shop`, `coffee`, `cafe`, `espresso` -> coffee / cafe
- `restaurant`, `meal`, `lunch`, `food` -> food service
- `medicine`, `health`, `pharmacy`, `clinic` -> health / pharmacy
- `gym`, `fitness`, `protein` -> fitness / wellness
- `shop`, `store`, `retail` -> retail

This concept determines which competitors, personas, and demand anchors matter most.

### 2. Competitor Cannibalisation

The backend calls Grab Maps nearby-place data for the selected location and classifies direct competitors according to the detected concept.

For a coffee / cafe concept, competitor signals include:

- cafes
- coffee shops
- espresso or specialty coffee concepts
- bakeries and toast shops
- tea shops
- nearby F&B alternatives competing for the same purchase occasion

The app returns:

- direct competitor count
- competitor examples
- cannibalisation risk: `Low`, `Medium`, or `High`
- competitor POIs for map markers

### 3. Locality Demand Anchors

UrbanSense AI analyses demand anchors around the selected catchment:

- offices and service businesses
- schools and colleges
- MRT / bus stops and transit points
- residential density
- nearby F&B clusters
- retail and mall clusters
- health and clinic anchors

These anchors help explain whether a concept has practical demand nearby. For example, a coffee concept benefits from office density, commuter traffic, and repeat weekday routines.

### 4. Persona Simulation

The simulation evaluates a set of locality personas with different schedules, travel patterns, need states, price sensitivity, and purchase triggers.

Each persona outcome includes:

- purchase probability
- likely / unlikely buyer status
- route and detour context
- persona-specific explanation
- timing and movement behaviour

Persona outputs are intentionally grounded in the data model and locality facts. They avoid generic repeated language by using each persona's specific motivation, travel mode, and demand occasion.

### 5. Active Revenue Potential

The UI includes an `Active revenue potential` field, but it is intentionally shown as:

```text
Nil
Requires connection to Grab Purchase Metrics DB
```

This prevents the app from implying real merchant revenue or profitability without access to a validated purchase metrics database. If connected later, this field can be replaced by actual order, basket, merchant activity, or revenue signals.

### 6. Recommendation Logic

The recommendation combines:

- simulated persona purchase probability
- route convenience
- office / school / transit / residential anchors
- competitor cannibalisation risk
- product concept fit
- demand-anchor strength
- missing-data limitations

The deterministic recommendation uses a locality opportunity score, so a location with strong anchors and limited direct competition is not rejected only because average persona probability is slightly below a fixed threshold.

### 7. OpenAI Strategy Summary

When `OPENAI_API_KEY` is available, UrbanSense AI sends the factual simulation result to the OpenAI Responses API and asks for a concise strategist-style recommendation.

The prompt explicitly requires the model to use only provided facts, including:

- direct competitor count
- cannibalisation risk
- office, school, transit, residential, F&B, and retail anchor counts
- persona fit
- simulated purchase probabilities
- unavailable active revenue metrics

The OpenAI output is used to improve narrative quality, not to invent data. If the request fails or the key is missing, the deterministic recommendation is used.

Default model:

```env
OPENAI_STRATEGY_MODEL=gpt-5.4-mini
```

### 8. CrewAI Analysis Layer

CrewAI is available as an optional analyst layer through `app/crew_service.py`.

When enabled, CrewAI receives the product, persona outcomes, and scenario facts, then produces an analyst-style report. The app guards this path behind environment variables so the main workflow remains stable without CrewAI installed.

Enable CrewAI with:

```env
CREWAI_USE_LLM=true
OPENAI_API_KEY=your_key_here
```

Install optional dependencies:

```bash
pip install -e ".[crewai]"
```

## Running The Application

Start the server:

```bash
python3 server.py
```

Open the printed local URL, usually:

```text
http://localhost:8000
```

The server automatically chooses the next available port from `8000` to `8009`.

## Environment Variables

Create a `.env` file when using external services.

```env
OPENAI_API_KEY=your_openai_key
OPENAI_STRATEGY_MODEL=gpt-5.4-mini
CREWAI_USE_LLM=false
ONEMAP_ACCESS_TOKEN=your_onemap_token
GRAB_MAPS_API_KEY=your_grab_maps_key
GRAB_MAPS_MCP_TOKEN=your_grab_maps_mcp_token
```

The app includes development defaults for local testing, but production deployments should use managed secrets.

## Key Files

```text
server.py                 HTTP server and API routing
app/data.py               Locality, route, catchment, and persona data
app/grab_maps.py          Grab Maps search and nearby-place intelligence
app/onemap.py             OneMap route/locality support
app/simulation.py         Persona scoring, timelines, recommendations
app/strategy_service.py   OpenAI strategy summary integration
app/crew_service.py       Optional CrewAI analyst layer
static/index.html         Application shell
static/app.js             Frontend state, map layers, simulation playback
static/styles.css         UI styling
```

## Insight Outputs

UrbanSense AI shares insights in three main places:

1. Recommendation panel
   - concise strategist recommendation
   - factual insight bullets
   - locality demand signals

2. Map view
   - selected location marker
   - competitor markers
   - demand-anchor markers
   - simulated persona movement paths

3. Persona outcomes
   - horizontal cards below the map
   - persona name, probability, buyer status, and tailored explanation

## Data Integrity Principles

- Do not claim profitability unless connected to real revenue or purchase data.
- Do not invent POI counts, routes, distances, or locality facts.
- Keep AI-generated summaries grounded in structured simulation facts.
- Label unavailable metrics clearly.
- Prefer conservative recommendations when competition is high or data is missing.

## Optional Dependencies

The base app runs with Python standard library modules. Optional packages are declared in `pyproject.toml`.

```toml
[project.optional-dependencies]
crewai = [
  "crewai>=0.175.0",
  "openai>=1.13.3"
]
```
