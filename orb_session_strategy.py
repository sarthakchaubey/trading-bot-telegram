"""
ORB + Displacement + Session Liquidity Strategy
=================================================

Step 1 (Displacement ORB):
  - Mark the NY-open opening range (default 09:30-09:45 ET, 15m).
  - On 5m candles, detect an impulsive displacement leg breaking that range
    (consecutive same-direction candles with bodies well above average range).
  - Inside the leg, locate the entry zone: a Fair Value Gap (3-candle imbalance)
    or, failing that, the demand/supply candle (last opposite-colored candle
    right before the impulsive push).
  - Wait for price to retrace into the zone; require an engulfing candle at
    the zone as entry confirmation.

Step 2 (Session bias):
  - Asian session range = a liquidity pool (a high and a low).
  - If London sweeps one side of that range (wicks through and closes back
    inside), the model expects NY to reverse toward the *other* side.
  - A trade is only taken when the Step 1 displacement direction agrees with
    this Step 2 bias. No sweep / no agreement -> no trade that day.

This is a backtester, not a signal bot: feed it historical 1m (or 5m) OHLCV
and it produces a trade log + summary stats so you can see whether the rules
actually have an edge before trading them. Every "strong candle" / "engulfing"
/ "sweep" rule below is a concrete, tunable threshold in Config -- the source
video describes these qualitatively, this file operationalizes them. Re-tune
before trusting the output.

Usage:
    python orb_session_strategy.py --csv path/to/1min_ohlcv.csv
    python orb_session_strategy.py                     # runs on generated sample data
    python orb_session_strategy.py --csv data.csv --rr 1.5 --atr-mult 1.2

CSV format expected: a timestamp/datetime column + open, high, low, close, volume.
Timestamps are parsed, assumed UTC if naive, then converted to America/New_York.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import time, timedelta

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

@dataclass
class Config:
    tz: str = "America/New_York"

    # Session windows, local ET. Asian session starts the evening before.
    asian_start: time = time(20, 0)
    asian_end: time = time(0, 0)
    london_start: time = time(2, 0)
    london_end: time = time(5, 0)

    ny_open: time = time(9, 30)
    or_minutes: int = 15                    # opening range length
    displacement_window_minutes: int = 90   # how long after OR to look for displacement
    displacement_min_candles: int = 2       # consecutive same-direction 5m candles required
    displacement_atr_mult: float = 1.3      # candle body must exceed atr * this to count as "strong"
    atr_period: int = 14                    # ATR lookback (on 5m candles)

    retrace_window_minutes: int = 120       # how long to wait for price to return to the zone
    zone_buffer_atr_mult: float = 0.1       # small buffer added beyond zone for stop placement

    risk_reward: float = 2.0                # target = risk * this
    sweep_min_atr_mult: float = 0.05        # min penetration beyond asian range to count as a sweep
    max_trades_per_day: int = 1

    session_bias_required: bool = True      # if False, ignore Step 2 and trade Step 1 alone


# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

def load_csv(path: str, tz: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts_col = next((c for c in df.columns if c.lower() in
                   ("timestamp", "datetime", "date", "time")), df.columns[0])
    df[ts_col] = pd.to_datetime(df[ts_col], utc=False)
    if df[ts_col].dt.tz is None:
        df[ts_col] = df[ts_col].dt.tz_localize("UTC")
    df[ts_col] = df[ts_col].dt.tz_convert(tz)
    df = df.set_index(ts_col).sort_index()
    df.columns = [c.lower() for c in df.columns]
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep]


def make_sample_data(tz: str, days: int = 6, seed: int = 7) -> pd.DataFrame:
    """Synthetic 1m OHLCV built from anchor prices at key session times, so the
    shape (Asian range -> London sweep that wicks out and closes back inside
    -> NY displacement -> pullback -> engulfing continuation) is guaranteed
    regardless of random-walk drift. Purely a smoke-test fixture, not
    representative of any real market."""
    rng = np.random.default_rng(seed)
    bars = []
    start = pd.Timestamp("2026-01-05", tz=tz)  # a Monday
    base = 2000.0

    for d in range(days):
        day = start + pd.Timedelta(days=d)
        if day.weekday() >= 5:
            continue
        sweep_dir = 1 if (d % 2 == 0) else -1
        or_dir = -sweep_dir  # NY reverses toward the side that wasn't swept

        anchors = [
            ((day - pd.Timedelta(days=1)).replace(hour=20, minute=0), base),
            (day.replace(hour=0, minute=0), base),
            (day.replace(hour=2, minute=0), base),
            (day.replace(hour=3, minute=50), base + sweep_dir * 16),   # sweep peak
            (day.replace(hour=4, minute=50), base - sweep_dir * 3),    # closes back inside
            (day.replace(hour=9, minute=30), base),
            (day.replace(hour=9, minute=45), base),                     # tight OR box
        ]

        price = anchors[0][1]
        for (t0, p0), (t1, p1) in zip(anchors[:-1], anchors[1:]):
            n_min = int((t1 - t0).total_seconds() // 60)
            if n_min <= 0:
                continue
            for m in range(n_min):
                t = t0 + pd.Timedelta(minutes=m)
                frac = m / n_min
                target = p0 + (p1 - p0) * frac
                o = price
                c = target + rng.normal(0, 0.35)
                h = max(o, c) + abs(rng.normal(0.15, 0.15))
                l = min(o, c) - abs(rng.normal(0.15, 0.15))
                v = int(rng.integers(50, 500))
                bars.append((t, o, h, l, c, v))
                price = c

        # NY portion: explicit per-5-minute-candle deltas so the displacement
        # leg / zone / pullback / engulfing shape is unambiguous at the 5m
        # timeframe the strategy trades on. `or_dir` is the leg's direction.
        ny_start = day.replace(hour=9, minute=45)
        deltas = ([or_dir * 10, or_dir * 10, or_dir * 8,      # 3-candle displacement leg
                    -or_dir * 5, -or_dir * 5, -or_dir * 2,     # pullback deep enough to tag the zone
                    or_dir * 8,                                 # engulfing entry candle
                    or_dir * 10, or_dir * 10, or_dir * 8])      # continuation to target
        for k, delta in enumerate(deltas):
            t0 = ny_start + pd.Timedelta(minutes=5 * k)
            o = price
            for m in range(5):
                t = t0 + pd.Timedelta(minutes=m)
                frac = (m + 1) / 5
                c = o + delta * frac + rng.normal(0, 0.25)
                bo = price
                h = max(bo, c) + abs(rng.normal(0.1, 0.1))
                l = min(bo, c) - abs(rng.normal(0.1, 0.1))
                v = int(rng.integers(50, 500))
                bars.append((t, bo, h, l, c, v))
                price = c

        rest_start = ny_start + pd.Timedelta(minutes=5 * len(deltas))
        rest_end = day.replace(hour=17, minute=0)
        n_min = max(int((rest_end - rest_start).total_seconds() // 60), 0)
        for m in range(n_min):
            t = rest_start + pd.Timedelta(minutes=m)
            o = price
            c = o + rng.normal(0, 0.3)
            h = max(o, c) + abs(rng.normal(0.15, 0.15))
            l = min(o, c) - abs(rng.normal(0.15, 0.15))
            v = int(rng.integers(50, 500))
            bars.append((t, o, h, l, c, v))
            price = c

        base = price + rng.normal(0, 1)

    df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df.set_index("timestamp")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    out = df.resample(rule).agg(agg).dropna(subset=["open", "high", "low", "close"])
    return out


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


# ----------------------------------------------------------------------------
# Step 2: Session liquidity analysis
# ----------------------------------------------------------------------------

def session_high_low(df: pd.DataFrame, start_dt: pd.Timestamp, end_dt: pd.Timestamp):
    window = df.loc[start_dt:end_dt]
    if window.empty:
        return None
    return float(window["high"].max()), float(window["low"].min())


def detect_sweep(london_df: pd.DataFrame, asian_high: float, asian_low: float,
                  min_pen: float) -> str | None:
    """Returns 'high_swept', 'low_swept', or None. A sweep = price wicks beyond
    the Asian range at some point during London, then closes back inside it by
    the end of the window (classic liquidity-grab shape). The wick and the
    reversion don't need to be the same candle."""
    if london_df.empty:
        return None
    last_close = float(london_df["close"].iloc[-1])
    swept_high = (london_df["high"].max() > asian_high + min_pen) and (last_close < asian_high)
    swept_low = (london_df["low"].min() < asian_low - min_pen) and (last_close > asian_low)
    if swept_high and not swept_low:
        return "high_swept"
    if swept_low and not swept_high:
        return "low_swept"
    return None  # both or neither: no clean read, sit out


