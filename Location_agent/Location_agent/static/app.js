let scenario = null;
let localityPlaces = [];
let map = null;
let agentNodes = new Map();
let agentCurrentPlaces = new Map();
let placeLookup = new Map();
let routeCache = new Map();
let formVisible = false;
let selectedPersonaIds = new Set();
let locationQuery = "";
let selectedLocation = null;
let grabSearchResults = [];
let grabSearchTimer = null;
let searchMarker = null;
let searchPopup = null;
let latestSimulationPlans = [];

const locationName = "MacPherson, Singapore";
const recentStorageKey = "demandlab_recent_simulations";
const starterRecentSimulations = [
  { location: locationName, product: "Paracetamol 500mg", date: "Apr 22, 2026" },
  { location: locationName, product: "Electrolyte drink", date: "Apr 21, 2026" },
  { location: locationName, product: "Protein bar", date: "Apr 20, 2026" }
];

const placeTypeLabel = {
  shell_select: "Selected store",
  residential: "Residential",
  office: "Office",
  school: "School",
  hospital: "Hospital",
  competitor: "Competitor",
  hotel: "Hotel",
  mall: "Mall",
  restaurant: "Restaurant",
  preschool: "Preschool",
  eldercare: "Eldercare",
  food_centre: "Food Centre",
  transport: "Transport"
};

const demoPlaceAliases = {
  hdb_101: "circuit_road_market",
  hdb_205: "ibis_macpherson",
  office_tower: "macpherson_mall",
  school: "little_seeds",
  hospital: "st_johns_home",
  pharmacy: "grantral_mall"
};

const agentColors = ["#dd1d21", "#2477a8", "#22884b", "#7b3f98", "#c77d00", "#00a6a6"];

async function loadScenario() {
  const scenarioResponse = await fetch("/api/scenario");
  scenario = await scenarioResponse.json();
  drawMap();
  showLocationSummary();
}

