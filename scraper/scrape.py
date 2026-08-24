import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from notify import send_notification

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


def extract_flights(page):
    # Selectors confirmed against a real trip.com debug snapshot
    # (see routes/route-3 debug HTML). Cards render as shimmer
    # placeholders first and fill in with real data asynchronously,
    # so wait_for_prices_to_settle lets more of them load before we
    # read the page; placeholder cards without a price are skipped.
    page.wait_for_selector(PRICE_SELECTOR, timeout=30000)
    wait_for_prices_to_settle(page)
    cards = page.query_selector_all(CARD_SELECTOR)

    flights = []
    for card in cards:
        price_el = card.query_selector(PRICE_SELECTOR)
        duration_el = card.query_selector(DURATION_SELECTOR)
        airline_el = card.query_selector(AIRLINE_SELECTOR)

        if not price_el or not duration_el:
            continue

        flights.append({
            "price": parse_price(price_el.inner_text()),
            "duration_minutes": parse_duration(duration_el.inner_text()),
            "airline": airline_el.inner_text() if airline_el else "unknown",
            "stops": parse_stops(card.inner_text()),
        })
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
    matches = []
    for flight in flights:
        if flight["price"] is None:
            continue
        if flight["price"] <= route["budget"]:
            matches.append(flight)
    return matches


def save_results(route, flights, matches):
    route_dir = DATA_DIR / route["id"]
    route_dir.mkdir(parents=True, exist_ok=True)

    prices = [f["price"] for f in flights if f["price"] is not None]
    latest = {
        "checked_at": int(time.time()),
        "lowest_price": min(prices) if prices else None,
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


def main():
    routes = load_active_routes()
    if not routes:
        print("No active routes found")
        return

    summaries = []
    with STEALTH.use_sync(sync_playwright()) as p:
        browser = p.chromium.launch()
        context = new_context(browser)
        for route in routes:
            flights = scrape_route(context, route)
            matches = evaluate_matches(route, flights)
            latest = save_results(route, flights, matches)
            summaries.append({**route, "latest": latest})

            if matches:
                send_notification(route, matches)
        context.close()
        browser.close()

    build_index(summaries)


if __name__ == "__main__":
    main()