def session_bias(sweep: str | None) -> str | None:
    """NY is expected to reverse toward the side that was NOT taken."""
    if sweep == "high_swept":
        return "short"   # liquidity above taken -> expect move down to asian_low
    if sweep == "low_swept":
        return "long"    # liquidity below taken -> expect move up to asian_high
    return None


# ----------------------------------------------------------------------------
# Step 1: Displacement ORB
# ----------------------------------------------------------------------------

def is_bullish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    return (prev["close"] < prev["open"] and curr["close"] > curr["open"]
            and curr["close"] >= prev["open"] and curr["open"] <= prev["close"])


def is_bearish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    return (prev["close"] > prev["open"] and curr["close"] < curr["open"]
            and curr["close"] <= prev["open"] and curr["open"] >= prev["close"])


def find_displacement_leg(df5: pd.DataFrame, or_high: float, or_low: float,
                           atr5: pd.Series, cfg: Config, allowed_dir: str | None):
    """Scan 5m candles for N consecutive strong same-direction candles that
    close beyond the opening range. Returns dict(direction, start_idx, break_idx)
    or None."""
    directions = []
    for i in range(len(df5)):
        row = df5.iloc[i]
        a = atr5.iloc[i] if not np.isnan(atr5.iloc[i]) else 0
        body = row["close"] - row["open"]
        strong = abs(body) > a * cfg.displacement_atr_mult
        d = "up" if body > 0 else ("down" if body < 0 else None)
        directions.append(d if strong else None)

    for i in range(len(df5)):
        d = directions[i]
        if d is None or (allowed_dir and d != ("up" if allowed_dir == "long" else "down")):
            continue
        run_len = 1
        j = i
        while j + 1 < len(df5) and directions[j + 1] == d:
            j += 1
            run_len += 1
        if run_len >= cfg.displacement_min_candles:
            close_at_j = df5.iloc[j]["close"]
            broke = (d == "up" and close_at_j > or_high) or (d == "down" and close_at_j < or_low)
            if broke:
                return {"direction": "long" if d == "up" else "short",
                        "start_idx": i, "break_idx": j}
    return None


