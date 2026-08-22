"""
Template for writing a custom strategy.

To implement a new strategy, define your logic inside the `run_strategy` function.
It takes a pandas DataFrame of candles and a config object, and returns a list of signal Event objects.
"""

from dataclasses import dataclass
from typing import List, Optional
import pandas as pd
from indicators import sma, ema, atr

@dataclass
class Event:
    kind: str            # "BUY" or "SELL"
    time: pd.Timestamp   # Time of the signal candle
    price: float         # Entry / Signal price
    tp: float            # Take Profit price target
    sl: float            # Stop Loss price target
    fib_high: float = 0.0 # Placeholder for compatibility with strategy.py Event schema
    fib_low: float = 0.0  # Placeholder for compatibility with strategy.py Event schema

def run_strategy(df: pd.DataFrame, cfg) -> List[Event]:
    """
    Main strategy calculations loop.
    
    Parameters:
    - df: DataFrame containing columns: time (tz-aware UTC), open, high, low, close
    - cfg: Configuration mock containing parameters defined in strategies.json
    
    Returns:
    - List[Event]: Chronological list of BUY/SELL triggers.
    """
    df = df.reset_index(drop=True)
    events: List[Event] = []
    
    n = len(df)
    if n < 30: # Minimum history lookback check
        return []

    # =========================================================================
    # 1. INDICATORS CALCULATIONS
    # =========================================================================
    # Example: Simple Moving Average (SMA) crossover
    fast_ma = sma(df["close"], 9)
    slow_ma = sma(df["close"], 21)
    current_atr = atr(df, 14)

    # =========================================================================
    # 2. STRATEGY LOOP
    # =========================================================================
    for i in range(1, n):
        row = df.iloc[i]
        t = row["time"]
        c_price = row["close"]
        atr_val = current_atr.iloc[i]

        # Detect crossover triggers
        bullish_crossover = (fast_ma.iloc[i-1] <= slow_ma.iloc[i-1]) and (fast_ma.iloc[i] > slow_ma.iloc[i])
        bearish_crossover = (fast_ma.iloc[i-1] >= slow_ma.iloc[i-1]) and (fast_ma.iloc[i] < slow_ma.iloc[i])

        # Simple ATR-based TP and SL calculations
        if bullish_crossover:
            tp = c_price + (atr_val * 2.0)
            sl = c_price - (atr_val * 1.5)
            events.append(Event(
                kind="BUY",
                time=t,
                price=c_price,
                tp=tp,
                sl=sl,
                fib_high=c_price,
                fib_low=sl
            ))
            
        elif bearish_crossover:
            tp = c_price - (atr_val * 2.0)
            sl = c_price + (atr_val * 1.5)
            events.append(Event(
                kind="SELL",
                time=t,
                price=c_price,
                tp=tp,
                sl=sl,
                fib_high=sl,
                fib_low=c_price
            ))

    return events
