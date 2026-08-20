import json
import os
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
    # Only searches route["earliest_date"]; scanning the full date range
    # is a possible enhancement, see README.
    params = f"?dcity={route['origin']}&acity={route['destination']}&ddate={route['earliest_date']}"

    if route.get("trip_type") == "round_trip" and route.get("return_date"):
        params += f"&rdate={route['return_date']}&triptype=rt"
    else:
        params += "&triptype=ow"

    params += f"&class=y&quantity=1&locale={TRIP_LOCALE}&curr={route['currency']}"
    return f"{TRIP_DOMAIN}/flights/showfarefirst{params}"


def extract_flights(page):
    # Selectors below are a starting point and likely need to be verified
    # against the live page in a browser, since trip.com's markup can
    # change and was not verified against a running instance here.
    page.wait_for_selector("[data-testid='flight-item']", timeout=30000)
    cards = page.query_selector_all("[data-testid='flight-item']")

    flights = []
    for card in cards:
        price_el = card.query_selector("[data-testid='price']")
        duration_el = card.query_selector("[data-testid='duration']")
        airline_el = card.query_selector("[data-testid='airline-name']")

        if not price_el or not duration_el:
            continue

        flights.append({
            "price": parse_price(price_el.inner_text()),
            "duration_minutes": parse_duration(duration_el.inner_text()),
            "airline": airline_el.inner_text() if airline_el else "unknown",
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
        if flight["price"] <= route["budget"] and flight["duration_minutes"] <= route["max_duration_minutes"]:
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
