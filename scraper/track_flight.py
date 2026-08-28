import json
import time
from pathlib import Path

FLIGHTS_DIR = Path("flights")
DATA_DIR = Path("data")


def load_active_tracked_flights():
    tracked = []
    for path in FLIGHTS_DIR.glob("*.json"):
        with open(path) as f:
            entry = json.load(f)
        if entry.get("active", True):
            tracked.append(entry)
    return tracked


def extract_hhmm(value):
    """Pull HH:MM out of a stored departure/arrival time value.

    scrape.py's parse_time_testid() reads this straight from a trip.com
    data-testid attribute, and its exact format (bare "HH:MM" vs a full
    "YYYY-MM-DD HH:MM:SS" datetime string) was never directly confirmed
    against a live page — see the DEPARTURE_TIME_SELECTOR comment in
    scrape.py. This mirrors notify.py's format_time(), which already
    handles both shapes, so the comparison below doesn't have to guess
    which one is actually in use.
    """
    if not value:
        return None
    return value.split(" ")[1][:5] if " " in value else value[:5]


def matches_tracked_flight_time(flight, tracked):
    if extract_hhmm(flight.get("departure_time")) != tracked["departure_time"]:
        return False
    if extract_hhmm(flight.get("arrival_time")) != tracked["arrival_time"]:
        return False
    return True


def find_tracked_flight(flights, tracked):
    """Return the first scraped flight matching a tracked flight's
    fingerprint (departure/arrival time only — airline isn't collected
    from the form), or None if this check's search results don't include
    a matching time at all.

    If two different flights share the exact same departure and arrival
    time (rare, but possible when two airlines happen to overlap), this
    returns whichever one appears first in trip.com's results list for
    this check — not a random pick, and not verified against airline
    identity. The matched flight's actual airline is still recorded in
    the saved result, so a same-time collision is visible after the fact
    even though it isn't prevented up front.

    A missing match is an expected, ordinary outcome (schedule changed,
    sold out, trip.com's result page just didn't surface it this time) —
    not an error condition — so callers should treat None as "not found
    this time", not as a failure to be raised or retried.
    """
    for flight in flights:
        if matches_tracked_flight_time(flight, tracked):
            return flight
    return None


def save_tracked_result(tracked_id, found_flight):
    flight_dir = DATA_DIR / tracked_id
    flight_dir.mkdir(parents=True, exist_ok=True)

    if found_flight is not None:
        entry = {
            "checked_at": int(time.time()),
            "found": True,
            "price": found_flight.get("price"),
            "stops": found_flight.get("stops"),
            "duration_minutes": found_flight.get("duration_minutes"),
            "airline": found_flight.get("airline"),
        }
    else:
        entry = {
            "checked_at": int(time.time()),
            "found": False,
            "price": None,
            "stops": None,
            "duration_minutes": None,
            "airline": None,
        }

    with open(flight_dir / "latest.json", "w") as f:
        json.dump(entry, f, indent=2)

    with open(flight_dir / "history.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def read_historical_lowest_price(tracked_id):
    # Same intent as scrape.py's route-level read_historical_lowest_price:
    # must be called before save_tracked_result() appends this run's own
    # entry, or this run's price would already be counted as "history" by
    # the time it's compared against itself.
    history_path = DATA_DIR / tracked_id / "history.jsonl"
    if not history_path.exists():
        return None

    lowest = None
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            price = entry.get("price")
            if price is None:
                continue
            if lowest is None or price < lowest:
                lowest = price
    return lowest