def find_fvg(df5: pd.DataFrame, start_idx: int, break_idx: int, direction: str):
    """3-candle fair value gap inside [start_idx-1, break_idx]. Bullish FVG:
    candle[i-1].high < candle[i+1].low. Returns (top, bottom, idx) or None."""
    lo = max(start_idx - 1, 1)
    for i in range(lo, break_idx):
        if i + 1 >= len(df5):
            break
        c0, c2 = df5.iloc[i - 1], df5.iloc[i + 1]
        if direction == "long" and c0["high"] < c2["low"]:
            return {"top": float(c2["low"]), "bottom": float(c0["high"]), "idx": i}
        if direction == "short" and c0["low"] > c2["high"]:
            return {"top": float(c0["low"]), "bottom": float(c2["high"]), "idx": i}
    return None


def find_base_candle_zone(df5: pd.DataFrame, start_idx: int, direction: str):
    """Demand/supply zone: last opposite-colored candle immediately before the
    impulsive leg begins."""
    for i in range(start_idx - 1, -1, -1):
        row = df5.iloc[i]
        is_opposite = (row["close"] < row["open"]) if direction == "long" else (row["close"] > row["open"])
        if is_opposite:
            return {"top": float(row["high"]), "bottom": float(row["low"]), "idx": i}
        if i < start_idx - 3:  # don't search too far back
            break
    return None


