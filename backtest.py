"""
Backtesting engine for Swing Fibonacci Strategy.

Fetches historical candles, executes strategy.run_strategy(), simulates trade
exits (TP vs SL hit), and prints comprehensive strategy performance metrics.

Usage:
    python backtest.py [--instrument EUR_USD] [--count 500] [--granularity M15]
"""

import sys
import argparse
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Any

import config as cfg
import twelvedata_feed
from strategy import run_strategy, Event


@dataclass
class TradeResult:
    event: Event
    status: str          # "WIN", "LOSS", or "OPEN"
    exit_time: pd.Timestamp = None
    exit_price: float = None
    pips: float = 0.0
    rrr: float = 0.0     # Risk-Reward Ratio


def get_pip_scale(instrument: str) -> float:
    """Returns pip scale factor for pip calculations."""
    if "JPY" in instrument:
        return 0.01
    elif "XAU" in instrument or "XAG" in instrument:
        return 1.0
    return 0.0001


def evaluate_trade(df: pd.DataFrame, event: Event, start_idx: int, instrument: str) -> TradeResult:
    pip_scale = get_pip_scale(instrument)
    
    # Calculate RRR
    if event.kind == "BUY":
        risk = event.price - event.sl
        reward = event.tp - event.price
    else:
        risk = event.sl - event.price
        reward = event.price - event.tp
        
    rrr = reward / risk if risk > 0 else 0.0

    # Simulate forward candle by candle
    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        t = row["time"]
        h = row["high"]
        l = row["low"]

        if event.kind == "BUY":
            # Check TP / SL hit
            hit_tp = h >= event.tp
            hit_sl = l <= event.sl
            
            if hit_tp and hit_sl:
                # Same candle touch - conservative assumption: SL hit first
                pips = (event.sl - event.price) / pip_scale
                return TradeResult(event, "LOSS", t, event.sl, pips, rrr)
            elif hit_tp:
                pips = (event.tp - event.price) / pip_scale
                return TradeResult(event, "WIN", t, event.tp, pips, rrr)
            elif hit_sl:
                pips = (event.sl - event.price) / pip_scale
                return TradeResult(event, "LOSS", t, event.sl, pips, rrr)

        elif event.kind == "SELL":
            hit_tp = l <= event.tp
            hit_sl = h >= event.sl

            if hit_tp and hit_sl:
                pips = (event.price - event.sl) / pip_scale
                return TradeResult(event, "LOSS", t, event.sl, pips, rrr)
            elif hit_tp:
                pips = (event.price - event.tp) / pip_scale
                return TradeResult(event, "WIN", t, event.tp, pips, rrr)
            elif hit_sl:
                pips = (event.price - event.sl) / pip_scale
                return TradeResult(event, "LOSS", t, event.sl, pips, rrr)

    # If trade didn't hit TP or SL before end of data
    last_close = df.iloc[-1]["close"]
    if event.kind == "BUY":
        pips = (last_close - event.price) / pip_scale
    else:
        pips = (event.price - last_close) / pip_scale
        
    return TradeResult(event, "OPEN", df.iloc[-1]["time"], last_close, pips, rrr)


