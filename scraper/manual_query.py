import os

from playwright.sync_api import sync_playwright

from notify import send_notification
from scrape import (
    STEALTH,
    build_search_url,
    evaluate_matches,
    extract_flights,
    new_context,
    save_debug_snapshot,
)

RESULT_FILE = "manual_query_result.txt"


def parse_command(body):
    parts = body.strip().split()
    if not parts or parts[0] != "/check":
        return None

    parts = parts[1:]
    if len(parts) < 3:
        return None

    origin, destination, date = parts[0], parts[1], parts[2]
    budget = float(parts[3]) if len(parts) > 3 else 999999
    max_duration = int(parts[4]) if len(parts) > 4 else 1440

    return build_route(origin, destination, date, budget, max_duration)


def build_route(origin, destination, date, budget, max_duration):
    return {
        "id": "manual",
        "origin": origin.upper(),
        "destination": destination.upper(),
        "earliest_date": date,
        "budget": budget,
        "currency": os.environ.get("INPUT_CURRENCY", "USD"),
        "max_duration_minutes": max_duration,
        "notify_channel": "discord",
    }


def build_route_from_env():
    if os.environ.get("EVENT_NAME") == "issue_comment":
        return parse_command(os.environ.get("COMMENT_BODY", ""))

    return build_route(
        os.environ["INPUT_ORIGIN"],
        os.environ["INPUT_DESTINATION"],
        os.environ["INPUT_DATE"],
        float(os.environ.get("INPUT_BUDGET", "999999")),
        int(os.environ.get("INPUT_MAX_DURATION", "1440")),
    )


def write_result(text):
    with open(RESULT_FILE, "w") as f:
        f.write(text)


def main():
    route = build_route_from_env()
    if route is None:
        write_result("Could not parse the query. Use: /check ORIGIN DESTINATION DATE [BUDGET] [MAX_DURATION_MINUTES]")
        return

    with STEALTH.use_sync(sync_playwright()) as p:
        browser = p.chromium.launch()
        context = new_context(browser)
        page = context.new_page()
        try:
            page.goto(build_search_url(route), timeout=60000)
            flights = extract_flights(page)
        except Exception as exc:
            print(f"Manual query failed: {exc}")
            save_debug_snapshot(page, "manual")
            flights = []
        context.close()
        browser.close()

    matches = evaluate_matches(route, flights)

    lines = [f"Query: {route['origin']} to {route['destination']} on {route['earliest_date']}"]
    prices = [f["price"] for f in flights if f["price"] is not None]
    if prices:
        lines.append(f"Lowest price found: {min(prices)} {route['currency']}")
        lines.append(
            f"{len(matches)} flight(s) matched budget {route['budget']} "
            f"and max duration {route['max_duration_minutes']} min"
        )
    else:
        lines.append("No flights found. Check the run's debug-snapshot artifact for a screenshot of what the page showed.")

    write_result("\n".join(lines))

    if matches:
        send_notification(route, matches)


if __name__ == "__main__":
    main()
