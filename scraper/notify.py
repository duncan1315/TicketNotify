import json
import os
import urllib.request


def send_notification(route, matches):
    channel = route.get("notify_channel", "discord")
    if channel == "discord":
        send_discord(route, matches)
    elif channel == "telegram":
        send_telegram(route, matches)
    else:
        print(f"Unknown notify_channel: {channel}")


def send_discord(route, matches):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL is not set, skipping notification")
        return

    payload = json.dumps({"content": build_message(route, matches)}).encode()
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request)


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
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request)


def build_message(route, matches):
    lines = [
        f"Price alert: {route['origin']} to {route['destination']}",
        f"Budget: {route['budget']} {route['currency']}",
        "",
    ]
    lines.extend(format_match(m) for m in matches)
    return "\n".join(lines)


def format_match(flight):
    return f"{flight['airline']} - {flight['price']} ({flight['duration_minutes']} min)"
