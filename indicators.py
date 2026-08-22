"""Minimal indicator helpers (no external TA library needed)."""

import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=length).mean()


def pivot_high(series: pd.Series, left: int, right: int) -> pd.Series:
    """
    Mirrors Pine's ta.pivothigh(source, left, right): a bar is a pivot high
    if it is strictly the max within [i-left, i+right]. The value is only
    known `right` bars after the pivot bar (same lag as Pine).
    Returns a Series aligned to `series.index`, NaN where no pivot.
    """
    n = len(series)
    out = pd.Series(index=series.index, dtype=float)
    vals = series.values
    for i in range(left, n - right):
        window = vals[i - left : i + right + 1]
        center = vals[i]
        if center == window.max() and (window == center).sum() == 1:
            out.iloc[i] = center
    return out


def pivot_low(series: pd.Series, left: int, right: int) -> pd.Series:
    n = len(series)
    out = pd.Series(index=series.index, dtype=float)
    vals = series.values
    for i in range(left, n - right):
        window = vals[i - left : i + right + 1]
        center = vals[i]
        if center == window.min() and (window == center).sum() == 1:
            out.iloc[i] = center
    return out


def rsi(series: pd.Series, length: int) -> pd.Series:
    """
    RSI calculation matching TradingView's ta.rsi (Wilder's moving average smoothing).
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Wilder's moving average of length N is equivalent to an EMA of span 2N - 1
    wilder_span = 2 * length - 1
    avg_gain = gain.ewm(span=wilder_span, adjust=False).mean()
    avg_loss = loss.ewm(span=wilder_span, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))
