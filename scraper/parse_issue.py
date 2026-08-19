import json
import os
import re
import sys

FIELD_MAP = {
    "Origin airport code": "origin",
    "Destination airport code": "destination",
    "Earliest departure date": "earliest_date",
    "Latest departure date": "latest_date",
    "Budget threshold": "budget",
    "Currency code": "currency",
    "Max flight duration in minutes": "max_duration_minutes",
    "Notification channel": "notify_channel",
}

REQUIRED_FIELDS = list(FIELD_MAP.values())


def parse_body(body):
    sections = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
    data = {}
    for i in range(1, len(sections), 2):
        label = sections[i].strip()
        value = sections[i + 1].strip()
        key = FIELD_MAP.get(label)
        if key:
            data[key] = value
    return data


def build_route(issue_number, parsed):
    return {
        "id": f"route-{issue_number}",
        "issue_number": int(issue_number),
        "origin": parsed["origin"].upper(),
        "destination": parsed["destination"].upper(),
        "earliest_date": parsed["earliest_date"],
        "latest_date": parsed["latest_date"],
        "budget": float(parsed["budget"]),
        "currency": parsed["currency"].upper(),
        "max_duration_minutes": int(parsed["max_duration_minutes"]),
        "notify_channel": parsed["notify_channel"].lower(),
        "active": True,
    }


def main():
    issue_number = os.environ["ISSUE_NUMBER"]
    body = os.environ["ISSUE_BODY"]
    parsed = parse_body(body)

    missing = [key for key in REQUIRED_FIELDS if key not in parsed]
    if missing:
        print(f"Missing fields: {missing}")
        sys.exit(1)

    route = build_route(issue_number, parsed)

    os.makedirs("routes", exist_ok=True)
    out_path = f"routes/{route['id']}.json"
    with open(out_path, "w") as f:
        json.dump(route, f, indent=2)
        f.write("\n")

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
