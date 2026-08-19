const REPO = "your-username/your-repo";

function setupLinks() {
  document.getElementById("add-route-link").href =
    `https://github.com/${REPO}/issues/new?template=track-route.yml`;
  document.getElementById("manual-check-link").href =
    `https://github.com/${REPO}/actions/workflows/manual-query.yml`;
}

function formatTimestamp(seconds) {
  if (!seconds) {
    return "not yet";
  }
  return new Date(seconds * 1000).toLocaleString();
}

function renderFlapPrice(text) {
  const wrap = document.createElement("div");
  wrap.className = "flap-price";
  for (const char of text) {
    const tile = document.createElement("span");
    tile.className = "flap-char";
    tile.textContent = char === " " ? "\u00a0" : char;
    wrap.appendChild(tile);
  }
  return wrap;
}

function renderRouteCard(route) {
  const latest = route.latest || {};
  const hasPrice = latest.lowest_price != null;
  const underBudget = hasPrice && latest.lowest_price <= route.budget;

  const card = document.createElement("article");
  card.className = `route-card ${underBudget ? "status-under" : ""}`;

  const header = document.createElement("div");
  header.className = "route-card-header";

  const title = document.createElement("h2");
  title.textContent = `${route.origin} \u2192 ${route.destination}`;

  const badge = document.createElement("span");
  badge.className = `status-badge ${underBudget ? "status-under" : "status-watching"}`;
  badge.textContent = underBudget ? "Under budget" : "Watching";

  header.append(title, badge);

  const details = document.createElement("dl");
  details.className = "route-details";
  details.append(
    detailRow("Dates", `${route.earliest_date} to ${route.latest_date}`),
    detailRow("Budget", `${route.budget} ${route.currency}`),
    detailRow("Max duration", `${route.max_duration_minutes} min`),
    detailRow("Last checked", formatTimestamp(latest.checked_at)),
  );

  card.append(header, details);

  const priceLabel = document.createElement("p");
  priceLabel.className = "route-details";
  const dt = document.createElement("dt");
  dt.textContent = "Lowest price seen";
  priceLabel.appendChild(dt);
  card.appendChild(priceLabel);

  if (hasPrice) {
    card.appendChild(renderFlapPrice(`${latest.lowest_price} ${route.currency}`));
  } else {
    const notChecked = document.createElement("p");
    notChecked.textContent = "Not checked yet";
    notChecked.style.color = "var(--ink-muted)";
    notChecked.style.fontSize = "14px";
    card.appendChild(notChecked);
  }

  return card;
}

function detailRow(label, value) {
  const row = document.createElement("div");
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value;
  row.append(dt, dd);
  return row;
}

async function loadRoutes() {
  const listEl = document.getElementById("route-list");
  const emptyState = document.getElementById("empty-state");

  try {
    const response = await fetch("data/index.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    const routes = await response.json();

    if (!routes.length) {
      emptyState.textContent = "No routes tracked yet. Add one to start watching fares.";
      return;
    }

    emptyState.remove();
    routes.forEach((route) => listEl.appendChild(renderRouteCard(route)));
  } catch (error) {
    emptyState.textContent = "No price data yet. It appears after the first scheduled check runs.";
  }
}

setupLinks();
loadRoutes();