# ----------------------------------------------------------------------------
# Entry + trade simulation
# ----------------------------------------------------------------------------

@dataclass
class Trade:
    date: pd.Timestamp
    direction: str
    zone_type: str
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    result_r: float | None = None


def find_entry_and_simulate(df5: pd.DataFrame, break_idx: int, zone: dict,
                             direction: str, cfg: Config, atr5: pd.Series,
                             day: pd.Timestamp) -> Trade | None:
    top, bottom = zone["top"], zone["bottom"]
    buffer = float(atr5.iloc[break_idx]) * cfg.zone_buffer_atr_mult if not np.isnan(atr5.iloc[break_idx]) else 0

    end_idx = min(break_idx + int(cfg.retrace_window_minutes / 5), len(df5) - 1)
    for i in range(break_idx + 1, end_idx):
        row = df5.iloc[i]
        touched = row["low"] <= top and row["high"] >= bottom
        if not touched:
            continue
        if i + 1 >= len(df5):
            break
        prev, curr = df5.iloc[i], df5.iloc[i + 1]
        confirmed = (is_bullish_engulfing(prev, curr) if direction == "long"
                     else is_bearish_engulfing(prev, curr))
        if not confirmed:
            continue

        entry = float(curr["close"])
        if direction == "long":
            stop = bottom - buffer
            risk = entry - stop
            target = entry + risk * cfg.risk_reward
        else:
            stop = top + buffer
            risk = stop - entry
            target = entry - risk * cfg.risk_reward
        if risk <= 0:
            return None

        trade = Trade(date=day, direction=direction,
                       zone_type=zone.get("type", "zone"),
                       entry_time=curr.name, entry=entry, stop=stop, target=target)

        for k in range(i + 2, len(df5)):
            bar = df5.iloc[k]
            hit_stop = bar["low"] <= stop if direction == "long" else bar["high"] >= stop
            hit_tgt = bar["high"] >= target if direction == "long" else bar["low"] <= target
            if hit_stop and hit_tgt:
                trade.exit_time, trade.exit_price, trade.result_r = bar.name, stop, -1.0
                return trade
            if hit_stop:
                trade.exit_time, trade.exit_price, trade.result_r = bar.name, stop, -1.0
                return trade
            if hit_tgt:
                trade.exit_time, trade.exit_price, trade.result_r = bar.name, target, cfg.risk_reward
                return trade
        return trade  # never resolved within available data -> open/unresolved
    return None


# ----------------------------------------------------------------------------
# Backtest engine
# ----------------------------------------------------------------------------