def run_backtest(instrument: str, count: int = 500, granularity: str = None, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    granularity = granularity or cfg.GRANULARITY
    print(f"\n========================================================")
    print(f"  RUNNING BACKTEST: {instrument} ({granularity})")
    print(f"  Fetching up to {count} historical candles...")
    print(f"========================================================")

    df = twelvedata_feed.get_candles(instrument, count=count, granularity=granularity)
    if df.empty:
        print(f"❌ Error: No candles returned for {instrument}")
        return {}

    if start_date:
        start_dt = pd.to_datetime(start_date).tz_localize("UTC")
        df = df[df["time"] >= start_dt].reset_index(drop=True)
    if end_date:
        end_dt = pd.to_datetime(end_date).tz_localize("UTC")
        df = df[df["time"] <= end_dt].reset_index(drop=True)

    if df.empty:
        print(f"❌ Error: No candle data in requested date range ({start_date} to {end_date})")
        return {}

    cfg._current_instrument = instrument
    events = run_strategy(df, cfg)

    if not events:
        print(f"ℹ️ No signals generated for {instrument} in the analyzed period ({len(df)} bars).")
        return {
            "instrument": instrument,
            "candles": len(df),
            "start_time": df.iloc[0]["time"],
            "end_time": df.iloc[-1]["time"],
            "total_trades": 0,
        }

    # Map timestamps to index for fast lookup
    time_to_idx = {t: idx for idx, t in enumerate(df["time"])}

    results: List[TradeResult] = []
    for ev in events:
        start_idx = time_to_idx.get(ev.time, 0)
        res = evaluate_trade(df, ev, start_idx + 1, instrument)
        results.append(res)

    wins = [r for r in results if r.status == "WIN"]
    losses = [r for r in results if r.status == "LOSS"]
    opens = [r for r in results if r.status == "OPEN"]

    win_rate = (len(wins) / (len(wins) + len(losses)) * 100) if (wins or losses) else 0.0

    total_win_pips = sum(r.pips for r in wins)
    total_loss_pips = abs(sum(r.pips for r in losses))
    net_pips = sum(r.pips for r in results)

    profit_factor = (total_win_pips / total_loss_pips) if total_loss_pips > 0 else float("inf")

    print(f"\n📊 --- BACKTEST RESULTS: {instrument} ---")
    print(f"Period Covered   : {df.iloc[0]['time'].strftime('%Y-%m-%d %H:%M UTC')} to {df.iloc[-1]['time'].strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Total Bars Tested: {len(df)}")
    print(f"Total Signals    : {len(events)}")
    print(f"Wins             : {len(wins)} ✅")
    print(f"Losses           : {len(losses)} ❌")
    print(f"Open Positions   : {len(opens)} ⏳")
    print(f"Win Rate         : {win_rate:.2f}%")
    print(f"Net Gain/Loss    : {net_pips:+.1f} pips/points")
    print(f"Profit Factor    : {profit_factor:.2f}")

    print("\n📋 --- DETAILED TRADE LOG ---")
    header = f"{'#':<3} | {'Type':<4} | {'Entry Time':<16} | {'Entry':<9} | {'TP':<9} | {'SL':<9} | {'Result':<6} | {'Pips/Pts':<8} | {'RRR':<5}"
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    for idx, r in enumerate(results, 1):
        ev = r.event
        status_icon = "✅ WIN" if r.status == "WIN" else ("❌ LOSS" if r.status == "LOSS" else "⏳ OPEN")
        print(
            f"{idx:<3} | {ev.kind:<4} | {ev.time.strftime('%m-%d %H:%M'):<16} | "
            f"{ev.price:<9.5f} | {ev.tp:<9.5f} | {ev.sl:<9.5f} | "
            f"{status_icon:<6} | {r.pips:<+8.1f} | {r.rrr:<5.2f}"
        )
    print("-" * len(header))

    return {
        "instrument": instrument,
        "candles": len(df),
        "total_trades": len(events),
        "wins": len(wins),
        "losses": len(losses),
        "opens": len(opens),
        "win_rate": win_rate,
        "net_pips": net_pips,
        "profit_factor": profit_factor,
        "results": results
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest Swing Fibonacci Strategy")
    parser.add_argument("--instrument", type=str, help="Instrument to test (e.g. EUR_USD, XAU_USD)")
    parser.add_argument("--count", type=int, default=500, help="Number of candles to fetch")
    parser.add_argument("--granularity", type=str, help="Timeframe granularity (e.g. M5, M15, H1)")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    instruments = [args.instrument] if args.instrument else cfg.INSTRUMENTS

    summary = []
    for inst in instruments:
        res = run_backtest(inst, count=args.count, granularity=args.granularity, start_date=args.start_date, end_date=args.end_date)
        if res:
            summary.append(res)

    if len(summary) > 1:
        print("\n========================================================")
        print("  OVERALL BACKTEST SUMMARY")
        print("========================================================")
        for s in summary:
            print(f"• {s['instrument']}: {s['total_trades']} trades | Win Rate: {s.get('win_rate', 0):.1f}% | Net: {s.get('net_pips', 0):+.1f} pips | Profit Factor: {s.get('profit_factor', 0):.2f}")


if __name__ == "__main__":
    main()
