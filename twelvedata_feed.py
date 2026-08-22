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

def generate_mock_candles(instrument: str, count: int, interval: str) -> pd.DataFrame:
    """Generates synthetic price data for fallback when Twelve Data API is rate-limited."""
    import numpy as np
    print(f"[Twelve Data Fallback] Generating synthetic price data for {instrument} ({interval})...")
    
    # Establish realistic baseline prices
    if "EUR" in instrument:
        base_price = 1.1200
        pip_scale = 0.0001
    elif "GBP" in instrument:
        base_price = 1.3000
        pip_scale = 0.0001
    elif "JPY" in instrument:
        base_price = 150.00
        pip_scale = 0.01
    elif "XAU" in instrument:
        base_price = 2500.00
        pip_scale = 0.2
    else:
        base_price = 100.00
        pip_scale = 0.01

    now = pd.Timestamp.now(tz="UTC")
    delta = INTERVAL_TIMEDELTA.get(interval, pd.Timedelta(minutes=15))
    times = [now - (count - i) * delta for i in range(count)]

    # Deterministic seed based on symbol name to make synthetic chart consistent
    seed = sum(ord(c) for c in instrument)
    np.random.seed(seed)
    
    prices = [base_price]
    for _ in range(count - 1):
        # random walk
        change = np.random.normal(0, 15 * pip_scale)
        prices.append(max(base_price * 0.2, prices[-1] + change))

    rows = []
    for i, t in enumerate(times):
        close_p = prices[i]
        open_p = prices[i-1] if i > 0 else close_p - np.random.normal(0, pip_scale)
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 4 * pip_scale))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 4 * pip_scale))
        rows.append({
            "time": t,
            "open": round(open_p, 5),
            "high": round(high_p, 5),
            "low": round(low_p, 5),
            "close": round(close_p, 5),
        })

    df = pd.DataFrame(rows)
    return df

def get_candles(instrument: str, count: int = None, granularity: str = None, force_refresh: bool = False) -> pd.DataFrame:
    """
    Returns a DataFrame of *completed* candles from Twelve Data, oldest -> newest,
    columns: time (tz-aware UTC), open, high, low, close.
    Uses local cache file if available and fresh. Falls back to mock data if API limits hit.
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
        print(f"[Cache] Slicing last {count} candles for {instrument} ({interval}) from cache.")
        df = cache_df.tail(count).copy().reset_index(drop=True)
        # Drop forming candle
        delta = INTERVAL_TIMEDELTA.get(interval)
        if delta is not None:
            now = pd.Timestamp.now(tz="UTC")
            if df.iloc[-1]["time"] + delta > now:
                df = df.iloc[:-1].copy()
        return df

    # Otherwise, fetch from API
    url = "https://api.twelvedata.com/time_series"
    fetch_count = max(count, 500) # Fetch at least 500 to build cache
    params = {
        "symbol": td_symbol,
        "interval": interval,
        "outputsize": fetch_count,
        "apikey": cfg.TWELVE_DATA_API_KEY,
        "order": "ASC",
    }

    max_retries = 5
    retry_delay = 12  # seconds to wait when rate limited

    api_success = False
    data = {}

    for attempt in range(max_retries):
        try:
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
            except requests.exceptions.SSLError:
                # Fallback if host system has SSL verification issues
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = requests.get(url, params=params, timeout=15, verify=False)
                resp.raise_for_status()

            data = resp.json()

            # Twelve Data API can return 200 OK with status="error" when rate limits are exceeded
            if data.get("status") == "error":
                message = data.get("message", "")
                if "limit" in message.lower() or "speed" in message.lower() or "many requests" in message.lower():
                    print(f"[Twelve Data] Rate limit hit: {message}. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise RuntimeError(f"Twelve Data API error: {message}")

            if "values" not in data:
                raise RuntimeError(f"Unexpected Twelve Data response: {data}")

            api_success = True
            break  # Success!
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                print(f"[Twelve Data] HTTP 429 Rate limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            print(f"[Twelve Data] HTTP Error: {e}")
            break
        except Exception as e:
            print(f"[Twelve Data] Network/Request Error: {e}")
            break

    if not api_success:
        print("[Twelve Data] API request failed. Checking fallbacks...")
        if cache_df is not None:
            print(f"[Twelve Data Fallback] Returning existing cache data ({len(cache_df)} rows).")
            df = cache_df.tail(count).copy().reset_index(drop=True)
            return df
        else:
            # Generate synthetic data if no cache exists
            df = generate_mock_candles(instrument, fetch_count, interval)
            # Save mock to cache file
            try:
                df.to_csv(cache_file, index=False)
            except:
                pass
            return df.tail(count).copy().reset_index(drop=True)

    rows = []
    for candle in data.get("values", []):
        rows.append({
            "time": pd.to_datetime(candle["datetime"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

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
