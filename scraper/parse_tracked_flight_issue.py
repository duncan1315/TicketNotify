import json
import os
import re
import sys

FIELD_MAP = {
    "Origin airport code": "origin",
    "Destination airport code": "destination",
    "Departure date": "date",
    "Departure time": "departure_time",
    "Arrival time": "arrival_time",
    "Currency code": "currency",
    "Notification channel": "notify_channel",
}

REQUIRED_FIELDS = [
    "origin",
    "destination",
    "date",
    "departure_time",
    "arrival_time",
    "currency",
    "notify_channel",
]

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_body(body):
    # Same section-splitting approach as parse_issue.py, kept identical on
    # purpose rather than importing it, since the two issue forms have
    # unrelated field sets and diverging independently is safer than
    # sharing a helper that would need to know about both.
    sections = re.split(r"^### (.+)$", body, flags=re.MULTILINE)
    data = {}
    for i in range(1, len(sections), 2):
        label = sections[i].strip()
        value = sections[i + 1].strip()
        if value == "_No response_":
            value = ""
        key = FIELD_MAP.get(label)
        if key:
            data[key] = value
    return data


def build_tracked_flight(issue_number, issue_title, parsed):
    return {
        "id": f"flight-{issue_number}",
        "issue_number": int(issue_number),
        "issue_title": issue_title.strip() if issue_title else None,
        "origin": parsed["origin"].upper(),
        "destination": parsed["destination"].upper(),
        "date": parsed["date"],
        "departure_time": parsed["departure_time"].strip(),
        "arrival_time": parsed["arrival_time"].strip(),
        "currency": parsed["currency"].upper(),
        "notify_channel": parsed["notify_channel"].lower(),
        "active": True,
    }


def main():
    issue_number = os.environ["ISSUE_NUMBER"]
    issue_title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ["ISSUE_BODY"]
    parsed = parse_body(body)

    missing = [key for key in REQUIRED_FIELDS if key not in parsed or not parsed[key].strip()]
    if missing:
        print(f"Missing fields: {missing}")
        sys.exit(1)

    for field_name in ("departure_time", "arrival_time"):
        value = parsed[field_name].strip()
        if not TIME_PATTERN.match(value):
            print(f"{field_name} must be 24-hour HH:MM (e.g. 08:30), got: {value!r}")
            sys.exit(1)

    tracked = build_tracked_flight(issue_number, issue_title, parsed)

    os.makedirs("flights", exist_ok=True)
    out_path = f"flights/{tracked['id']}.json"
    with open(out_path, "w") as f:
        json.dump(tracked, f, indent=2)
        f.write("\n")

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
