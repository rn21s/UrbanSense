let scenario = null;
let agentNodes = new Map();

const placeTypeLabel = {
  shell_select: "Shell Select",
  residential: "Residential",
  office: "Office",
  school: "School",
  hospital: "Hospital",
  competitor: "Competitor"
};

async function loadScenario() {
  const response = await fetch("/api/scenario");
  scenario = await response.json();
  drawMap();
}

function drawMap() {
  const map = document.querySelector("#map");
  map.innerHTML = "";

  [
    ["horizontal", 27],
    ["horizontal", 50],
    ["horizontal", 73],
    ["vertical", 30],
    ["vertical", 52],
    ["vertical", 78]
  ].forEach(([kind, pos]) => {
    const road = document.createElement("div");
    road.className = `road ${kind}`;
    if (kind === "horizontal") road.style.top = `${pos}%`;
    if (kind === "vertical") road.style.left = `${pos}%`;
    map.appendChild(road);
  });

  scenario.places.forEach(place => {
    const node = document.createElement("div");
    node.className = `place ${place.type}`;
    node.style.left = `${place.x}%`;
    node.style.top = `${place.y}%`;
    node.innerHTML = `<strong>${place.name}</strong><span>${placeTypeLabel[place.type]} · ${place.opening_hours}</span>`;
    map.appendChild(node);
  });

  scenario.personas.forEach(persona => {
    const home = scenario.places.find(place => place.id === persona.home) || scenario.places[0];
    const node = document.createElement("div");
    node.className = "agent";
    node.dataset.name = persona.name;
    node.style.left = `${home.x}%`;
    node.style.top = `${home.y}%`;
    map.appendChild(node);
    agentNodes.set(persona.name, node);
  });
}

async function simulate() {
  const button = document.querySelector("#simulateBtn");
  button.disabled = true;
  button.textContent = "Simulating...";

  const payload = {
    name: document.querySelector("#productName").value,
    category: document.querySelector("#category").value,
    price_sgd: document.querySelector("#price").value,
    notes: document.querySelector("#notes").value
  };

  const response = await fetch("/api/simulate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();

  await animateTimeline(result.timeline);
  renderTimeline(result.timeline);
  renderSummary(result);

  button.disabled = false;
  button.textContent = "Simulate Day";
}

function animateTimeline(timeline) {
  return new Promise(resolve => {
    let index = 0;
    const tick = () => {
      const event = timeline[index];
      if (!event) {
        resolve();
        return;
      }

      const place = scenario.places.find(item => item.id === event.place);
      const agent = agentNodes.get(event.persona);
      if (place && agent) {
        agent.style.left = `${place.x}%`;
        agent.style.top = `${place.y}%`;
      }

      index += 1;
      setTimeout(tick, 360);
    };
    tick();
  });
}

function renderTimeline(timeline) {
  const root = document.querySelector("#timeline");
  root.innerHTML = timeline.map(event => `
    <article class="event">
      <b>${event.time} · ${event.persona}</b>
      <span>${event.activity}</span>
    </article>
  `).join("");
}

function renderSummary(result) {
  const root = document.querySelector("#summary");
  root.innerHTML = `
    <h2>Recommendation</h2>
    <p>${result.summary.recommendation}</p>
    <div class="metric-row">
      <div class="metric"><strong>${result.summary.buyer_count}</strong><span>buyers</span></div>
      <div class="metric"><strong>${result.summary.maybe_count}</strong><span>maybes</span></div>
      <div class="metric"><strong>${result.summary.persona_count}</strong><span>personas</span></div>
    </div>
    <p><b>Engine:</b> ${result.summary.engine}</p>
    <p><b>Best windows:</b> ${result.summary.best_windows.join(", ")}</p>
    <div class="outcomes">
      ${result.outcomes.map(outcome => `
        <article class="outcome">
          <b>${outcome.name} · ${outcome.purchase_probability}%</b>
          <span>${outcome.quote}</span>
          <div class="badge">${outcome.will_buy ? "Likely buyer" : "Unlikely buyer"}</div>
        </article>
      `).join("")}
    </div>
    ${result.summary.crew_report ? `<p>${result.summary.crew_report}</p>` : ""}
  `;
}

document.querySelector("#simulateBtn").addEventListener("click", simulate);
loadScenario();

