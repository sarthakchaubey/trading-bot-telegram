"""
Opening Range Breakout (ORB) Strategy Implementation.
"""
from dataclasses import dataclass
from datetime import time, timedelta
from typing import List, Optional
import pandas as pd
from strategy import Event

def run_strategy(df: pd.DataFrame, cfg) -> List[Event]:
    """
    Executes the Opening Range Breakout (ORB) strategy.
    
    Parameters:
    - df: DataFrame containing columns: time (tz-aware UTC), open, high, low, close, volume
    - cfg: Configuration mock containing parameters defined in strategies.json or config.py
    
    Returns:
    - List[Event]: Chronological list of BUY/SELL triggers.
    """
    df = df.copy()
    n = len(df)
    if n < 5:
        return []

    # ------------------------- INPUTS & DEFAULTS -------------------------
    # Retrieve parameters from cfg, using defaults matching the user's script
    start_hour = int(getattr(cfg, "START_HOUR", 9))
    start_minute = int(getattr(cfg, "START_MINUTE", 30))
    session_start = time(start_hour, start_minute)

    range_minutes = int(getattr(cfg, "RANGE_MINUTES", 30))

    end_hour = int(getattr(cfg, "END_HOUR", 16))
    end_minute = int(getattr(cfg, "END_MINUTE", 0))
    session_end = time(end_hour, end_minute)

    stop_pct_of_range = float(getattr(cfg, "STOP_PCT_OF_RANGE", 0.60))
    target_pct_of_range = float(getattr(cfg, "TARGET_PCT_OF_RANGE", 1.00))
    spread = float(getattr(cfg, "SPREAD", 0.20))
    tz = getattr(cfg, "TIME_ZONE", "America/New_York")

    # Ensure df["time"] is a datetime index or column localized to tz
    if "time" in df.columns:
        ts_col = "time"
    elif "datetime" in df.columns:
        ts_col = "datetime"
    else:
        ts_col = df.columns[0]

    df[ts_col] = pd.to_datetime(df[ts_col])
    if df[ts_col].dt.tz is None:
        df[ts_col] = df[ts_col].dt.tz_localize("UTC")
    
    # Store localized time for session window filtering
    df["local_time"] = df[ts_col].dt.tz_convert(tz)
    df["date"] = df["local_time"].dt.date

    events: List[Event] = []

    for day, day_df in df.groupby("date"):
        day_df = day_df.reset_index(drop=True)

        try:
            session_start_dt = pd.Timestamp.combine(day, session_start).tz_localize(tz, ambiguous='NaT', nonexistent='NaT')
            range_end_dt = session_start_dt + pd.Timedelta(minutes=range_minutes)
            session_end_dt = pd.Timestamp.combine(day, session_end).tz_localize(tz, ambiguous='NaT', nonexistent='NaT')
        except Exception:
            continue

        # Opening Range window
        ob_window = day_df[(day_df["local_time"] >= session_start_dt) &
                           (day_df["local_time"] < range_end_dt)]
        if ob_window.empty:
            continue

        ib_high = ob_window["high"].max()
        ib_low = ob_window["low"].min()
        ib_range = ib_high - ib_low
        if ib_range <= 0:
            continue

        # Rest of the session after range
        after_range = day_df[(day_df["local_time"] >= range_end_dt) &
                             (day_df["local_time"] <= session_end_dt)].reset_index(drop=True)

        in_trade = False
        direction = 0  # 1 for BUY (Long), -1 for SELL (Short)
        entry_price = stop_price = target_price = None

        for _, bar in after_range.iterrows():
            if not in_trade:
                # Trigger logic based on close crossing range bounds
                if bar["close"] > ib_high:
                    direction = 1
                    entry_price = bar["close"] + spread / 2
                    stop_price = entry_price - stop_pct_of_range * ib_range
                    target_price = entry_price + target_pct_of_range * ib_range
                    in_trade = True
                    events.append(Event(
                        kind="BUY",
                        time=bar[ts_col],  # Store original UTC timestamp
                        price=entry_price,
                        tp=target_price,
                        sl=stop_price,
                        fib_high=target_price,
                        fib_low=stop_price
                    ))
                elif bar["close"] < ib_low:
                    direction = -1
                    entry_price = bar["close"] - spread / 2
                    stop_price = entry_price + stop_pct_of_range * ib_range
                    target_price = entry_price - target_pct_of_range * ib_range
                    in_trade = True
                    events.append(Event(
                        kind="SELL",
                        time=bar[ts_col],  # Store original UTC timestamp
                        price=entry_price,
                        tp=target_price,
                        sl=stop_price,
                        fib_high=stop_price,
                        fib_low=target_price
                    ))
            else:
                # Check for trade exit (hits TP/SL or EOD)
                if direction == 1:
                    if bar["low"] <= stop_price or bar["high"] >= target_price or bar["local_time"] >= session_end_dt:
                        in_trade = False
                elif direction == -1:
                    if bar["high"] >= stop_price or bar["low"] <= target_price or bar["local_time"] >= session_end_dt:
                        in_trade = False

    return events