class OrbSessionStrategy:
    def __init__(self, cfg: Config = Config()):
        self.cfg = cfg

    def run(self, df1: pd.DataFrame) -> pd.DataFrame:
        cfg = self.cfg
        df5 = resample_ohlc(df1, "5min")
        atr5 = atr(df5, cfg.atr_period)

        dates = sorted({ts.date() for ts in df5.index
                         if ts.time() >= cfg.ny_open})
        trades: list[Trade] = []

        for d in dates:
            day = pd.Timestamp(d, tz=df5.index.tz)

            asian = session_high_low(df1, (day - timedelta(days=1)).replace(
                hour=cfg.asian_start.hour, minute=cfg.asian_start.minute),
                day.replace(hour=cfg.asian_end.hour, minute=cfg.asian_end.minute))
            if asian is None:
                continue
            asian_high, asian_low = asian

            london_df = df1.loc[
                day.replace(hour=cfg.london_start.hour, minute=cfg.london_start.minute):
                day.replace(hour=cfg.london_end.hour, minute=cfg.london_end.minute)]
            sweep = detect_sweep(london_df, asian_high, asian_low,
                                  min_pen=(asian_high - asian_low) * cfg.sweep_min_atr_mult)
            bias = session_bias(sweep)

            if cfg.session_bias_required and bias is None:
                continue

            or_start = day.replace(hour=cfg.ny_open.hour, minute=cfg.ny_open.minute)
            or_end = or_start + timedelta(minutes=cfg.or_minutes)
            or_range = session_high_low(df1, or_start, or_end)
            if or_range is None:
                continue
            or_high, or_low = or_range

            window_end = or_end + timedelta(minutes=cfg.displacement_window_minutes)
            day5 = df5.loc[or_end:window_end]
            if day5.empty:
                continue
            day5_atr = atr5.loc[day5.index]

            leg = find_displacement_leg(day5, or_high, or_low, day5_atr, cfg, bias)
            if leg is None:
                continue
            direction = leg["direction"]

            zone = find_fvg(day5, leg["start_idx"], leg["break_idx"], direction)
            if zone:
                zone["type"] = "FVG"
            else:
                zone = find_base_candle_zone(day5, leg["start_idx"], direction)
                if zone:
                    zone["type"] = "base_candle"
            if zone is None:
                continue

            trade = find_entry_and_simulate(day5, leg["break_idx"], zone, direction,
                                             cfg, day5_atr, day)
            if trade is not None:
                trades.append(trade)
                if len(trades) >= cfg.max_trades_per_day:
                    pass  # one trade/day by construction of the loop

        if not trades:
            return pd.DataFrame(columns=["date", "direction", "zone_type", "entry_time",
                                          "entry", "stop", "target", "exit_time",
                                          "exit_price", "result_r"])
        return pd.DataFrame([t.__dict__ for t in trades])

    @staticmethod
    def summary(trades: pd.DataFrame) -> dict:
        resolved = trades.dropna(subset=["result_r"])
        if resolved.empty:
            return {"trades": len(trades), "resolved": 0}
        wins = (resolved["result_r"] > 0).sum()
        return {
            "trades": len(trades),
            "resolved": len(resolved),
            "win_rate_pct": round(100 * wins / len(resolved), 1),
            "avg_r": round(resolved["result_r"].mean(), 3),
            "expectancy_r": round(resolved["result_r"].mean(), 3),
            "total_r": round(resolved["result_r"].sum(), 2),
            "max_drawdown_r": round((resolved["result_r"].cumsum()
                                      - resolved["result_r"].cumsum().cummax()).min(), 2),
        }


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="ORB + Displacement + Session Liquidity backtester")
    p.add_argument("--csv", help="path to 1-minute OHLCV csv (falls back to sample data)")
    p.add_argument("--rr", type=float, default=2.0, help="risk:reward target")
    p.add_argument("--atr-mult", type=float, default=1.3, help="displacement strength threshold")
    p.add_argument("--no-bias", action="store_true", help="ignore Step 2 session bias filter")
    args = p.parse_args()

    cfg = Config(risk_reward=args.rr, displacement_atr_mult=args.atr_mult,
                 session_bias_required=not args.no_bias)

    if args.csv:
        df1 = load_csv(args.csv, cfg.tz)
        print(f"Loaded {len(df1)} 1m bars from {args.csv}")
    else:
        df1 = make_sample_data(cfg.tz)
        print("No --csv given: running on generated sample data (demo only, not real market data).")

    strat = OrbSessionStrategy(cfg)
    trades = strat.run(df1)

    pd.set_option("display.width", 120)
    if trades.empty:
        print("\nNo trades generated. Loosen displacement_atr_mult / disable session_bias_required, "
              "or check that your data actually spans Asian+London+NY hours.")
    else:
        print(f"\n{len(trades)} trade(s):")
        print(trades.to_string(index=False))
        print("\nSummary:", OrbSessionStrategy.summary(trades))


if __name__ == "__main__":
    main()
