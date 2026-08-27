import json
import os
import urllib.error
import urllib.request

# Discord sits behind Cloudflare, which blocks requests with no/suspicious
# User-Agent (Cloudflare error 1010). urllib's default UA ("Python-urllib/3.x")
# gets flagged, so send a normal browser-looking one instead.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def send_notification(route, matches):
    channel = route.get("notify_channel", "discord")
    if channel == "discord":
        send_discord(route, matches)
    elif channel == "telegram":
        send_telegram(route, matches)
    else:
        print(f"Unknown notify_channel: {channel}")


def send_discord(route, matches):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL is not set, skipping notification")
        return
    if not webhook_url.startswith("https://discord.com/api/webhooks/") and not webhook_url.startswith("https://discordapp.com/api/webhooks/"):
        print(f"DISCORD_WEBHOOK_URL does not look like a valid webhook URL (got: {webhook_url[:40]}...)")
        return

    payload = json.dumps({"content": build_message(route, matches)}).encode()
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        urllib.request.urlopen(request)
        print(f"Discord notification sent for {route.get('id', route.get('origin'))} ({len(matches)} match(es))")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"Discord webhook failed: HTTP {exc.code} {exc.reason}")
        print(f"Response body: {body}")
        raise
    except urllib.error.URLError as exc:
        print(f"Discord webhook failed: connection error: {exc.reason}")
        raise


def send_telegram(route, matches):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set, skipping notification")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": build_message(route, matches)}).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    urllib.request.urlopen(request)


def build_title(route):
    # Falls back to origin → destination when there's no origin/destination
    # concept to add on top of — currently always present, but kept as a
    # guard since manual_query.py builds routes without issue_title.
    name = route.get("issue_title") or f"{route['origin']} → {route['destination']}"
    return f"✈️ {name}"


def build_subtitle(route):
    dates = route.get("date", "")
    return_date = route.get("return_date")
    if return_date:
        dates = f"{dates} → {return_date}"

    return f"💰{route['budget']} {route['currency']} | {dates}"


def build_message(route, matches):
    lines = [
        "———————————————",
        build_title(route),
        build_subtitle(route),
        "",
    ]
    lines.extend(format_match(m, route["currency"]) for m in matches)
    lines.append("———————————————")
    return "\n".join(lines)


def format_time(value):
    if not value:
        return "?"
    # value looks like "2026-09-02 06:45:00"; only HH:MM is useful here since
    # the route's date is already shown in the message header.
    return value.split(" ")[1][:5] if " " in value else value


def format_duration(total_minutes):
    if total_minutes is None:
        return "? duration"
    hours, minutes = divmod(int(total_minutes), 60)
    if hours and minutes:
        return f"{hours}h{minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def format_match(flight, currency):
    stops = flight.get("stops")
    if stops is None:
        stops_label = "stops unknown"
    elif stops == 0:
        stops_label = "direct"
    else:
        stops_label = f"{stops} stop{'s' if stops != 1 else ''}"

    departure = format_time(flight.get("departure_time"))
    arrival = format_time(flight.get("arrival_time"))
    duration = format_duration(flight.get("duration_minutes"))

    return (
        f"• {flight['airline']} — {flight['price']} {currency}\n"
        f"  ({departure} → {arrival}, {duration}, {stops_label})"
    )
