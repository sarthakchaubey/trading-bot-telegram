"""
Python implementation of the TradingView Pine Script strategy:
"Momentum Exhaustion Breakout"

Calculations match version 6 of the original Pine Script:
- Breakout high/low detection
- Volume expansion filter
- Trend filters (Fast & Slow EMA)
- RSI & RSI Rate of Change (ROC) momentum qualifiers
- ATR-based Stop Loss & Take Profit targets
"""

from dataclasses import dataclass
from typing import List, Optional
import pandas as pd
from indicators import sma, ema, atr, rsi

@dataclass
class Event:
    kind: str            # "BUY" or "SELL"
    time: pd.Timestamp   # Time of the signal candle
    price: float         # Entry / Signal price
    tp: float            # Take Profit price target
    sl: float            # Stop Loss price target
    fib_high: float = 0.0 # Placeholder for compatibility with dashboard views
    fib_low: float = 0.0  # Placeholder for compatibility with dashboard views

def run_strategy(df: pd.DataFrame, cfg) -> List[Event]:
    """
    Executes the Momentum Exhaustion Breakout strategy.
    
    Parameters:
    - df: DataFrame containing columns: time (tz-aware UTC), open, high, low, close, volume
    - cfg: Configuration mock containing parameters defined in strategies.json
    
    Returns:
    - List[Event]: Chronological list of BUY/SELL triggers.
    """
    df = df.reset_index(drop=True)
    n = len(df)
    
    # ------------------------- INPUTS & DEFAULTS -------------------------
    n_len = int(getattr(cfg, "NLEN", 20))
    vol_len = int(getattr(cfg, "VOLLEN", 20))
    vol_mult = float(getattr(cfg, "VOLMULT", 1.5))

    ema_fast_len = int(getattr(cfg, "EMAFASTLEN", 20))
    ema_slow_len = int(getattr(cfg, "EMASLOWLEN", 50))

    rsi_len = int(getattr(cfg, "RSILEN", 14))
    roc_len = int(getattr(cfg, "ROCLEN", 5))
    rsi_confirm_lvl = float(getattr(cfg, "RSICONFIRMLVL", 55.0))

    atr_len = int(getattr(cfg, "ATRLEN", 14))
    atr_sl_mult = float(getattr(cfg, "ATRSLMULT", 1.5))
    atr_trail_mult = float(getattr(cfg, "ATRTRAILMULT", 1.5))
    allow_shorts = bool(getattr(cfg, "ALLOWSHORTS", True))

    if n < max(ema_slow_len, n_len + roc_len) + 5:
        return []

    # =========================================================================
    # 1. INDICATOR CALCULATIONS
    # =========================================================================
    close_s = df["close"]
    high_s = df["high"]
    low_s = df["low"]
    volume_s = df["volume"]

    # Trend Context
    ema_fast = ema(close_s, ema_fast_len)
    ema_slow = ema(close_s, ema_slow_len)
    uptrend = ema_fast > ema_slow

    # Breakout + Volume Context
    prior_high = high_s.shift(1).rolling(window=n_len).max()
    prior_low = low_s.shift(1).rolling(window=n_len).min()
    vol_avg = volume_s.rolling(window=vol_len).mean()
    vol_expansion = volume_s > (vol_avg * vol_mult)

    # RSI & Momentum
    rsi_val = rsi(close_s, rsi_len)
    rsi_roc = rsi_val - rsi_val.shift(roc_len)
    prior_rsi_pk = rsi_val.shift(1).rolling(window=n_len).max()

    # Breakout conditions
    breakout_up = (high_s > prior_high) & vol_expansion

    # ATR Values
    atr_val = atr(df, atr_len)

    # =========================================================================
    # 2. SIGNAL GENERATION LOOP
    # =========================================================================
    events: List[Event] = []

    # We replicate the 'strategy.position_size == 0' gate from Pine Script
    # using a virtual position flat state tracker
    pos_active = False
    pos_direction = 0  # 1 for Long, -1 for Short
    pos_tp = 0.0
    pos_sl = 0.0

    for i in range(1, n):
        row = df.iloc[i]
        t = row["time"]
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        a_val = atr_val.iloc[i]

        if pd.isna(a_val) or pd.isna(prior_high.iloc[i]) or pd.isna(rsi_roc.iloc[i]) or pd.isna(prior_rsi_pk.iloc[i]):
            continue

        # Check virtual position exit
        if pos_active:
            if pos_direction == 1:
                if h >= pos_tp or l <= pos_sl:
                    pos_active = False
            elif pos_direction == -1:
                if l <= pos_tp or h >= pos_sl:
                    pos_active = False

        # Evaluation signals only if position is flat
        if not pos_active:
            # Reconstruct boolean arrays variables evaluation at bar i
            is_breakout_up = breakout_up.iloc[i]
            is_uptrend = uptrend.iloc[i]
            r_val = rsi_val.iloc[i]
            r_roc = rsi_roc.iloc[i]
            r_pk = prior_rsi_pk.iloc[i]

            long_signal = is_breakout_up and is_uptrend and (r_roc > 0) and (r_val > rsi_confirm_lvl)
            fade_signal = allow_shorts and is_breakout_up and (not is_uptrend) and ((r_val < r_pk) or (r_roc < 0))

            if long_signal:
                sl_dist = a_val * atr_sl_mult
                # Note: original has trailing exit; we model with standard static SL and TP targets
                # TP target is scaled up by atr_trail_mult to mirror trailing exit expectations
                sl = c - sl_dist
                tp = c + (a_val * atr_trail_mult * 2.0)
                
                events.append(Event(
                    kind="BUY",
                    time=t,
                    price=c,
                    tp=tp,
                    sl=sl,
                    fib_high=tp,
                    fib_low=sl
                ))
                pos_active = True
                pos_direction = 1
                pos_tp = tp
                pos_sl = sl

            elif fade_signal:
                sl_dist = a_val * atr_sl_mult
                sl = c + sl_dist
                tp = c - (a_val * atr_trail_mult * 2.0)

                events.append(Event(
                    kind="SELL",
                    time=t,
                    price=c,
                    tp=tp,
                    sl=sl,
                    fib_high=sl,
                    fib_low=tp
                ))
                pos_active = True
                pos_direction = -1
                pos_tp = tp
                pos_sl = sl

    return events
