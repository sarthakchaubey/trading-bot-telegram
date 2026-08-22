"""
Python re-implementation of the Pine Script "Swing Fibonacci Strategy".

This replays the exact same bar-by-bar logic as the original strategy:
  - pivot-based swing detection (left/right bars)
  - alternating high/low swing memory
  - directional fib construction (Follow Trend / Both / Bullish / Bearish)
  - fib levels 0 / .25 / .5 / .618 / .786 / .9 / 1
  - signal level touch detection ("came from above/below, then touched")
  - TP / SL selection from configurable fib levels + directional sanity check
  - optional filters: departure, candle confirmation, trend, consolidation,
    time-of-day / no-trade windows
  - a virtual "position" so a new signal can't fire again until the previous
    virtual trade would have hit its TP or SL (mirrors strategy.position_size)

Because this is alert-only, "entering a trade" just means "stop signaling
on this fib until price would have exited," matching the Pine strategy's
`strategy.position_size == 0` gating.

Call `run_strategy(df, cfg)` with a full OHLC DataFrame (oldest -> newest,
columns: time, open, high, low, close) and it returns a list of Event
objects, one for every BUY/SELL signal found in that history, in order.
The caller (main.py) is responsible for only alerting on *new* events it
hasn't already sent.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import pandas as pd

from indicators import sma, ema, atr as atr_fn, pivot_high, pivot_low


LEVELS = ("0", "0.25", "0.5", "0.618", "0.786", "0.9", "1")
LEVEL_RATIO = {"0": 0.0, "0.25": 0.25, "0.5": 0.50, "0.618": 0.618,
                "0.786": 0.786, "0.9": 0.90, "1": 1.0}


@dataclass
class Event:
    kind: str            # "BUY" or "SELL"
    time: pd.Timestamp
    price: float          # signal / entry price
    tp: float
    sl: float
    fib_high: float
    fib_low: float


@dataclass
class _FibState:
    direction: int = 0          # 1 bullish (low->high), -1 bearish (high->low), 0 none
    low: float = float("nan")
    high: float = float("nan")
    has_signaled: bool = False
    locked: bool = False


@dataclass
class _VirtualPosition:
    active: bool = False
    direction: int = 0
    tp: float = float("nan")
    sl: float = float("nan")


def _in_window(cur_min, start_min, end_min):
    if start_min <= end_min:
        return start_min <= cur_min <= end_min
    return cur_min >= start_min or cur_min <= end_min


def run_strategy(df: pd.DataFrame, cfg) -> List[Event]:
    df = df.reset_index(drop=True)
    n = len(df)
    if n < cfg.LEFT_BARS + cfg.RIGHT_BARS + 5:
        return []

    src_high = df["high"] if cfg.PRICE_SOURCE == "Wick" else df[["open", "close"]].max(axis=1)
    src_low = df["low"] if cfg.PRICE_SOURCE == "Wick" else df[["open", "close"]].min(axis=1)

    ph = pivot_high(src_high, cfg.LEFT_BARS, cfg.RIGHT_BARS)
    pl = pivot_low(src_low, cfg.LEFT_BARS, cfg.RIGHT_BARS)

    trend_ma = None
    trend_slope = None
    if cfg.USE_TREND_FILTER:
        ma_fn = ema if cfg.TREND_MA_TYPE == "EMA" else sma
        trend_ma = ma_fn(df["close"], cfg.TREND_LENGTH)
        trend_slope = trend_ma - trend_ma.shift(cfg.TREND_SLOPE_BARS)

    consolidating = None
    if cfg.USE_CONSOLIDATION_FILTER:
        c_atr = atr_fn(df, cfg.CONSOLIDATION_ATR_LENGTH)
        recent_range = (
            df["high"].rolling(cfg.CONSOLIDATION_LENGTH).max()
            - df["low"].rolling(cfg.CONSOLIDATION_LENGTH).min()
        )
        consolidating = recent_range <= c_atr * cfg.MAX_CONSOLIDATION_ATR

    last_high = float("nan")
    last_high_bar = None
    last_low = float("nan")
    last_low_bar = None
    last_swing_type = 0

    fib = _FibState()
    pos = _VirtualPosition()

    events: List[Event] = []

    tz = cfg.TIME_ZONE

    for i in range(n):
        row = df.iloc[i]
        t: pd.Timestamp = row["time"]
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]

        # -------------------- time filters --------------------
        local_t = t.tz_convert(tz) if t.tzinfo is not None else t
        cur_min = local_t.hour * 60 + local_t.minute

        allowed_time = True
        if cfg.USE_TIME_FILTER:
            allowed_time = _in_window(
                cur_min,
                cfg.START_HOUR * 60 + cfg.START_MINUTE,
                cfg.END_HOUR * 60 + cfg.END_MINUTE,
            )
        in_nt1 = cfg.USE_NO_TRADE_1 and _in_window(
            cur_min, cfg.NT1_START_HOUR * 60 + cfg.NT1_START_MINUTE,
            cfg.NT1_END_HOUR * 60 + cfg.NT1_END_MINUTE,
        )
        in_nt2 = cfg.USE_NO_TRADE_2 and _in_window(
            cur_min, cfg.NT2_START_HOUR * 60 + cfg.NT2_START_MINUTE,
            cfg.NT2_END_HOUR * 60 + cfg.NT2_END_MINUTE,
        )
        allowed_trade_time = allowed_time and not in_nt1 and not in_nt2

        # -------------------- virtual position exit --------------------
        if pos.active:
            if pos.direction == 1:
                if h >= pos.tp or l <= pos.sl:
                    pos.active = False
                    fib.locked = True
            else:
                if l <= pos.tp or h >= pos.sl:
                    pos.active = False
                    fib.locked = True

        position_flat = not pos.active

        min_fib_range = cfg.MIN_FIB_RANGE
        if getattr(cfg, "MIN_FIB_RANGE_OVERRIDES", None):
            min_fib_range = cfg.MIN_FIB_RANGE_OVERRIDES.get(
                getattr(cfg, "_current_instrument", None), cfg.MIN_FIB_RANGE
            )

        # -------------------- process new pivot high --------------------
        if not pd.isna(ph.iloc[i]):
            new_high_bar = i - cfg.RIGHT_BARS
            new_high = ph.iloc[i]

            enough_bars = last_low_bar is None or abs(new_high_bar - last_low_bar) >= cfg.MIN_BARS_BETWEEN_SWINGS
            enough_dist = pd.isna(last_low) or abs(new_high - last_low) >= cfg.MIN_SWING_SIZE
            alt_ok = (not cfg.REQUIRE_ALTERNATING_SWINGS) or last_swing_type != 1

            if enough_bars and enough_dist and alt_ok:
                if not pd.isna(last_low):
                    proposed_range = abs(new_high - last_low)
                    if proposed_range >= min_fib_range:
                        trend_ok = True
                        if cfg.FIB_DIRECTION == "Follow Trend" and not pd.isna(last_high) and not pd.isna(last_low):
                            trend_ok = new_high > last_high
                        dir_allowed = _direction_allowed(cfg, 1)
                        if dir_allowed and trend_ok and position_flat:
                            fib = _FibState(direction=1, low=last_low, high=new_high)

            last_high = new_high
            last_high_bar = new_high_bar
            last_swing_type = 1

        # -------------------- process new pivot low --------------------
        if not pd.isna(pl.iloc[i]):
            new_low_bar = i - cfg.RIGHT_BARS
            new_low = pl.iloc[i]

            enough_bars = last_high_bar is None or abs(new_low_bar - last_high_bar) >= cfg.MIN_BARS_BETWEEN_SWINGS
            enough_dist = pd.isna(last_high) or abs(new_low - last_high) >= cfg.MIN_SWING_SIZE
            alt_ok = (not cfg.REQUIRE_ALTERNATING_SWINGS) or last_swing_type != -1

            if enough_bars and enough_dist and alt_ok:
                if not pd.isna(last_high):
                    proposed_range = abs(last_high - new_low)
                    if proposed_range >= min_fib_range:
                        trend_ok = True
                        if cfg.FIB_DIRECTION == "Follow Trend" and not pd.isna(last_low) and not pd.isna(last_high):
                            trend_ok = new_low < last_low
                        dir_allowed = _direction_allowed(cfg, -1)
                        if dir_allowed and trend_ok and position_flat:
                            fib = _FibState(direction=-1, low=new_low, high=last_high)

            last_low = new_low
            last_low_bar = new_low_bar
            last_swing_type = -1

        # -------------------- extreme recalculation --------------------
        if cfg.RECALCULATE_ON_EXTREME and not fib.locked and position_flat and fib.direction != 0:
            if fib.direction == 1 and h > fib.high:
                fib.high = h
                fib.has_signaled = False
            elif fib.direction == -1 and l < fib.low:
                fib.low = l
                fib.has_signaled = False

        if fib.direction == 0:
            continue

        fib_range = abs(fib.high - fib.low)
        if fib_range < min_fib_range:
            continue

        # -------------------- fib levels --------------------
        levels = {}
        if fib.direction == 1:
            levels["0"] = fib.high
            levels["1"] = fib.low
            for lv in ("0.25", "0.5", "0.618", "0.786", "0.9"):
                levels[lv] = fib.high - fib_range * LEVEL_RATIO[lv]
        else:
            levels["0"] = fib.low
            levels["1"] = fib.high
            for lv in ("0.25", "0.5", "0.618", "0.786", "0.9"):
                levels[lv] = fib.low + fib_range * LEVEL_RATIO[lv]

        signal_price = levels[cfg.SIGNAL_LEVEL]

        if fib.direction == 1:
            calc_tp = levels[cfg.BULL_TP_LEVEL]
            calc_sl = levels[cfg.BULL_SL_LEVEL]
            valid_tp_sl = calc_tp > signal_price and calc_sl < signal_price
        else:
            calc_tp = levels[cfg.BEAR_TP_LEVEL]
            calc_sl = levels[cfg.BEAR_SL_LEVEL]
            valid_tp_sl = calc_tp < signal_price and calc_sl > signal_price

        # -------------------- departure filter --------------------
        departure_ok = True
        if cfg.USE_DEPARTURE_FILTER:
            if fib.direction == 1:
                req = cfg.DEPARTURE_VALUE if cfg.DEPARTURE_MODE == "Points" else signal_price * cfg.DEPARTURE_VALUE / 100.0
                departure_ok = (h - signal_price) >= req
            else:
                req = cfg.DEPARTURE_VALUE if cfg.DEPARTURE_MODE == "Points" else signal_price * cfg.DEPARTURE_VALUE / 100.0
                departure_ok = (signal_price - l) >= req

        # -------------------- candle confirmation --------------------
        candle_ok = True
        if cfg.USE_CANDLE_CONFIRMATION:
            candle_ok = _candle_confirmation(cfg, fib.direction, df, i, signal_price)

        # -------------------- trend filter --------------------
        trend_ok = True
        if cfg.USE_TREND_FILTER:
            tma = trend_ma.iloc[i]
            tsl = trend_slope.iloc[i]
            if pd.isna(tma) or pd.isna(tsl):
                trend_ok = False
            elif fib.direction == 1:
                trend_ok = c > tma and tsl >= cfg.MINIMUM_SLOPE
            else:
                trend_ok = c < tma and tsl <= -cfg.MINIMUM_SLOPE

        # -------------------- consolidation filter --------------------
        consolidation_ok = True
        if cfg.USE_CONSOLIDATION_FILTER:
            cval = consolidating.iloc[i]
            consolidation_ok = (not bool(cval)) if not pd.isna(cval) else False

        common_ok = (
            cfg.ENABLE_SIGNALS
            and allowed_trade_time
            and position_flat
            and not fib.locked
            and not fib.has_signaled
            and departure_ok
            and candle_ok
            and trend_ok
            and consolidation_ok
        )

        if not common_ok:
            continue

        if fib.direction == 1:
            prev_close = df["close"].iloc[i - 1] if i > 0 else float("nan")
            came_from_above = (not pd.isna(prev_close)) and prev_close > signal_price
            touched = l <= signal_price <= h
            if came_from_above and touched and valid_tp_sl:
                fib.has_signaled = True
                pos = _VirtualPosition(active=True, direction=1, tp=calc_tp, sl=calc_sl)
                events.append(Event("BUY", t, signal_price, calc_tp, calc_sl, fib.high, fib.low))

        elif fib.direction == -1:
            prev_close = df["close"].iloc[i - 1] if i > 0 else float("nan")
            came_from_below = (not pd.isna(prev_close)) and prev_close < signal_price
            touched = h >= signal_price >= l
            if came_from_below and touched and valid_tp_sl:
                fib.has_signaled = True
                pos = _VirtualPosition(active=True, direction=-1, tp=calc_tp, sl=calc_sl)
                events.append(Event("SELL", t, signal_price, calc_tp, calc_sl, fib.high, fib.low))

    return events


def _direction_allowed(cfg, direction: int) -> bool:
    if cfg.FIB_DIRECTION == "Both Directions":
        return True
    if cfg.FIB_DIRECTION == "Bullish Only":
        return direction == 1
    if cfg.FIB_DIRECTION == "Bearish Only":
        return direction == -1
    return True  # "Follow Trend" - trend_ok is checked separately


def _candle_confirmation(cfg, direction: int, df: pd.DataFrame, i: int, signal_price: float) -> bool:
    row = df.iloc[i]
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]

    if cfg.CONFIRMATION_TYPE == "Touch Only":
        return True

    if cfg.CONFIRMATION_TYPE == "Close Confirmation":
        if direction == 1:
            return l <= signal_price and c > signal_price
        return h >= signal_price and c < signal_price

    if cfg.CONFIRMATION_TYPE == "Rejection Candle":
        candle_range = h - l
        if candle_range <= 0:
            return False
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        if direction == 1:
            return l <= signal_price and c > signal_price and (lower_wick / candle_range) >= cfg.MINIMUM_WICK_RATIO
        return h >= signal_price and c < signal_price and (upper_wick / candle_range) >= cfg.MINIMUM_WICK_RATIO

    if cfg.CONFIRMATION_TYPE == "Engulfing Candle":
        if i == 0:
            return False
        prev = df.iloc[i - 1]
        po, pc = prev["open"], prev["close"]
        if direction == 1:
            return pc < po and c > o and o <= pc and c >= po
        return pc > po and c < o and o >= pc and c <= po

    return True
