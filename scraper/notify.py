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
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"Discord webhook failed: HTTP {exc.code} {exc.reason}")
        print(f"Response body: {body}")
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
