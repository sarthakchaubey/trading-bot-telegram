"""Fetches closed candles from Twelve Data API as a pandas DataFrame."""

import os
import time
import requests
import pandas as pd
import config as cfg

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# Map intervals to pandas timedelta to detect and drop the incomplete (currently forming) candle
INTERVAL_TIMEDELTA = {
    "1min": pd.Timedelta(minutes=1),
    "5min": pd.Timedelta(minutes=5),
    "15min": pd.Timedelta(minutes=15),
    "30min": pd.Timedelta(minutes=30),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1day": pd.Timedelta(days=1),
}

def map_granularity(granularity: str) -> str:
    """Maps OANDA granularity style to Twelve Data interval style."""
    mapping = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "1h",
        "H4": "4h",
        "D": "1day",
        "D1": "1day",
    }
    return mapping.get(granularity, granularity)

def get_candles(instrument: str, count: int = None, granularity: str = None, force_refresh: bool = False, stop_event=None) -> pd.DataFrame:
    """
    Returns a DataFrame of *completed* authentic candles from Twelve Data, oldest -> newest,
    columns: time (tz-aware UTC), open, high, low, close, volume.
    Uses local cache file if available and fresh.
    """
    count = count or cfg.CANDLE_HISTORY_COUNT
    granularity = granularity or cfg.GRANULARITY
    interval = map_granularity(granularity)

    # Convert OANDA symbol format (e.g. EUR_USD) to Twelve Data format (e.g. EUR/USD)
    td_symbol = instrument.replace("_", "/")

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"{instrument}_{interval}.csv")

    # Read existing cache if available
    cache_df = None
    if os.path.exists(cache_file):
        try:
            cache_df = pd.read_csv(cache_file)
            cache_df["time"] = pd.to_datetime(cache_df["time"])
            if cache_df["time"].dt.tz is None:
                cache_df["time"] = cache_df["time"].dt.tz_localize("UTC")
            else:
                cache_df["time"] = cache_df["time"].dt.tz_convert("UTC")
            if "volume" not in cache_df.columns:
                cache_df["volume"] = 0.0
        except Exception as e:
            print(f"[Cache] Error reading cache file: {e}")

    # Determine if cache is valid and has enough rows
    cache_valid = False
    if not force_refresh and cache_df is not None and len(cache_df) >= count:
        file_age = time.time() - os.path.getmtime(cache_file)
        # 1 hour for backtesting (large count), 30 seconds for live polling
        max_age = 3600 if count >= 300 else 30
        if file_age < max_age:
            cache_valid = True

    if cache_valid and cache_df is not None:
        print(f"[Cache] Slicing last {count} authentic candles for {instrument} ({interval}) from cache.")
        df = cache_df.tail(count).copy().reset_index(drop=True)
        # Drop forming candle
        delta = INTERVAL_TIMEDELTA.get(interval)
        if delta is not None:
            now = pd.Timestamp.now(tz="UTC")
            if df.iloc[-1]["time"] + delta > now:
                df = df.iloc[:-1].copy()
        return df

    # Otherwise, fetch authentic real-time/historical candles from Twelve Data API
    url = "https://api.twelvedata.com/time_series"
    fetch_count = max(count, 500) # Fetch at least 500 to build cache
    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": fetch_count,
        "apikey": cfg.TWELVE_DATA_API_KEY,
        "order": "ASC",
    }

    max_retries = 3
    retry_delay = 10  # seconds to wait when rate limited

    api_success = False
    data = {}
    last_error_msg = ""

    for attempt in range(max_retries):
        try:
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
            except requests.exceptions.SSLError:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = requests.get(url, params=params, timeout=15, verify=False)
                resp.raise_for_status()

            data = resp.json()

            if data.get("status") == "error":
                message = data.get("message", "")
                last_error_msg = message
                if "limit" in message.lower() or "speed" in message.lower() or "many requests" in message.lower():
                    print(f"[Twelve Data] Rate limit: {message}. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    if stop_event and stop_event.wait(timeout=retry_delay):
                        break
                    if not stop_event:
                        time.sleep(retry_delay)
                    continue
                else:
                    raise RuntimeError(f"Twelve Data API error: {message}")

            if "values" not in data:
                raise RuntimeError(f"Unexpected Twelve Data response: {data}")

            api_success = True
            break
        except requests.exceptions.HTTPError as e:
            last_error_msg = str(e)
            if e.response is not None and e.response.status_code == 429:
                print(f"[Twelve Data] HTTP 429 Rate limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                if stop_event and stop_event.wait(timeout=retry_delay):
                    break
                if not stop_event:
                    time.sleep(retry_delay)
                continue
            print(f"[Twelve Data] HTTP Error: {e}")
            break
        except Exception as e:
            last_error_msg = str(e)
            print(f"[Twelve Data] Network/Request Error: {e}")
            break

    if not api_success:
        if cache_df is not None and len(cache_df) > 0:
            print(f"[Twelve Data] API failed ({last_error_msg}). Falling back to existing cached real data ({len(cache_df)} rows).")
            df = cache_df.tail(count).copy().reset_index(drop=True)
            return df
        raise RuntimeError(f"Twelve Data API error: {last_error_msg or 'Failed to fetch real market data'}")

    rows = []
    for candle in data.get("values", []):
        rows.append({
            "time": pd.to_datetime(candle["datetime"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle.get("volume", 0) or 0),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Sort chronologically (oldest -> newest)
    df = df.sort_values("time", ascending=True).reset_index(drop=True)

    # Localize time to UTC
    df["time"] = df["time"].dt.tz_localize("UTC")

    # Drop the last candle if it is still forming
    delta = INTERVAL_TIMEDELTA.get(interval)
    if delta is not None:
        now = pd.Timestamp.now(tz="UTC")
        if df.iloc[-1]["time"] + delta > now:
            # Drop the final incomplete candle
            df = df.iloc[:-1].copy()

    # Save to cache
    try:
        df.to_csv(cache_file, index=False)
    except Exception as e:
        print(f"[Cache] Error saving cache file: {e}")

    return df.tail(count).copy().reset_index(drop=True)
