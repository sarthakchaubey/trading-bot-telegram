"""
Runs OrbSessionStrategy on real market data fetched via Twelve Data API.
"""

import pandas as pd
import twelvedata_feed
import config as cfg
from orb_session_strategy import OrbSessionStrategy, Config

def run_real_backtest(instrument: str = "EUR_USD", count: int = 500, rr: float = 2.0, no_bias: bool = False):
    print(f"Fetching {count} 1-minute candles for {instrument} from Twelve Data...")
    df = twelvedata_feed.get_candles(instrument, count=count, granularity="M1")
    if df.empty:
        print("No data returned!")
        return

    # Prepare DataFrame for OrbSessionStrategy
    # Expects index = timestamp in America/New_York tz
    df["timestamp"] = df["time"].dt.tz_convert("America/New_York")
    df = df.set_index("timestamp").sort_index()
    df = df[["open", "high", "low", "close"]]

    print(f"Data period: {df.index[0]} to {df.index[-1]} ({len(df)} 1-minute bars)")

    c = Config(risk_reward=rr, session_bias_required=not no_bias)
    strat = OrbSessionStrategy(c)
    trades = strat.run(df)

    pd.set_option("display.width", 140)
    if trades.empty:
        print("\nNo trades generated under strict session bias rules.")
        print("Retrying with --no-bias (Step 1 Displacement ORB alone)...")
        c.session_bias_required = False
        strat = OrbSessionStrategy(c)
        trades = strat.run(df)

    if trades.empty:
        print("No trades generated on the analyzed 1-minute dataset.")
    else:
        print(f"\n{len(trades)} Trade(s) Generated:")
        print(trades.to_string(index=False))
        print("\nSummary Metrics:")
        print(OrbSessionStrategy.summary(trades))

if __name__ == "__main__":
    import sys
    inst = sys.argv[1] if len(sys.argv) > 1 else "XAU_USD"
    run_real_backtest(instrument=inst, count=500)
