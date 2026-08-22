"""Sends alert messages to Telegram via the plain Bot API (no extra deps)."""

import requests
import config as cfg


def send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": cfg.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[telegram] failed to send message: {e}")


def format_signal(instrument: str, granularity: str, event) -> str:
    arrow = "🟢 BUY" if event.kind == "BUY" else "🔴 SELL"
    return (
        f"<b>{arrow}</b>  {instrument}  ({granularity})\n"
        f"Time: {event.time.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Entry: <code>{event.price:.5f}</code>\n"
        f"TP: <code>{event.tp:.5f}</code>\n"
        f"SL: <code>{event.sl:.5f}</code>\n"
        f"Fib range: {event.fib_low:.5f} — {event.fib_high:.5f}"
    )
