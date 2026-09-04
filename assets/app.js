const REPO = "duncan1315/TicketNotify";

function setupLinks() {
  document.getElementById("add-route-link").href =
    `https://github.com/${REPO}/issues/new?template=track-route.yml`;
  document.getElementById("add-flight-link").href =
    `https://github.com/${REPO}/issues/new?template=track-flight.yml`;
  document.getElementById("manual-check-link").href =
    `https://github.com/${REPO}/actions/workflows/manual-query.yml`;
}

function formatTimestamp(seconds) {
  if (!seconds) {
    return "not yet";
  }
  return new Date(seconds * 1000).toLocaleString();
}

function formatStops(stops) {
  if (stops == null) {
    return "Stops unknown";
  }
  if (stops === 0) {
    return "Direct";
  }
  return `${stops} stop${stops === 1 ? "" : "s"}`;
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
  const withinBudget = hasPrice && latest.lowest_price <= route.budget;
  const withinDuration = route.max_duration_minutes == null
    || latest.lowest_price_duration_minutes == null
    || latest.lowest_price_duration_minutes <= route.max_duration_minutes;
  const underBudget = withinBudget && withinDuration;

  const card = document.createElement("a");
  card.className = `route-card ${underBudget ? "status-under" : ""}`;
  card.href = `route.html?id=${encodeURIComponent(route.id)}`;

  const header = document.createElement("div");
  header.className = "route-card-header";

  const title = document.createElement("h2");
  title.textContent = `${route.origin} \u2192 ${route.destination}`;

  const badge = document.createElement("span");
  badge.className = `status-badge ${underBudget ? "status-under" : "status-watching"}`;
  badge.textContent = underBudget ? "Under budget" : "Watching";

  header.append(title, badge);

  const isRoundTrip = route.trip_type === "round_trip";
  const dateRange = isRoundTrip && route.return_date
    ? `${route.date}, return ${route.return_date}`
    : route.date;

  const details = document.createElement("dl");
  details.className = "route-details";
  details.append(
    detailRow("Trip type", isRoundTrip ? "Round trip" : "One way"),
    detailRow("Dates", dateRange),
    detailRow("Budget", `${route.budget} ${route.currency}`),
  );
  if (route.max_duration_minutes != null) {
    details.appendChild(detailRow("Max duration", `${route.max_duration_minutes} min`));
  }
  details.appendChild(detailRow("Last checked", formatTimestamp(latest.checked_at)));

  card.append(header, details);

  const priceLabel = document.createElement("p");
  priceLabel.className = "route-details";
  const dt = document.createElement("dt");
  dt.textContent = "Lowest price seen";
  priceLabel.appendChild(dt);
  card.appendChild(priceLabel);

  if (hasPrice) {
    card.appendChild(renderFlapPrice(`${latest.lowest_price} ${route.currency}`));
    const stopsNote = document.createElement("p");
    stopsNote.className = "price-note";
    stopsNote.textContent = formatStops(latest.lowest_price_stops);
    card.appendChild(stopsNote);

    if (withinBudget && !withinDuration) {
      const durationNote = document.createElement("p");
      durationNote.className = "price-note";
      durationNote.textContent = `Under budget, but ${latest.lowest_price_duration_minutes} min exceeds the ${route.max_duration_minutes} min limit`;
      card.appendChild(durationNote);
    }
  } else {
    const notChecked = document.createElement("p");
    notChecked.textContent = "Not checked yet";
    notChecked.style.color = "var(--ink-muted)";
    notChecked.style.fontSize = "14px";
    card.appendChild(notChecked);
  }

  return card;
}

function renderTrackedFlightCard(tracked) {
  const latest = tracked.latest || {};
  const wasChecked = latest.checked_at != null;
  const wasFound = latest.found === true;
  const withinBudget = wasFound && latest.price != null && latest.price <= tracked.budget;

  const card = document.createElement("a");
  card.className = `route-card ${withinBudget ? "status-under" : ""}`;
  card.href = `route.html?id=${encodeURIComponent(tracked.id)}`;

  const header = document.createElement("div");
  header.className = "route-card-header";

  const title = document.createElement("h2");
  title.textContent = tracked.issue_title || `${tracked.origin} \u2192 ${tracked.destination}`;

  const badgeLabel = !wasChecked
    ? "Watching"
    : !wasFound
    ? "Not found last check"
    : withinBudget
    ? "Found"
    : "Over budget";
  const badge = document.createElement("span");
  badge.className = `status-badge ${withinBudget ? "status-under" : "status-watching"}`;
  badge.textContent = badgeLabel;

  header.append(title, badge);

  const details = document.createElement("dl");
  details.className = "route-details";
  details.append(
    detailRow("Route", `${tracked.origin} \u2192 ${tracked.destination}`),
    detailRow("Date", tracked.date),
    detailRow("Departure / arrival", `${tracked.departure_time} \u2192 ${tracked.arrival_time}`),
    detailRow("Budget", `${tracked.budget} ${tracked.currency}`),
    detailRow("Last checked", formatTimestamp(latest.checked_at)),
  );
  if (latest.airline) {
    details.appendChild(detailRow("Matched airline", latest.airline));
  }

  card.append(header, details);

  const priceLabel = document.createElement("p");
  priceLabel.className = "route-details";
  const dt = document.createElement("dt");
  dt.textContent = "Last seen price";
  priceLabel.appendChild(dt);
  card.appendChild(priceLabel);

  if (wasFound && latest.price != null) {
    card.appendChild(renderFlapPrice(`${latest.price} ${tracked.currency}`));
    const stopsNote = document.createElement("p");
    stopsNote.className = "price-note";
    stopsNote.textContent = formatStops(latest.stops);
    card.appendChild(stopsNote);
  } else {
    const notFound = document.createElement("p");
    notFound.textContent = wasChecked ? "Not found in the last check" : "Not checked yet";
    notFound.style.color = "var(--ink-muted)";
    notFound.style.fontSize = "14px";
    card.appendChild(notFound);
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

async function loadTrackedFlights() {
  const listEl = document.getElementById("tracked-flight-list");
  const emptyState = document.getElementById("tracked-empty-state");

  try {
    const response = await fetch("data/tracked-index.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    const trackedFlights = await response.json();

    if (!trackedFlights.length) {
      emptyState.textContent = "No specific flights tracked yet.";
      return;
    }

    emptyState.remove();
    trackedFlights.forEach((tracked) => listEl.appendChild(renderTrackedFlightCard(tracked)));
  } catch (error) {
    emptyState.textContent = "No tracked flight data yet. It appears after the first scheduled check runs.";
  }
}

setupLinks();
loadRoutes();
loadTrackedFlights();
