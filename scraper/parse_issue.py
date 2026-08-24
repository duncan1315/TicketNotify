import json
import os
import re
import sys

FIELD_MAP = {
    "Origin airport code": "origin",
    "Destination airport code": "destination",
    "Trip type": "trip_type",
    "Departure date": "date",
    "Return date": "return_date",
    "Budget threshold": "budget",
    "Currency code": "currency",
    "Notification channel": "notify_channel",
    "Max flight duration — hours": "max_duration_hours",
    "Max flight duration — minutes": "max_duration_minutes_part",
}

REQUIRED_FIELDS = [
    "origin",
    "destination",
    "trip_type",
    "date",
    "budget",
    "currency",
    "notify_channel",
]


def normalize_trip_type(value):
    return value.strip().lower().replace(" ", "_")


def parse_optional_float(value):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return float(value)


def combine_duration_minutes(hours_raw, minutes_raw):
    """Combine the hours/minutes issue-form fields into total minutes.

    Either sub-field can be left blank (treated as 0), but leaving both
    blank means "no limit" (returns None), matching the old single-field
    behavior. Minutes must be 0-59; anything higher belongs in the hours
    field instead.
    """
    hours_raw = (hours_raw or "").strip()
    minutes_raw = (minutes_raw or "").strip()
    if not hours_raw and not minutes_raw:
        return None

    hours = float(hours_raw) if hours_raw else 0.0
    minutes = float(minutes_raw) if minutes_raw else 0.0
    return hours * 60 + minutes


def parse_body(body):
    sections = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
    data = {}
    for i in range(1, len(sections), 2):
        label = sections[i].strip()
        value = sections[i + 1].strip()
        if value == "_No response_":
            # GitHub Issue Forms renders this literal placeholder for optional
            # fields the user left blank, instead of omitting the section.
            value = ""
        key = FIELD_MAP.get(label)
        if key:
            data[key] = value
    return data


def build_route(issue_number, issue_title, parsed):
    return {
        "id": f"route-{issue_number}",
        "issue_number": int(issue_number),
        "issue_title": issue_title.strip() if issue_title else None,
        "origin": parsed["origin"].upper(),
        "destination": parsed["destination"].upper(),
        "trip_type": normalize_trip_type(parsed["trip_type"]),
        "date": parsed["date"],
        "return_date": parsed.get("return_date", "").strip() or None,
        "budget": float(parsed["budget"]),
        "currency": parsed["currency"].upper(),
        "notify_channel": parsed["notify_channel"].lower(),
        "max_duration_minutes": combine_duration_minutes(
            parsed.get("max_duration_hours"), parsed.get("max_duration_minutes_part")
        ),
        "active": True,
    }


def main():
    issue_number = os.environ["ISSUE_NUMBER"]
    issue_title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ["ISSUE_BODY"]
    parsed = parse_body(body)

    missing = [key for key in REQUIRED_FIELDS if key not in parsed]
    if missing:
        print(f"Missing fields: {missing}")
        sys.exit(1)

    trip_type = normalize_trip_type(parsed["trip_type"])
    if trip_type not in ("one_way", "round_trip"):
        print(f"Trip type must be 'One way' or 'Round trip', got: {parsed['trip_type']}")
        sys.exit(1)
    if trip_type == "round_trip" and not parsed.get("return_date", "").strip():
        print("Return date is required for round trip routes")
        sys.exit(1)

    hours_raw = parsed.get("max_duration_hours", "").strip()
    minutes_raw = parsed.get("max_duration_minutes_part", "").strip()
    for field_name, value in (("hours", hours_raw), ("minutes", minutes_raw)):
        if value:
            try:
                float(value)
            except ValueError:
                print(f"Max flight duration {field_name} must be a number, got: {value!r}")
                sys.exit(1)
    if minutes_raw and not (0 <= float(minutes_raw) <= 59):
        print(f"Max flight duration minutes must be between 0 and 59, got: {minutes_raw!r}")
        sys.exit(1)

    route = build_route(issue_number, issue_title, parsed)

    os.makedirs("routes", exist_ok=True)
    out_path = f"routes/{route['id']}.json"
    with open(out_path, "w") as f:
        json.dump(route, f, indent=2)
        f.write("\n")

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
