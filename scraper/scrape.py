import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from ai_stops import infer_stops
from notify import send_notification
from track_flight import (
    load_active_tracked_flights,
    find_tracked_flight,
    save_tracked_result,
    read_historical_lowest_price as read_tracked_historical_lowest_price,
)

ROUTES_DIR = Path("routes")
DATA_DIR = Path("data")
DEBUG_DIR = Path(__file__).resolve().parent / "debug"

TRIP_DOMAIN = os.environ.get("TRIP_DOMAIN", "https://us.trip.com")
TRIP_LOCALE = os.environ.get("TRIP_LOCALE", "en-US")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}

STEALTH = Stealth()

# Card wrapper uses a per-card numeric suffix (u-flight-card-1, -2, ...),
# so match on the prefix instead of an exact value.
CARD_SELECTOR = "[data-testid^='u-flight-card-']"
PRICE_SELECTOR = "[data-testid='u_price_info']"
DURATION_SELECTOR = "[data-testid='flightInfoDuration']"
AIRLINE_SELECTOR = "[data-testid='flights-name']"

# Departure/arrival each have their own data-testid (flight-time-<datetime>),
# but the datetime is embedded in the attribute name itself rather than being
# a fixed value, so we can't select on it directly. The wrapper class is what
# reliably distinguishes the two, confirmed against a saved results page: a
# leg's departure time sits inside .is-departure-meridiem and its arrival
# time inside .is-arrival-meridiem. One-way only for now — a round-trip card
# here shows just the outbound leg (return-leg selection happens on a second
# page this scraper doesn't visit yet), so these selectors are not used to
# populate return-flight times.
DEPARTURE_TIME_SELECTOR = "[class*='is-departure-meridiem'] [data-testid^='flight-time-']"
ARRIVAL_TIME_SELECTOR = "[class*='is-arrival-meridiem'] [data-testid^='flight-time-']"

# No confirmed data-testid for stop count exists yet (couldn't verify against
# a live desktop page — see build_search_url's stoptype comment). Falls back
# to scanning the card's visible text for common English stop-count phrasing
# instead of a dedicated selector. Returns None rather than guessing when no
# match is found, so "unknown" is never silently recorded as "0 stops".
STOPS_TEXT_PATTERN = re.compile(
    r"\b(nonstop|direct)\b|\b(\d+)\s+stops?\b", re.IGNORECASE
)


def new_context(browser):
    return browser.new_context(
        user_agent=USER_AGENT,
        locale=TRIP_LOCALE,
        viewport=VIEWPORT,
        extra_http_headers={"Accept-Language": f"{TRIP_LOCALE},en;q=0.9"},
    )