function drawMap() {
  const mapEl = document.querySelector("#map");
  if (!window.maplibregl) {
    mapEl.innerHTML = "<div class=\"map-error\">Grab map library did not load. Check internet access, then refresh.</div>";
    return;
  }

  try {
    map = new maplibregl.Map({
      container: "map",
      style: "/api/grab/style.json",
      center: [103.8198, 1.3521],
      zoom: 11,
      attributionControl: true
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-left");
    map.on("error", event => {
      console.warn("Grab Maps render warning", event?.error || event);
      if (!map.isStyleLoaded() && !mapEl.querySelector(".map-error")) {
        mapEl.insertAdjacentHTML("beforeend", "<div class=\"map-error\">Grab map credentials are not available on the server. Add GRAB_MAPS_API_KEY in .env, then refresh.</div>");
      }
    });
  } catch (error) {
    console.error(error);
    map = null;
    mapEl.innerHTML = "<div class=\"map-error\">Grab map could not be initialised. Check the server credentials, then refresh.</div>";
  }
}

async function simulate(event) {
  if (!selectedLocation) return;
  const button = event?.currentTarget || document.querySelector("#runSimulationBtn") || document.querySelector("#runSimulationFromProductBtn");
  const mapEl = document.querySelector("#map");
  button.disabled = true;
  button.textContent = "Running...";
  mapEl.classList.add("simulating");
  try {
    clearPersonaResults();
    clearMarketMapLayer();
    startDayNightAnimation();

    const payload = {
      name: document.querySelector("#productName").value.trim() || "Untitled product",
      category: document.querySelector("#category").value || "grocery",
      price_sgd: priceTierValue(document.querySelector("#price").value),
      price_tier: document.querySelector("#price").value,
      placement_assumption: defaultPlacementAssumption(),
      partnership_brand: "",
      location: selectedLocation,
      notes: productNotes()
    };
    if (selectedPersonaIds.size) {
      payload.selected_persona_ids = [...selectedPersonaIds];
    }

    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();

    showLiveSimulation();
    initLiveFeed();
    clearAgentMarkers();
    await waitForMapReady();
    if (map) map.resize();
    const plans = await buildTimelapsePlans(result.timeline);
    latestSimulationPlans = plans;
    renderSimulationMapLayer(plans);
    fitSimulationPlans(plans);
    resetAgentsFromPlans(plans);
    await animateTimeline(result.timeline, result, plans);
    collapseLiveSimulationPanel();
    renderSummary(result);
    renderPersonaResults(result.outcomes);
    renderMarketMapLayer(result.summary.locality);
    saveRecentSimulation(payload.name);
  } catch (error) {
    console.error(error);
    document.querySelector("#summary").innerHTML = `
      <section class="recommendation-card" aria-label="Simulation error">
        <div class="recommendation-card-header">
          <span>Simulation error</span>
          <strong>Unable to run simulation</strong>
        </div>
        <p>${escapeHtml(error.message || "Please check the selected location and try again.")}</p>
      </section>
    `;
    showLiveSimulation();
    collapseLiveSimulationPanel();
  } finally {
    mapEl.classList.remove("simulating");
    button.disabled = false;
    button.textContent = "Run Simulation";
  }
}

function productNotes() {
  const baseNotes = document.querySelector("#notes").value;
  return `${baseNotes} Placement assumption: ${defaultPlacementAssumption()}.`.trim();
}

function defaultPlacementAssumption() {
  return "counter";
}

function priceTierValue(tier) {
  const values = {
    value: 3.5,
    mainstream: 6.5,
    premium: 12,
    super_premium: 22,
  };
  return values[tier] ?? values.mainstream;
}

function showSimulationForm() {
  formVisible = true;
  setProgressStep("product");
  document.querySelector("#recentView").classList.add("is-hidden");
  document.querySelector("#locationSummaryView").classList.add("is-hidden");
  document.querySelector("#personaSelectionView").classList.add("is-hidden");
  document.querySelector("#liveSimulationView").classList.add("is-hidden");
  document.querySelector("#simulationForm").classList.remove("is-hidden");
  document.querySelector("#productName").focus();
}

function continueToPersonaSelection() {
  setProgressStep("product");
  document.querySelector("#simulationForm").classList.add("is-hidden");
  document.querySelector("#liveSimulationView").classList.add("is-hidden");
  document.querySelector("#personaSelectionView").classList.remove("is-hidden");
  renderPersonaSelection();
}

function showRecentView() {
  formVisible = false;
  setProgressStep("location");
  document.querySelector("#simulationForm").classList.add("is-hidden");
  document.querySelector("#personaSelectionView").classList.add("is-hidden");
  document.querySelector("#liveSimulationView").classList.add("is-hidden");
  document.querySelector("#locationSummaryView").classList.add("is-hidden");
  document.querySelector("#recentView").classList.remove("is-hidden");
  renderRecentSimulations();
}

function showLocationSummary() {
  formVisible = false;
  setProgressStep("location");
  document.querySelector("#recentView").classList.add("is-hidden");
  document.querySelector("#simulationForm").classList.add("is-hidden");
  document.querySelector("#personaSelectionView").classList.add("is-hidden");
  document.querySelector("#liveSimulationView").classList.add("is-hidden");
  document.querySelector("#locationSummaryView").classList.remove("is-hidden");
  renderLocationSummary();
}

function showLiveSimulation() {
  setProgressStep("results");
  document.querySelector("#recentView").classList.add("is-hidden");
  document.querySelector("#simulationForm").classList.add("is-hidden");
  document.querySelector("#personaSelectionView").classList.add("is-hidden");
  document.querySelector("#locationSummaryView").classList.add("is-hidden");
  document.querySelector("#liveSimulationView").classList.remove("is-hidden");
  expandLiveSimulationPanel();
}

function setProgressStep(step) {
  const order = ["location", "product", "results"];
  const currentIndex = Math.max(0, order.indexOf(step));
  const label = document.querySelector("#progressStepLabel");
  if (label) label.textContent = `Step ${currentIndex + 1} of ${order.length}`;

  document.querySelectorAll(".progress-step").forEach(item => {
    const index = order.indexOf(item.dataset.progressStep);
    item.classList.toggle("is-current", index === currentIndex);
    item.classList.toggle("is-done", index < currentIndex);
  });

  document.querySelectorAll(".progress-connector").forEach((connector, index) => {
    connector.classList.toggle("is-done", index < currentIndex);
  });
}

function renderPersonaSelection() {
  if (!selectedPersonaIds.size) {
    selectedPersonaIds = new Set(scenario.personas.map(persona => persona.id));
  }

  const root = document.querySelector("#personaGrid");
  root.innerHTML = scenario.personas.map(persona => {
    const relevance = personaRelevance(persona);
    const selected = selectedPersonaIds.has(persona.id);
    return `
      <button class="persona-card ${selected ? "is-selected" : "is-unselected"}" type="button" data-persona-id="${persona.id}">
        <span class="persona-relevance ${relevance.toLowerCase()}">${relevance}</span>
        <strong class="persona-name">
          ${persona.name}
          <span class="info-icon" tabindex="0" aria-label="${personaSummary(persona)}">i</span>
        </strong>
        <dl class="persona-facts">
          <div><dt>Travel mode</dt><dd>${persona.travel_mode}</dd></div>
          <div><dt>Peak hours</dt><dd>${formatPeakHours(persona.peak_hours)}</dd></div>
        </dl>
      </button>
    `;
  }).join("");

  root.querySelectorAll(".persona-card").forEach(card => {
    card.addEventListener("click", () => togglePersona(card.dataset.personaId));
  });
}

function togglePersona(personaId) {
  if (selectedPersonaIds.has(personaId)) {
    selectedPersonaIds.delete(personaId);
  } else {
    selectedPersonaIds.add(personaId);
  }
  if (!selectedPersonaIds.size) selectedPersonaIds.add(personaId);
  renderPersonaSelection();
}

function personaSummary(persona) {
  const text = persona.current_behaviour || persona.purchase_trigger || "Local shopper with a regular convenience touchpoint.";
  return text.length > 112 ? `${text.slice(0, 109)}...` : text;
}

function personaRelevance(persona) {
  const high = new Set([
    "morning_rusher",
    "school_run_parent_car",
    "school_run_parent_walking",
    "elderly_neighbourhood_regular",
    "lunch_breaker",
    "cabbie_grab_driver"
  ]);
  const low = new Set(["transient_traveller"]);
  if (high.has(persona.type)) return "High";
  if (low.has(persona.type)) return "Low";
  return "Possible";
}

function formatPeakHours(peakHours) {
  return peakHours.replace(/, (?=\d{1,2}:\d{2} [AP]M)/g, "<br>");
}

function renderLocationSummary() {
  const root = document.querySelector("#locationSummary");
  root.innerHTML = `
    <h2>Choose Location</h2>
    <label class="location-search">
      Search store or locality
      <input id="locationSearchInput" placeholder="Search with Grab Maps" value="${escapeHtml(locationQuery)}" autocomplete="off">
    </label>
    <div id="locationSearchResults" class="location-results"></div>
    ${selectedLocation ? `
      <article class="location-card is-selected" id="selectedLocationCard">
        <div class="location-card-copy">
          <span class="location-kicker">Selected zone</span>
          <strong>${escapeHtml(selectedLocation.name)}</strong>
          <span>${selectedLocationMeta(selectedLocation)}</span>
        </div>
        <span class="location-hot-badge">
          <span class="location-hot-icon" aria-hidden="true"></span>
          Hot
        </span>
      </article>
    ` : `
      <p class="location-empty">Search for the store or locality to begin.</p>
    `}
  `;

  const input = root.querySelector("#locationSearchInput");
  input.addEventListener("input", event => {
    locationQuery = event.target.value;
    scheduleGrabSearch(locationQuery);
  });
  const selectedCard = root.querySelector("#selectedLocationCard");
  if (selectedCard) selectedCard.addEventListener("click", focusSelectedLocation);
  renderLocationSearchResults();
  document.querySelector("#confirmLocationBtn").disabled = !selectedLocation;
  if (selectedLocation) focusSelectedLocation();
}

function selectedLocationMeta(location) {
  if (!location?.lat || !location?.lng) return "Singapore";
  return `Singapore · ${Math.abs(location.lat).toFixed(3)}° ${location.lat >= 0 ? "N" : "S"}, ${Math.abs(location.lng).toFixed(3)}° ${location.lng >= 0 ? "E" : "W"}`;
}

function scheduleGrabSearch(query) {
  clearTimeout(grabSearchTimer);
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    grabSearchResults = [];
    renderLocationSearchResults(trimmed ? "Keep typing to search Grab Maps." : "");
    return;
  }
  renderLocationSearchResults("Searching Grab Maps...");
  grabSearchTimer = setTimeout(() => searchGrabPlaces(trimmed), 300);
}

async function searchGrabPlaces(query) {
  try {
    const response = await fetch(`/api/grab/search?${new URLSearchParams({ keyword: query, limit: "8" })}`);
    if (!response.ok) throw new Error("Grab Maps search failed");
    const payload = await response.json();
    grabSearchResults = (payload.places || []).filter(place => place.lat && place.lng);
    const emptyMessage = payload.warning
      ? "Grab Maps is retrying. Try another spelling or search again."
      : "No Grab Maps results found.";
    renderLocationSearchResults(grabSearchResults.length ? "" : emptyMessage);
  } catch (error) {
    console.error(error);
    grabSearchResults = [];
    renderLocationSearchResults("Search is retrying. Type another character or try again.");
  }
}

function renderLocationSearchResults(message = "") {
  const root = document.querySelector("#locationSearchResults");
  if (!root) return;
  if (message) {
    root.innerHTML = `<p class="location-result-note">${escapeHtml(message)}</p>`;
    return;
  }
  root.innerHTML = grabSearchResults.map(place => `
    <button class="location-result" type="button" data-place-id="${escapeHtml(place.id)}">
      <strong>${escapeHtml(place.name)}</strong>
      <span>${escapeHtml(place.address)}</span>
    </button>
  `).join("");
  root.querySelectorAll(".location-result").forEach(button => {
    button.addEventListener("click", () => selectGrabLocation(button.dataset.placeId));
  });
}

function selectGrabLocation(placeId) {
  const place = grabSearchResults.find(item => item.id === placeId);
  if (!place) return;
  clearSimulationLayer();
  selectedLocation = {
    id: place.id,
    name: place.name,
    address: place.address,
    lat: place.lat,
    lng: place.lng,
    source: "Grab Maps"
  };
  locationQuery = place.name;
  grabSearchResults = [];
  renderLocationSummary();
}

function focusSelectedLocation() {
  if (!map || !selectedLocation?.lat || !selectedLocation?.lng) return;
  const lnglat = [selectedLocation.lng, selectedLocation.lat];
  if (!searchMarker) {
    const markerEl = document.createElement("div");
    markerEl.className = "search-location-pin";
    searchMarker = new maplibregl.Marker({ element: markerEl, anchor: "center" });
  }
  searchMarker.setLngLat(lnglat);
  if (!searchMarker.getElement().parentElement) searchMarker.addTo(map);
  if (!searchPopup) searchPopup = new maplibregl.Popup({ offset: 18 });
  searchPopup
    .setLngLat(lnglat)
    .setHTML(`<b>${escapeHtml(selectedLocation.name)}</b><br>${escapeHtml(selectedLocation.address)}`);
  searchMarker.setPopup(searchPopup);
  map.flyTo({ center: lnglat, zoom: 15, essential: true });
}

function catchmentSnapshot() {
  const stored = scenario?.locality?.catchment_snapshot;
  if (stored) {
    return {
      radiusKm: stored.radius_km,
      schools: stored.nearby_schools_count,
      businesses: stored.nearby_offices_business_parks_count,
      transport: stored.mrt_bus_stops_count,
      competitors: stored.competing_convenience_retail_count,
      residentialDensity: stored.residential_density_indicator,
      source: `${stored.source}; verified ${formatAddress(stored.verified_on)}.`
    };
  }

  const places = localityPlaces.filter(place => place.resolved);
  const schools = countTypes(places, ["school", "preschool"]);
  const businesses = countTypes(places, ["office", "mall", "hotel", "restaurant"]);
  const transport = countTypes(places, ["transport"]);
  const competitors = countTypes(places, ["mall", "food_centre", "competitor"]);
  const residentialSignals = countTypes(places, ["food_centre", "eldercare", "preschool"]);

  return {
    radiusKm: 5,
    schools,
    businesses,
    transport,
    competitors,
    residentialDensity: residentialSignals >= 3 ? "High" : residentialSignals >= 1 ? "Medium" : "Low",
    source: "Estimated from visible locality anchors."
  };
}

function countTypes(places, types) {
  return places.filter(place => types.includes(place.type)).length;
}

function renderRecentSimulations() {
  const root = document.querySelector("#recentSimulations");
  const simulations = loadRecentSimulations().slice(0, 5);

  root.innerHTML = simulations.map(item => `
    <article class="recent-run">
      <strong>${item.product}</strong>
      <span>${item.location}</span>
      <time>${item.date}</time>
    </article>
  `).join("");
}

function saveRecentSimulation(productName) {
  const simulations = loadRecentSimulations();
  const entry = {
    location: locationName,
    product: productName || "Untitled product",
    date: new Intl.DateTimeFormat("en-SG", {
      month: "short",
      day: "numeric",
      year: "numeric"
    }).format(new Date())
  };
  const next = [
    entry,
    ...simulations.filter(item => item.product !== entry.product || item.date !== entry.date)
  ].slice(0, 5);
  localStorage.setItem(recentStorageKey, JSON.stringify(next));
}

function loadRecentSimulations() {
  try {
    const saved = JSON.parse(localStorage.getItem(recentStorageKey) || "[]");
    return Array.isArray(saved) && saved.length ? saved : starterRecentSimulations;
  } catch {
    return starterRecentSimulations;
  }
}

function clearAgentMarkers() {
  agentNodes.forEach(marker => marker.remove());
  agentNodes = new Map();
  agentCurrentPlaces = new Map();
}

function clearSimulationLayer() {
  clearAgentMarkers();
  latestSimulationPlans = [];
  clearPersonaResults();
  clearMarketMapLayer();
  removeMapLayer("simulation-routes");
  removeMapLayer("simulation-points-labels");
  removeMapLayer("simulation-points");
  removeMapSource("simulation-routes");
  removeMapSource("simulation-points");
  document.querySelector("#timeline").innerHTML = "";
}

function removeMapLayer(layerId) {
  if (map?.getLayer(layerId)) map.removeLayer(layerId);
}

function removeMapSource(sourceId) {
  if (map?.getSource(sourceId)) map.removeSource(sourceId);
}

function resetAgents(timeline) {
  const activeNames = new Set(timeline.map(event => event.persona));
  scenario.personas.forEach(persona => {
    let marker = agentNodes.get(persona.name);
    if (!activeNames.has(persona.name)) {
      if (marker) marker.remove();
      if (marker) agentNodes.delete(persona.name);
      agentCurrentPlaces.delete(persona.name);
      return;
    }

    const firstEvent = timeline.find(event => event.persona === persona.name);
    const startingPlaceId = persona.home || firstEvent.place;
    const startingPlace = simulationPlaceFor(startingPlaceId, persona.name);
    if (startingPlace) {
      if (!marker) {
        marker = new maplibregl.Marker({
          element: agentIcon(agentDisplayName(persona), agentColor(persona.name)),
          anchor: "bottom"
        })
          .setPopup(new maplibregl.Popup({ offset: 24 }).setHTML(`<b>${agentDisplayName(persona)}</b><br>${persona.name}`))
          .addTo(map);
        agentNodes.set(persona.name, marker);
      }
      marker.setLngLat([startingPlace.lng, startingPlace.lat]);
      agentCurrentPlaces.set(persona.name, startingPlaceId);
    }
  });
  fitSimulationCatchment(timeline);
}

function resetAgentsFromPlans(plans) {
  if (!map) return;
  plans.forEach(plan => {
    const persona = scenario.personas.find(item => item.name === plan.persona);
    const firstPoint = plan.segments[0]?.path[0] || { lng: selectedLocation.lng, lat: selectedLocation.lat };
    const position = lngLatArray(firstPoint);
    if (!isValidLngLat(position)) return;

    const marker = new maplibregl.Marker({
      element: agentIcon(agentDisplayName(persona || { name: plan.persona }), agentColor(plan.persona)),
      anchor: "center"
    })
      .setLngLat(position)
      .setPopup(new maplibregl.Popup({ offset: 22 }).setHTML(`<b>${agentDisplayName(persona || { name: plan.persona })}</b><br>${persona?.name || plan.persona}`))
      .addTo(map);
    agentNodes.set(plan.persona, marker);
  });
}

async function animateTimeline(timeline, result, preparedPlans = null) {
  const plans = preparedPlans || await buildTimelapsePlans(timeline);
  if (!preparedPlans) {
    latestSimulationPlans = plans;
    renderSimulationMapLayer(plans);
    fitSimulationPlans(plans);
    resetAgentsFromPlans(plans);
  }
  const startMinute = Math.max(0, Math.min(...timeline.map(event => toMinutes(event.time))) - 30);
  const endMinute = Math.max(...timeline.map(event => toMinutes(event.time)), 24 * 60);
  const durationMs = 18000;
  const startedAt = performance.now();
  const liveEvents = buildLiveFeedEvents(plans, result).sort((a, b) => a.minute - b.minute);
  let nextLiveEvent = 0;
  renderSimulationScrubber(startMinute, endMinute);

  return new Promise(resolve => {
    const frame = now => {
      const elapsed = now - startedAt;
      const progress = Math.min(elapsed / durationMs, 1);
      const currentMinute = startMinute + (endMinute - startMinute) * progress;
      setClock(formatClock(currentMinute));
      updateSimulationScrubber(progress, currentMinute);

      plans.forEach(plan => {
        const marker = agentNodes.get(plan.persona);
        if (!marker) return;
        const nextPosition = positionForPlan(plan, currentMinute);
        if (isValidLngLat(nextPosition)) marker.setLngLat(nextPosition);
      });

      while (nextLiveEvent < liveEvents.length && liveEvents[nextLiveEvent].minute <= currentMinute) {
        appendLiveFeed(liveEvents[nextLiveEvent], elapsed);
        nextLiveEvent += 1;
      }

      if (progress < 1) {
        requestAnimationFrame(frame);
      } else {
        setClock("24:00");
        updateSimulationScrubber(1, endMinute);
        resolve();
      }
    };

    requestAnimationFrame(frame);
  });
}

async function buildTimelapsePlans(timeline) {
  const byPersona = new Map();
  timeline.forEach(event => {
    if (!byPersona.has(event.persona)) byPersona.set(event.persona, []);
    byPersona.get(event.persona).push(event);
  });

  const plans = [];
  for (const [personaName, events] of byPersona.entries()) {
    const persona = scenario.personas.find(item => item.name === personaName);
    if (!persona) continue;

    const sortedEvents = [...events].sort((a, b) => toMinutes(a.time) - toMinutes(b.time));
    const firstPlaceId = persona.home || sortedEvents[0].place;
    let previousPlaceId = firstPlaceId;
    let previousMinute = Math.max(0, toMinutes(sortedEvents[0].time) - 30);
    const segments = [];

    for (const event of sortedEvents) {
      const destinationId = event.place;
      const originPlace = simulationPlaceFor(previousPlaceId, persona.name);
      const destinationPlace = simulationPlaceFor(destinationId, persona.name);
      const destinationMinute = toMinutes(event.time);
      if (!previousPlaceId || !destinationId || !destinationPlace) continue;

      const mode = routeModeFor(event.persona_type);
      const path = localSimulationPath(originPlace, destinationPlace, persona.name, destinationMinute);
      segments.push({
        startMinute: previousMinute,
        endMinute: Math.max(previousMinute + 1, destinationMinute),
        originId: previousPlaceId,
        destinationId,
        originPlace,
        destinationPlace,
        mode,
        path: normalizePath(path),
        event
      });

      previousPlaceId = destinationId;
      previousMinute = destinationMinute;
    }

    plans.push({
      persona: personaName,
      segments
    });
  }
  return plans;
}

function startDayNightAnimation() {
  const card = document.querySelector(".day-night-card");
  const body = document.querySelector("#celestialBody");
  if (!card || !body) return;
  card.classList.remove("active");
  body.className = "celestial sun";
  setClock("06:00");
  void card.offsetWidth;
  card.classList.add("active");

  setTimeout(() => {
    body.className = "celestial moon";
  }, 11800);
}

function setClock(time) {
  const clockLabel = document.querySelector("#clockLabel");
  if (clockLabel) clockLabel.textContent = time;
  const liveClock = document.querySelector("#liveClock");
  if (liveClock) liveClock.textContent = time;
}

function renderSimulationScrubber(startMinute, endMinute) {
  const root = document.querySelector("#timeline");
  root.innerHTML = `
    <div class="simulation-scrubber">
      <div class="scrubber-meta">
        <span>${formatClock(startMinute)}</span>
        <strong>10x route timelapse</strong>
        <span>${formatClock(endMinute)}</span>
      </div>
      <div class="scrubber-track">
        <span id="scrubberFill"></span>
      </div>
    </div>
  `;
}

function updateSimulationScrubber(progress, currentMinute) {
  const fill = document.querySelector("#scrubberFill");
  if (fill) fill.style.width = `${Math.round(progress * 100)}%`;
  const liveClock = document.querySelector("#liveClock");
  if (liveClock) liveClock.textContent = formatClock(currentMinute);
}

function initLiveFeed() {
  document.querySelector("#liveFeed").innerHTML = `
    <article class="feed-item">
      <time>0:00</time>
      <p>Simulation started. Agents begin moving through the ${selectedLocation?.name || "selected"} catchment.</p>
    </article>
  `;
  document.querySelector("#summary").innerHTML = "";
}

function expandLiveSimulationPanel() {
  const panel = document.querySelector("#liveSimulationPanel");
  if (panel) panel.classList.remove("is-collapsed");
}

function collapseLiveSimulationPanel() {
  const panel = document.querySelector("#liveSimulationPanel");
  if (panel) panel.classList.add("is-collapsed");
}

function appendLiveFeed(item, elapsedMs) {
  const root = document.querySelector("#liveFeed");
  root.insertAdjacentHTML("afterbegin", `
    <article class="feed-item">
      <time>${formatElapsed(elapsedMs)}</time>
      <p>${item.message}</p>
    </article>
  `);
}

function buildLiveFeedEvents(plans, result) {
  const product = result?.product || {};
  const placement = defaultPlacementAssumption();
  const events = [];

  plans.forEach(plan => {
    const persona = scenario.personas.find(item => item.name === plan.persona);
    if (!persona) return;
    plan.segments.forEach(segment => {
      const destination = segment.destinationPlace || resolvePlace(segment.destinationId);
      const origin = segment.originPlace || resolvePlace(segment.originId);
      const personaName = persona.name.replace(/^The /, "");
      events.push({
        minute: segment.startMinute + 1,
        message: `${personaName} leaves ${origin?.displayName || "a nearby stop"} by ${segment.mode}. ${movementNuance(persona, segment.mode)}`
      });
      events.push({
        minute: segment.startMinute + (segment.endMinute - segment.startMinute) * 0.62,
        message: `${personaName} approaches ${destination?.displayName || "the next stop"}. Evaluating ${product.name || "the product"} visibility at ${placement}; observing route friction and browsing intent.`
      });
      events.push({
        minute: segment.endMinute,
        message: arrivalMessage(persona, segment, destination, product, placement)
      });
    });
  });

  return events;
}

function movementNuance(persona, mode) {
  if (persona.type === "elderly_neighbourhood_regular") {
    return "Walking slowly, pausing at crossings, with higher sensitivity to heat and shelf accessibility.";
  }
  if (persona.type === "school_run_parent_car") {
    return "Movement is fast and parking-led; store entry depends on forecourt visibility.";
  }
  if (persona.type === "morning_rusher") {
    return "Time pressure is high; only highly visible, low-effort products get attention.";
  }
  if (persona.type === "cabbie_grab_driver") {
    return "Route is opportunistic between rides; speed and counter placement matter.";
  }
  if (mode === "walk") return "Walking route keeps the store visually available along the path.";
  if (mode === "drive") return "Driving route makes visibility from road and pump area important.";
  return "Transit movement compresses dwell time and rewards simple product recognition.";
}

function arrivalMessage(persona, segment, destination, product, placement) {
  const personaName = persona.name.replace(/^The /, "");
  if (segment.destinationId === "shell_select") {
    return `${personaName} enters the selected store. Checking whether ${product.name || "the product"} is noticeable from ${placement}; observing behavior, hesitation, and impulse-fit.`;
  }
  return `${personaName} reaches ${destination?.displayName || "the next stop"}. Capturing whether the selected-store detour still feels plausible after this movement.`;
}

function formatElapsed(ms) {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function renderSummary(result) {
  const root = document.querySelector("#summary");
  root.innerHTML = `
    <section class="recommendation-card" aria-label="Recommendation">
      <div class="recommendation-card-header">
        <span>Key insight</span>
        <strong>Recommendation</strong>
      </div>
      <p>${result.summary.recommendation}</p>
      ${renderRecommendationInsights(result.summary.recommendation_insights)}
    </section>
    ${renderMarketInsights(result.summary.locality)}
    ${result.summary.crew_report ? `<p>${result.summary.crew_report}</p>` : ""}
  `;
}

function renderRecommendationInsights(insights = []) {
  if (!Array.isArray(insights) || !insights.length) return "";
  return `
    <div class="recommendation-insights">
      ${insights.slice(0, 5).map(insight => `
        <span>${escapeHtml(insight)}</span>
      `).join("")}
    </div>
  `;
}

function renderMarketInsights(locality) {
  if (!locality) return "";
  const activeRevenue = locality.active_revenue_potential || {};
  const snapshot = catchmentSnapshot();
  const items = [
    { label: locality.competitor_label || "Direct competitors", value: locality.competitor_count || 0, tone: "risk" },
    { label: "Cannibalisation risk", value: riskLabel(locality.cannibalisation_risk || locality.crowding), tone: locality.cannibalisation_risk || locality.crowding },
    {
      label: "Active revenue potential",
      value: "Nil",
      note: "Requires connection to Grab Purchase Metrics DB",
      tone: "anchor"
    },
    { label: "Nearby schools / preschools", value: snapshot.schools, tone: "anchor" },
    { label: "Offices / business parks", value: snapshot.businesses, tone: "anchor" },
    { label: "MRT / bus stops", value: snapshot.transport, tone: "anchor" },
    { label: "Competing convenience retail", value: snapshot.competitors, tone: "anchor" },
    { label: "Residential density", value: snapshot.residentialDensity, tone: "anchor" },
  ];
  return `
    <div class="market-insights">
      <div class="market-insights-header">
        <div>
          <h3>Locality Demand Signals</h3>
          <p>${escapeHtml(activeRevenue.explanation || "Signals are based on nearby POIs and local demand anchors.")}</p>
        </div>
        <span>${locality.poi_count || 0} POIs scanned</span>
      </div>
      <div class="market-signal-grid">
        ${items.map(item => `
          <article class="market-signal ${signalToneClass(item.tone)}">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
            ${item.note ? `<em>${escapeHtml(item.note)}</em>` : ""}
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderPersonaResults(outcomes = []) {
  const root = document.querySelector("#personaResults");
  if (!root) return;
  if (!outcomes.length) {
    clearPersonaResults();
    return;
  }
  root.classList.remove("is-hidden");
  root.innerHTML = `
    <div class="persona-results-header">
      <h3>Persona Outcomes</h3>
      <span>${outcomes.length} simulated personas</span>
    </div>
    <div class="persona-results-strip">
      ${outcomes.map(outcome => `
        <article class="outcome persona-result-card">
          <b>${escapeHtml(outcome.agent_name || outcome.name)} · ${outcome.purchase_probability}%</b>
          <span>${escapeHtml(outcome.name)}</span>
          <span>${escapeHtml(outcome.quote)}</span>
          <div class="badge">${outcome.will_buy ? "Likely buyer" : "Unlikely buyer"}</div>
        </article>
      `).join("")}
    </div>
  `;
}

function clearPersonaResults() {
  const root = document.querySelector("#personaResults");
  if (!root) return;
  root.innerHTML = "";
  root.classList.add("is-hidden");
}

function clearMarketMapLayer() {
  removeMapLayer("market-poi-labels");
  removeMapLayer("market-pois");
  removeMapSource("market-pois");
}

function riskLabel(value) {
  const normalized = String(value || "unknown").toLowerCase();
  if (normalized === "high") return "High";
  if (normalized === "medium") return "Medium";
  if (normalized === "low") return "Low";
  return "Unknown";
}

function signalToneClass(tone) {
  const normalized = String(tone || "").toLowerCase();
  if (normalized === "high") return "is-high";
  if (normalized === "medium") return "is-medium";
  if (normalized === "low") return "is-low";
  if (normalized === "risk") return "is-risk";
  return "";
}

function resolvePlace(placeId) {
  return placeLookup.get(placeId) || placeLookup.get(demoPlaceAliases[placeId]);
}

function agentDisplayName(persona) {
  return persona.agent_name || persona.name;
}

function boundsFromPlaces(places) {
  const coordinates = places
    .filter(place => place.resolved)
    .map(place => [place.resolved.lat, place.resolved.lng]);
  if (!coordinates.length) return null;

  return L.latLngBounds(coordinates).pad(0.18);
}

function canonicalPlaceId(placeId) {
  return placeLookup.has(placeId) ? placeId : demoPlaceAliases[placeId];
}

function routeModeFor(personaType) {
  if (
    personaType === "school_run_parent_car"
    || personaType === "weekend_family_shopper"
    || personaType === "ev_fuel_regular"
    || personaType === "transient_traveller"
    || personaType === "cabbie_grab_driver"
  ) return "drive";
  if (personaType === "morning_rusher") return "bus";
  return "walk";
}

function simulationPlaceFor(placeId, personaName = "") {
  if (!selectedLocation) return null;
  const center = {
    id: "shell_select",
    displayName: selectedLocation.name,
    lat: selectedLocation.lat,
    lng: selectedLocation.lng
  };
  if (placeId === "shell_select") return center;

  const localOffsets = {
    hdb_101: [-720, -420, "Residential west"],
    hdb_205: [760, 360, "Residential east"],
    office_tower: [540, -660, "Office cluster"],
    school: [-520, 520, "School / preschool"],
    hospital: [140, 780, "Care facility"],
    pharmacy: [860, -180, "Competing retail"],
    macpherson_mall: [680, -300, "Retail cluster"],
    ibis_macpherson: [430, 470, "Hotel / visitors"],
    circuit_road_market: [-780, 160, "Resident market"],
    little_seeds: [-460, 590, "Preschool"],
    st_johns_home: [220, 760, "Eldercare"],
    mattar_mrt: [60, -860, "Transit stop"],
    grantral_mall: [880, -260, "Convenience competitor"]
  };
  const alias = demoPlaceAliases[placeId] || placeId;
  const fallback = offsetForPersona(personaName || alias);
  const [eastM, northM, label] = localOffsets[placeId] || localOffsets[alias] || fallback;
  const coord = offsetCoordinate(selectedLocation.lat, selectedLocation.lng, eastM, northM);
  return {
    id: placeId,
    displayName: label || "Local activity point",
    lat: coord.lat,
    lng: coord.lng
  };
}

function offsetForPersona(seed) {
  let total = 0;
  for (const char of seed) total += char.charCodeAt(0);
  const angle = (total % 360) * Math.PI / 180;
  const radius = 520 + (total % 360);
  return [
    Math.cos(angle) * radius,
    Math.sin(angle) * radius,
    "Local activity point"
  ];
}

function offsetCoordinate(lat, lng, eastM, northM) {
  const latDelta = northM / 111320;
  const lngDelta = eastM / (111320 * Math.cos(lat * Math.PI / 180));
  return {
    lat: lat + latDelta,
    lng: lng + lngDelta
  };
}

function localSimulationPath(origin, destination, seed, minute) {
  if (!origin || !destination) return [];
  const bend = offsetCoordinate(
    (origin.lat + destination.lat) / 2,
    (origin.lng + destination.lng) / 2,
    ((seed.length * 37 + minute) % 180) - 90,
    ((seed.length * 53 + minute) % 180) - 90
  );
  return [
    [origin.lng, origin.lat],
    [bend.lng, bend.lat],
    [destination.lng, destination.lat]
  ];
}

function fitSimulationCatchment(timeline) {
  if (!map || !selectedLocation || !timeline.length) return;
  const points = [[selectedLocation.lng, selectedLocation.lat]];
  timeline.forEach(event => {
    const place = simulationPlaceFor(event.place, event.persona);
    if (place) points.push([place.lng, place.lat]);
  });
  scenario.personas.forEach(persona => {
    const place = simulationPlaceFor(persona.home, persona.name);
    if (place) points.push([place.lng, place.lat]);
  });
  const bounds = points.reduce(
    (box, point) => box.extend(point),
    new maplibregl.LngLatBounds(points[0], points[0])
  );
  map.fitBounds(bounds, {
    padding: { top: 70, bottom: 70, left: 70, right: 70 },
    maxZoom: 15,
    duration: 600
  });
}

function renderSimulationMapLayer(plans) {
  if (!map || !plans.length) return;
  if (!map.isStyleLoaded()) {
    map.once("load", () => renderSimulationMapLayer(plans));
    return;
  }
  const routeFeatures = [];
  const pointLookup = new Map();

  plans.forEach(plan => {
    const persona = scenario.personas.find(item => item.name === plan.persona);
    const color = agentColor(plan.persona);
    plan.segments.forEach(segment => {
      if (segment.path.length > 1) {
        routeFeatures.push({
          type: "Feature",
          properties: {
            persona: agentDisplayName(persona || { name: plan.persona }),
            color,
            mode: segment.mode
          },
          geometry: {
            type: "LineString",
            coordinates: segment.path.map(point => [point.lng, point.lat])
          }
        });
      }
      [segment.originPlace, segment.destinationPlace].forEach(place => {
        if (!place) return;
        pointLookup.set(place.id || `${place.lng},${place.lat}`, place);
      });
    });
  });

  pointLookup.set("selected_location", {
    id: "selected_location",
    displayName: selectedLocation.name,
    lat: selectedLocation.lat,
    lng: selectedLocation.lng
  });

  const pointFeatures = [...pointLookup.values()].map(place => ({
    type: "Feature",
    properties: {
      title: place.displayName || place.name || "Local point",
      isStore: place.id === "shell_select" || place.id === "selected_location"
    },
    geometry: {
      type: "Point",
      coordinates: [place.lng, place.lat]
    }
  }));

  upsertGeoJsonSource("simulation-routes", {
    type: "FeatureCollection",
    features: routeFeatures
  });
  upsertGeoJsonSource("simulation-points", {
    type: "FeatureCollection",
    features: pointFeatures
  });

  if (!map.getLayer("simulation-routes")) {
    map.addLayer({
      id: "simulation-routes",
      type: "line",
      source: "simulation-routes",
      paint: {
        "line-color": ["get", "color"],
        "line-width": 3,
        "line-opacity": 0.42,
        "line-dasharray": [1.2, 1.2]
      }
    });
  }
  if (!map.getLayer("simulation-points")) {
    map.addLayer({
      id: "simulation-points",
      type: "circle",
      source: "simulation-points",
      paint: {
        "circle-radius": ["case", ["get", "isStore"], 8, 5],
        "circle-color": ["case", ["get", "isStore"], "#dd1d21", "#22884b"],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
        "circle-opacity": 0.9
      }
    });
  }
  if (!map.getLayer("simulation-points-labels")) {
    map.addLayer({
      id: "simulation-points-labels",
      type: "symbol",
      source: "simulation-points",
      layout: {
        "text-field": ["get", "title"],
        "text-size": 12,
        "text-offset": [0, 1.1],
        "text-anchor": "top"
      },
      paint: {
        "text-color": "#15201b",
        "text-halo-color": "#ffffff",
        "text-halo-width": 1.5
      }
    });
  }
}

function renderMarketMapLayer(locality) {
  if (!map || !locality?.map_pois?.length) return;
  if (!map.isStyleLoaded()) {
    map.once("load", () => renderMarketMapLayer(locality));
    return;
  }

  const features = locality.map_pois
    .filter(place => Number.isFinite(place.lng) && Number.isFinite(place.lat))
    .map(place => ({
      type: "Feature",
      properties: {
        title: place.name || "Local POI",
        kind: place.kind || "anchor",
        category: place.category || ""
      },
      geometry: {
        type: "Point",
        coordinates: [place.lng, place.lat]
      }
    }));
  if (!features.length) return;

  upsertGeoJsonSource("market-pois", {
    type: "FeatureCollection",
    features
  });

  if (!map.getLayer("market-pois")) {
    map.addLayer({
      id: "market-pois",
      type: "circle",
      source: "market-pois",
      paint: {
        "circle-radius": ["case", ["==", ["get", "kind"], "competitor"], 7, 5],
        "circle-color": [
          "match",
          ["get", "kind"],
          "competitor", "#e73c46",
          "school", "#3b82f6",
          "office", "#7c3aed",
          "transport", "#0f766e",
          "residential", "#f59e0b",
          "#00b14f"
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
        "circle-opacity": 0.94
      }
    });
  }

  if (!map.getLayer("market-poi-labels")) {
    map.addLayer({
      id: "market-poi-labels",
      type: "symbol",
      source: "market-pois",
      layout: {
        "text-field": ["get", "title"],
        "text-size": 11,
        "text-offset": [0, 1.1],
        "text-anchor": "top",
        "text-optional": true
      },
      paint: {
        "text-color": "#15201b",
        "text-halo-color": "#ffffff",
        "text-halo-width": 1.5
      }
    });
  }
}

function fitSimulationPlans(plans) {
  if (!map || !selectedLocation || !plans.length) return;
  const points = [[selectedLocation.lng, selectedLocation.lat]];
  plans.forEach(plan => {
    plan.segments.forEach(segment => {
      segment.path.forEach(point => points.push([point.lng, point.lat]));
    });
  });
  const validPoints = points.filter(isValidLngLat);
  if (!validPoints.length) return;
  const bounds = validPoints.reduce(
    (box, point) => box.extend(point),
    new maplibregl.LngLatBounds(validPoints[0], validPoints[0])
  );
  map.fitBounds(bounds, {
    padding: { top: 90, bottom: 90, left: 90, right: 90 },
    maxZoom: 15.8,
    duration: 900
  });
}

function upsertGeoJsonSource(sourceId, data) {
  const existing = map.getSource(sourceId);
  if (existing) {
    existing.setData(data);
    return;
  }
  map.addSource(sourceId, {
    type: "geojson",
    data
  });
}

async function routePath(originId, destinationId, mode, destinationPlace) {
  const origin = placeLookup.get(originId);
  if (!origin || !destinationPlace || originId === destinationId) {
    return destinationPlace ? [[destinationPlace.lat, destinationPlace.lng]] : [];
  }

  const cacheKey = `${originId}:${destinationId}:${mode}`;
  if (routeCache.has(cacheKey)) return routeCache.get(cacheKey);

  try {
    const params = new URLSearchParams({ origin: originId, destination: destinationId, mode });
    const response = await fetch(`/api/onemap/route?${params.toString()}`);
    if (!response.ok) throw new Error("Route unavailable");
    const route = await response.json();
    const geometry = Array.isArray(route.geometry) && route.geometry.length > 1
      ? route.geometry
      : [[origin.lat, origin.lng]];
    routeCache.set(cacheKey, geometry);
    return geometry;
  } catch {
    // No official route means no movement. This avoids unrealistic diagonal map-crossing.
    console.warn(`No official route for ${originId} -> ${destinationId} (${mode}); agent will wait in place.`);
    return [[origin.lat, origin.lng]];
  }
}

function placeIcon(place) {
  if (place.type === "shell_select") {
    return L.divIcon({
      className: "",
      html: `<div class="shell-map-pin" aria-label="Selected store">
        <span class="shell-map-pin-center"></span>
      </div>`,
      iconSize: [64, 74],
      iconAnchor: [32, 58]
    });
  }

  const letter = place.name.charAt(0);
  return L.divIcon({
    className: "",
    html: `<div class="place-pin context">${letter}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });
}

function shellHoverCard(place) {
  const address = formatAddress(place.resolved?.address || "MacPherson Road, Singapore");
  return `
    <div class="shell-hover-card">
      <strong>${place.name}</strong>
      <span>${address}</span>
    </div>
  `;
}

function formatAddress(address) {
  return address
    .toLowerCase()
    .split(/\s+/)
    .map(word => /^\d/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("\"", "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function agentIcon(name, color) {
  const marker = document.createElement("div");
  marker.className = "agent-dot-marker";
  marker.style.setProperty("--agent-color", color);
  marker.title = name;
  marker.innerHTML = `
    <span class="agent-dot-pulse"></span>
    <span class="agent-dot-core"></span>
    <span class="agent-dot-label">${escapeHtml(name)}</span>
  `;
  return marker;
}

function normalizePath(path) {
  return path.map(point => ({ lng: point[0], lat: point[1] }));
}

function positionForPlan(plan, minute) {
  if (!plan.segments.length) return [selectedLocation.lng, selectedLocation.lat];
  let segment = plan.segments[0];

  if (minute <= segment.startMinute) return lngLatArray(segment.path[0]);

  for (const item of plan.segments) {
    if (minute <= item.endMinute) {
      segment = item;
      break;
    }
    segment = item;
  }

  if (minute >= segment.endMinute) return lngLatArray(segment.path[segment.path.length - 1]);
  if (segment.path.length < 2) return lngLatArray(segment.path[0]);

  const progress = (minute - segment.startMinute) / (segment.endMinute - segment.startMinute);
  return interpolatePath(segment.path, Math.max(0, Math.min(1, progress)));
}

function interpolatePath(path, progress) {
  const segments = buildSegments(path);
  const totalDistance = segments[segments.length - 1].endDistance || 1;
  const targetDistance = totalDistance * progress;
  const segment = segments.find(item => targetDistance <= item.endDistance) || segments[segments.length - 1];
  const segmentProgress = segment.distance
    ? (targetDistance - segment.startDistance) / segment.distance
    : 1;
  return [
    segment.from.lng + (segment.to.lng - segment.from.lng) * segmentProgress,
    segment.from.lat + (segment.to.lat - segment.from.lat) * segmentProgress
  ];
}

function buildSegments(points) {
  let total = 0;
  const segments = [];
  for (let index = 0; index < points.length - 1; index += 1) {
    const from = points[index];
    const to = points[index + 1];
    const distance = coordinateDistance(from, to);
    segments.push({
      from,
      to,
      distance,
      startDistance: total,
      endDistance: total + distance
    });
    total += distance;
  }
  return segments;
}

function lngLatArray(point) {
  return [point.lng, point.lat];
}

function isValidLngLat(value) {
  return Array.isArray(value)
    && value.length === 2
    && Number.isFinite(value[0])
    && Number.isFinite(value[1]);
}

function waitForMapReady() {
  return new Promise(resolve => {
    if (!map) {
      resolve();
      return;
    }
    if (map.loaded() && map.isStyleLoaded()) {
      resolve();
      return;
    }
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    map.once("idle", finish);
    map.once("error", finish);
    setTimeout(finish, 3000);
  });
}

function coordinateDistance(from, to) {
  const lat1 = from.lat * Math.PI / 180;
  const lat2 = to.lat * Math.PI / 180;
  const deltaLat = lat2 - lat1;
  const deltaLng = (to.lng - from.lng) * Math.PI / 180;
  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLng / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function agentColor(name) {
  let total = 0;
  for (const char of name) total += char.charCodeAt(0);
  return agentColors[total % agentColors.length];
}

function toMinutes(time) {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function formatClock(minute) {
  const rounded = Math.min(24 * 60, Math.max(0, Math.round(minute)));
  const hours = Math.floor(rounded / 60);
  const minutes = rounded % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

bindClick("#newSimulationBtn", showLocationSummary);
bindClick("#confirmLocationBtn", showSimulationForm);
bindClick("#backToLocationBtn", showLocationSummary);
bindClick("#runSimulationFromProductBtn", simulate);
bindClick("#backToProductBtn", showSimulationForm);
bindClick("#runSimulationBtn", simulate);
loadScenario();

function bindClick(selector, handler) {
  const element = document.querySelector(selector);
  if (element) element.addEventListener("click", handler);
}
