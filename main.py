"""
Swing Fibonacci Telegram Alert Bot.

Polls OANDA for closed candles on each configured instrument, replays the
Fibonacci swing strategy over the fetched history, and sends a Telegram
message for any signal that is newer than the last one already alerted.

Run:
    python main.py
"""

import time
import traceback
from datetime import datetime, timezone

import config as cfg
import twelvedata_feed
import telegram_notifier
from strategy import run_strategy

# Tracks the timestamp of the last alerted event per instrument, so we never
# send the same signal twice across polling cycles / restarts within a run.
_last_alert_time = {instrument: None for instrument in cfg.INSTRUMENTS}


def check_instrument(instrument: str) -> None:
    df = twelvedata_feed.get_candles(instrument)
    if df.empty:
        print(f"[{instrument}] no candle data returned")
        return

    # Let the strategy know which instrument it's running so it can apply
    # the per-instrument MIN_FIB_RANGE override.
    cfg._current_instrument = instrument

    events = run_strategy(df, cfg)
    if not events:
        return

    last_seen = _last_alert_time[instrument]
    new_events = [e for e in events if last_seen is None or e.time > last_seen]

    for event in new_events:
        text = telegram_notifier.format_signal(instrument, cfg.GRANULARITY, event)
        telegram_notifier.send_message(text)
        print(f"[{instrument}] sent alert: {event.kind} @ {event.price} ({event.time})")

    if new_events:
        _last_alert_time[instrument] = new_events[-1].time


def main() -> None:
    print(f"Starting Swing Fib Telegram bot — {cfg.INSTRUMENTS} @ {cfg.GRANULARITY}")
    print(f"Polling every {cfg.POLL_SECONDS}s. Ctrl+C to stop.")

    # Prime last_alert_time with the most recent existing signal so the bot
    # doesn't blast out every historical signal the moment it starts.
    for idx, instrument in enumerate(cfg.INSTRUMENTS):
        if idx > 0:
            time.sleep(10)  # Staggered requests to avoid rate limits
        try:
            df = twelvedata_feed.get_candles(instrument)
            cfg._current_instrument = instrument
            events = run_strategy(df, cfg)
            if events:
                _last_alert_time[instrument] = events[-1].time
                print(f"[{instrument}] primed, last known signal at {events[-1].time}")
        except Exception:
            traceback.print_exc()

    # Send a startup notification to Telegram
    try:
        telegram_notifier.send_message(
            f"🔔 <b>Bot 04 is online!</b>\n"
            f"Monitoring: <code>{cfg.INSTRUMENTS}</code>\n"
            f"Timeframe: <code>{cfg.GRANULARITY}</code>"
        )
    except Exception as e:
        print(f"[telegram] failed to send startup message: {e}")

    while True:
        for idx, instrument in enumerate(cfg.INSTRUMENTS):
            if idx > 0:
                time.sleep(10)  # Staggered requests to avoid rate limits
            try:
                check_instrument(instrument)
            except Exception:
                print(f"[{instrument}] error during check:")
                traceback.print_exc()
        time.sleep(cfg.POLL_SECONDS)


if __name__ == "__main__":
    main()