def save_debug_snapshot(page, name):
    DEBUG_DIR.mkdir(exist_ok=True)
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
        (DEBUG_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
        print(f"Saved debug snapshot to {DEBUG_DIR}/{name}.png and .html")
    except Exception as exc:
        print(f"Could not save debug snapshot for {name}: {exc}")


def load_active_routes():
    routes = []
    for path in ROUTES_DIR.glob("*.json"):
        with open(path) as f:
            route = json.load(f)
        if route.get("active", True):
            routes.append(route)
    return routes


def build_search_url(route):
    params = f"?dcity={route['origin']}&acity={route['destination']}&ddate={route['date']}"

    if route.get("trip_type") == "round_trip" and route.get("return_date"):
        params += f"&rdate={route['return_date']}&triptype=rt"
    else:
        params += "&triptype=ow"

    params += f"&class=y&quantity=1&locale={TRIP_LOCALE}&curr={route['currency']}"

    # Direct-flights-only filter. Confirmed via manual testing on trip.com's
    # mobile site (tw.trip.com/m/flights/flightfirst/, using dcitycode/acitycode
    # params) that clicking "Direct" adds stoptype=0 to the URL. NOT yet
    # confirmed that the desktop showfarefirst endpoint (dcity/acity params,
    # used here) accepts the same stoptype param name/value — the two pages
    # may use different backend routes. If flight results still include
    # connecting flights after this change, check a debug snapshot
    # (scraper/debug/<route-id>.html) to see whether stoptype was honored,
    # and adjust the param name/value below accordingly.
    params += "&stoptype=0"

    return f"{TRIP_DOMAIN}/flights/showfarefirst{params}"


def wait_for_prices_to_settle(page, poll_ms=1000, max_wait_ms=15000, stable_polls=2):
    stable = 0
    last_count = -1
    waited = 0
    while waited < max_wait_ms:
        page.wait_for_timeout(poll_ms)
        waited += poll_ms
        count = len(page.query_selector_all(PRICE_SELECTOR))
        if count == last_count:
            stable += 1
            if stable >= stable_polls:
                return
        else:
            stable = 0
        last_count = count


def scroll_to_load_more_cards(page, scroll_count=3, wait_ms=1500):
    # trip.com renders some flights only after scrolling — confirmed
    # directly against a live page, not assumed. This scrolls a fixed
    # number of times rather than looping "until no new cards appear":
    # trip.com's actual scroll-triggered loading behavior (infinite
    # scroll vs a fixed page of results vs a "load more" click target)
    # has never been observed here, so a fixed count with a hard ceiling
    # was chosen over an open-ended loop that could stall or spin
    # forever against behavior this code can't anticipate. If flights
    # further down the results are still being missed, raising
    # scroll_count is the first thing to try — see extract_flights.
    for _ in range(scroll_count):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(wait_ms)
        wait_for_prices_to_settle(page)


def extract_flights(page):
    # Selectors confirmed against a real trip.com debug snapshot
    # (see routes/route-3 debug HTML). Cards render as shimmer
    # placeholders first and fill in with real data asynchronously,
    # so wait_for_prices_to_settle lets more of them load before we
    # read the page; placeholder cards without a price are skipped.
    page.wait_for_selector(PRICE_SELECTOR, timeout=30000)
    wait_for_prices_to_settle(page)
    scroll_to_load_more_cards(page)
    cards = page.query_selector_all(CARD_SELECTOR)

    flights = []
    card_texts = []
    for card in cards:
        price_el = card.query_selector(PRICE_SELECTOR)
        duration_el = card.query_selector(DURATION_SELECTOR)
        airline_el = card.query_selector(AIRLINE_SELECTOR)
        departure_el = card.query_selector(DEPARTURE_TIME_SELECTOR)
        arrival_el = card.query_selector(ARRIVAL_TIME_SELECTOR)

        if not price_el or not duration_el:
            continue

        card_text = card.inner_text()
        flights.append({
            "price": parse_price(price_el.inner_text()),
            "duration_minutes": parse_duration(duration_el.inner_text()),
            "airline": airline_el.inner_text() if airline_el else "unknown",
            "stops": parse_stops(card_text),
            "departure_time": parse_time_testid(departure_el) if departure_el else None,
            "arrival_time": parse_time_testid(arrival_el) if arrival_el else None,
            "_raw_price_text": price_el.inner_text(),
            "_raw_card_text": card_text,
        })
        card_texts.append(card_text)

    return fill_unknown_stops(flights, card_texts)


def fill_unknown_stops(flights, card_texts):
    # Only cards the regex above couldn't read go to the AI fallback, and
    # infer_stops only ever sees that subset - not their position in the
    # full flights list - so its result dict is keyed by position within
    # `unresolved`, not by index into `flights`; position/flight_index
    # below map one back to the other.
    unresolved = [i for i, flight in enumerate(flights) if flight["stops"] is None]
    if not unresolved:
        return flights

    ai_results = infer_stops([card_texts[i] for i in unresolved])
    for position, flight_index in enumerate(unresolved):
        stops = ai_results.get(position)
        if stops is not None:
            flights[flight_index]["stops"] = stops

    return flights


def parse_price(text):
    digits = "".join(ch for ch in text if ch.isdigit())
    return float(digits) if digits else None


def parse_duration(text):
    hours = 0
    minutes = 0
    if "h" in text:
        hours_part, text = text.split("h", 1)
        hours = int(hours_part.strip())
    if "m" in text:
        minutes = int(text.replace("m", "").strip())
    return hours * 60 + minutes


def parse_time_testid(el):
    testid = el.get_attribute("data-testid") or ""
    return testid.removeprefix("flight-time-") or None


def parse_stops(card_text):
    match = STOPS_TEXT_PATTERN.search(card_text)
    if not match:
        return None
    if match.group(1):  # "nonstop" or "direct"
        return 0
    return int(match.group(2))  # "N stops"


def scrape_route(context, route):
    page = context.new_page()
    try:
        page.goto(build_search_url(route), timeout=60000)
        flights = extract_flights(page)
    except Exception as exc:
        print(f"Failed to scrape {route['id']}: {exc}")
        save_debug_snapshot(page, route["id"])
        flights = []
    finally:
        page.close()
    return flights


def evaluate_matches(route, flights):
    max_duration = route.get("max_duration_minutes")
    matches = []
    for flight in flights:
        if flight["price"] is None:
            continue
        if flight["price"] > route["budget"]:
            continue
        if max_duration is not None and flight["duration_minutes"] > max_duration:
            continue
        matches.append(flight)
    return matches


def read_historical_lowest_price(route_id):
    # Called BEFORE save_results() appends this run's entry to
    # history.jsonl — otherwise this run's own price would already be in
    # "history" by the time we compare against it, and a genuinely new low
    # would never register as new (it would just be tied with itself).
    history_path = DATA_DIR / route_id / "history.jsonl"
    if not history_path.exists():
        return None

    lowest = None
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            price = entry.get("lowest_price")
            if price is None:
                continue
            if lowest is None or price < lowest:
                lowest = price
    return lowest


def mark_new_lows(matches, historical_lowest_price):
    # historical_lowest_price is None when history.jsonl doesn't exist yet
    # (first-ever run for this route) or every past entry had a null price
    # (every past scrape failed to find any flight). Either way there's no
    # prior price to beat, so nothing can be flagged "new low" — a first
    # sighting isn't a record broken, it's just the first data point.
    if historical_lowest_price is None:
        return
    for flight in matches:
        flight["is_new_low"] = flight["price"] < historical_lowest_price


def save_results(route, flights, matches):
    route_dir = DATA_DIR / route["id"]
    route_dir.mkdir(parents=True, exist_ok=True)

    priced_flights = [f for f in flights if f["price"] is not None]
    cheapest = min(priced_flights, key=lambda f: f["price"]) if priced_flights else None

    latest = {
        "checked_at": int(time.time()),
        "lowest_price": cheapest["price"] if cheapest else None,
        "lowest_price_stops": cheapest["stops"] if cheapest else None,
        "lowest_price_duration_minutes": cheapest["duration_minutes"] if cheapest else None,
        "flight_count": len(flights),
        "match_count": len(matches),
    }

    with open(route_dir / "latest.json", "w") as f:
        json.dump(latest, f, indent=2)

    with open(route_dir / "history.jsonl", "a") as f:
        f.write(json.dumps(latest) + "\n")

    return latest


def build_index(route_summaries):
    with open(DATA_DIR / "index.json", "w") as f:
        json.dump(route_summaries, f, indent=2)


def build_tracked_index(tracked_summaries):
    with open(DATA_DIR / "tracked-index.json", "w") as f:
        json.dump(tracked_summaries, f, indent=2)


def scrape_tracked_flight(context, tracked):
    # Reuses scrape_route()'s page-load-and-extract logic by handing it a
    # route-shaped dict, rather than duplicating that logic here. A
    # tracked flight has no return date, budget, or duration limit of its
    # own — those are route-level filtering concepts that don't apply to
    # "find this one specific flight" — so this always searches one-way.
    pseudo_route = {
        "id": tracked["id"],
        "origin": tracked["origin"],
        "destination": tracked["destination"],
        "date": tracked["date"],
        "trip_type": "one_way",
        "currency": tracked["currency"],
    }
    return scrape_route(context, pseudo_route)


def check_tracked_flight(context, tracked):
    flights = scrape_tracked_flight(context, tracked)
    found_flight = find_tracked_flight(flights, tracked)

    historical_lowest_price = read_tracked_historical_lowest_price(tracked["id"])
    is_new_low = (
        found_flight is not None
        and historical_lowest_price is not None
        and found_flight["price"] < historical_lowest_price
    )

    entry = save_tracked_result(tracked["id"], found_flight)

    under_budget = found_flight is not None and found_flight["price"] <= tracked["budget"]

    if found_flight is None:
        print(f"{tracked['id']}: not found in this check's search results")
    elif not under_budget:
        print(f"{tracked['id']}: found, price {entry['price']} exceeds budget {tracked['budget']}, no notification")
        print(f"{tracked['id']}: DEBUG raw price text: {found_flight.get('_raw_price_text')!r}")
        print(f"{tracked['id']}: DEBUG full card text: {found_flight.get('_raw_card_text')!r}")
    else:
        print(f"{tracked['id']}: found, price {entry['price']}" + (" (NEW LOW)" if is_new_low else ""))
        print(f"{tracked['id']}: DEBUG raw price text: {found_flight.get('_raw_price_text')!r}")
        print(f"{tracked['id']}: DEBUG full card text: {found_flight.get('_raw_card_text')!r}")

    if under_budget:
        found_flight = {**found_flight, "is_new_low": is_new_low}
        send_notification(tracked, [found_flight])

    return {**tracked, "latest": entry}


def main():
    routes = load_active_routes()
    tracked_flights = load_active_tracked_flights()
    if not routes and not tracked_flights:
        print("No active routes or tracked flights found")
        return

    summaries = []
    with STEALTH.use_sync(sync_playwright()) as p:
        browser = p.chromium.launch()
        context = new_context(browser)
        for route in routes:
            flights = scrape_route(context, route)
            matches = evaluate_matches(route, flights)

            historical_lowest_price = read_historical_lowest_price(route["id"])
            mark_new_lows(matches, historical_lowest_price)

            latest = save_results(route, flights, matches)
            summaries.append({**route, "latest": latest})

            print(f"{route['id']}: {len(flights)} flight(s) seen, {len(matches)} match(es), lowest price {latest['lowest_price']}")

            if matches:
                send_notification(route, matches)

        tracked_summaries = []
        for tracked in tracked_flights:
            tracked_summaries.append(check_tracked_flight(context, tracked))

        context.close()
        browser.close()

    build_index(summaries)
    build_tracked_index(tracked_summaries)


if __name__ == "__main__":
    main()
