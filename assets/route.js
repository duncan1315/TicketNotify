const REPO = "duncan1315/TicketNotify";

function getRouteIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("id");
}

function formatTimestamp(seconds) {
  if (!seconds) {
    return "not yet";
  }
  return new Date(seconds * 1000).toLocaleString();
}

function formatShortDate(seconds) {
  return new Date(seconds * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
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

// history.jsonl is append-only newline-delimited JSON, not a JSON array,
// so it can't be parsed with a single JSON.parse() call the way
// data/index.json can.
function parseJsonl(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
}

function renderRouteHeader(route) {
  document.getElementById("route-title").textContent = `${route.origin} \u2192 ${route.destination}`;
  document.title = `${route.origin} \u2192 ${route.destination} — Route history`;

  const isRoundTrip = route.trip_type === "round_trip";
  const dateRange = isRoundTrip && route.return_date
    ? `${route.date} \u2192 ${route.return_date}`
    : route.date;

  document.getElementById("route-subtitle").textContent =
    `Budget ${route.budget} ${route.currency} \u00b7 ${dateRange}`;
}

function renderTrackedFlightHeader(tracked) {
  const label = tracked.issue_title || `${tracked.origin} \u2192 ${tracked.destination}`;
  document.getElementById("route-title").textContent = label;
  document.title = `${label} — Flight history`;

  document.getElementById("route-subtitle").textContent =
    `${tracked.airline} \u00b7 ${tracked.departure_time} \u2192 ${tracked.arrival_time} \u00b7 ${tracked.date}`;
}

// Reshapes a tracked-flight history entry (price/stops/found) into the
// same field names renderChart() and renderHistoryTable() already expect
// (lowest_price/lowest_price_stops/match_count), so those two rendering
// functions can be shared between routes and tracked flights instead of
// needing a second parallel implementation for each. match_count is 1
// when the flight was found in that check and 0 when it wasn't — the
// tracked-flight equivalent of "did anything match the route's filters".
function normalizeTrackedHistoryEntry(entry) {
  return {
    checked_at: entry.checked_at,
    lowest_price: entry.price,
    lowest_price_stops: entry.stops,
    match_count: entry.found ? 1 : 0,
  };
}

// A minimal inline line chart. No charting library is used here because
// the rest of this project has zero build tooling or npm dependencies —
// pulling one in for a single chart would be a heavier change than the
// chart itself. Handles the case where some history entries have a null
// lowest_price (a run that found no priced flights at all) by breaking
// the line at that point rather than plotting a fake zero.
function renderChart(history) {
  const width = 720;
  const height = 220;
  const padding = { top: 16, right: 16, bottom: 28, left: 56 };

  const priced = history.filter((h) => h.lowest_price != null);
  if (priced.length === 0) {
    const empty = document.createElement("p");
    empty.className = "price-note";
    empty.textContent = "No priced checks recorded yet.";
    return empty;
  }

  const prices = priced.map((h) => h.lowest_price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  // When every recorded price is identical, minPrice === maxPrice and a
  // 0-height range would divide by zero below; pad the range so the line
  // still renders (flat, centered) instead of collapsing to NaN.
  const priceRange = maxPrice - minPrice || 1;

  const xFor = (index) => {
    if (history.length === 1) {
      return padding.left + (width - padding.left - padding.right) / 2;
    }
    return padding.left + (index / (history.length - 1)) * (width - padding.left - padding.right);
  };
  const yFor = (price) =>
    padding.top + (1 - (price - minPrice) / priceRange) * (height - padding.top - padding.bottom);

  // Build one or more polyline point-strings, starting a new segment
  // whenever a null price breaks the sequence, so the SVG doesn't draw a
  // straight line across a gap where no price was recorded.
  const segments = [];
  let current = [];
  history.forEach((entry, index) => {
    if (entry.lowest_price == null) {
      if (current.length > 0) {
        segments.push(current);
        current = [];
      }
      return;
    }
    current.push(`${xFor(index)},${yFor(entry.lowest_price)}`);
  });
  if (current.length > 0) {
    segments.push(current);
  }

  const svgNs = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNs, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "history-chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Price history chart, ranging from ${minPrice} to ${maxPrice}`);

  const gridLine = (price) => {
    const y = yFor(price);
    const line = document.createElementNS(svgNs, "line");
    line.setAttribute("x1", padding.left);
    line.setAttribute("x2", width - padding.right);
    line.setAttribute("y1", y);
    line.setAttribute("y2", y);
    line.setAttribute("class", "chart-gridline");
    svg.appendChild(line);

    const label = document.createElementNS(svgNs, "text");
    label.setAttribute("x", padding.left - 8);
    label.setAttribute("y", y);
    label.setAttribute("class", "chart-axis-label");
    label.setAttribute("text-anchor", "end");
    label.setAttribute("dominant-baseline", "middle");
    label.textContent = Math.round(price);
    svg.appendChild(label);
  };
  gridLine(minPrice);
  gridLine(maxPrice);

  segments.forEach((points) => {
    const polyline = document.createElementNS(svgNs, "polyline");
    polyline.setAttribute("points", points.join(" "));
    polyline.setAttribute("class", "chart-line");
    svg.appendChild(polyline);
  });

  // First and last x-axis date labels only — the container this chart
  // sits in isn't wide enough to legibly fit one label per data point
  // once a route has more than a handful of checks.
  const firstPriced = priced[0];
  const lastPriced = priced[priced.length - 1];
  [
    { entry: firstPriced, index: history.indexOf(firstPriced), anchor: "start" },
    { entry: lastPriced, index: history.indexOf(lastPriced), anchor: "end" },
  ].forEach(({ entry, index, anchor }) => {
    const label = document.createElementNS(svgNs, "text");
    label.setAttribute("x", xFor(index));
    label.setAttribute("y", height - padding.bottom + 16);
    label.setAttribute("class", "chart-axis-label");
    label.setAttribute("text-anchor", anchor);
    label.textContent = formatShortDate(entry.checked_at);
    svg.appendChild(label);
  });

  return svg;
}

function renderHistoryTable(history) {
  const table = document.createElement("table");
  table.className = "history-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Checked at", "Lowest price", "Stops", "Matches"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  // Newest first — history.jsonl is append-only so the file itself is
  // oldest-first; reverse only for display, the chart above still reads
  // it oldest-first (left-to-right time order is what a trend line needs).
  [...history].reverse().forEach((entry) => {
    const row = document.createElement("tr");

    const checkedCell = document.createElement("td");
    checkedCell.textContent = formatTimestamp(entry.checked_at);
    row.appendChild(checkedCell);

    const priceCell = document.createElement("td");
    priceCell.textContent = entry.lowest_price != null ? entry.lowest_price : "—";
    row.appendChild(priceCell);

    const stopsCell = document.createElement("td");
    stopsCell.textContent = entry.lowest_price != null ? formatStops(entry.lowest_price_stops) : "—";
    row.appendChild(stopsCell);

    const matchCell = document.createElement("td");
    matchCell.textContent = entry.match_count != null ? entry.match_count : "—";
    row.appendChild(matchCell);

    tbody.appendChild(row);
  });
  table.appendChild(tbody);

  return table;
}

async function loadRouteDetail() {
  const emptyState = document.getElementById("detail-empty-state");
  const id = getRouteIdFromUrl();

  if (!id) {
    emptyState.textContent = "No route specified. Go back and pick one from the list.";
    return;
  }

  if (id.startsWith("flight-")) {
    await loadTrackedFlightDetail(id);
  } else {
    await loadRouteOnlyDetail(id);
  }
}

async function loadRouteOnlyDetail(routeId) {
  const detailSection = document.getElementById("route-detail");
  const emptyState = document.getElementById("detail-empty-state");

  try {
    const indexResponse = await fetch("data/index.json", { cache: "no-store" });
    if (!indexResponse.ok) {
      throw new Error(`Request failed with status ${indexResponse.status}`);
    }
    const routes = await indexResponse.json();
    const route = routes.find((r) => r.id === routeId);

    if (!route) {
      emptyState.textContent = "This route wasn't found. It may have been removed.";
      return;
    }

    renderRouteHeader(route);

    const historyResponse = await fetch(`data/${routeId}/history.jsonl`, { cache: "no-store" });
    if (!historyResponse.ok) {
      throw new Error(`Request failed with status ${historyResponse.status}`);
    }
    const historyText = await historyResponse.text();
    const history = parseJsonl(historyText);

    emptyState.remove();

    if (history.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No checks recorded yet for this route.";
      detailSection.appendChild(empty);
      return;
    }

    const chartWrap = document.createElement("div");
    chartWrap.className = "history-chart-wrap";
    chartWrap.appendChild(renderChart(history));
    detailSection.appendChild(chartWrap);

    detailSection.appendChild(renderHistoryTable(history));
  } catch (error) {
    emptyState.textContent = "Couldn't load this route's history.";
  }
}

async function loadTrackedFlightDetail(trackedId) {
  const detailSection = document.getElementById("route-detail");
  const emptyState = document.getElementById("detail-empty-state");

  try {
    const indexResponse = await fetch("data/tracked-index.json", { cache: "no-store" });
    if (!indexResponse.ok) {
      throw new Error(`Request failed with status ${indexResponse.status}`);
    }
    const trackedFlights = await indexResponse.json();
    const tracked = trackedFlights.find((t) => t.id === trackedId);

    if (!tracked) {
      emptyState.textContent = "This tracked flight wasn't found. It may have been removed.";
      return;
    }

    renderTrackedFlightHeader(tracked);

    const historyResponse = await fetch(`data/${trackedId}/history.jsonl`, { cache: "no-store" });
    if (!historyResponse.ok) {
      throw new Error(`Request failed with status ${historyResponse.status}`);
    }
    const historyText = await historyResponse.text();
    const rawHistory = parseJsonl(historyText);
    const history = rawHistory.map(normalizeTrackedHistoryEntry);

    emptyState.remove();

    if (history.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No checks recorded yet for this flight.";
      detailSection.appendChild(empty);
      return;
    }

    const chartWrap = document.createElement("div");
    chartWrap.className = "history-chart-wrap";
    chartWrap.appendChild(renderChart(history));
    detailSection.appendChild(chartWrap);

    detailSection.appendChild(renderHistoryTable(history));
  } catch (error) {
    emptyState.textContent = "Couldn't load this flight's history.";
  }
}

loadRouteDetail();
