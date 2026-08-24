import os
import json
import time
import threading
import traceback
import collections
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

import config as cfg
import twelvedata_feed
import strategy as fib_strategy
import custom_strategy_template as breakout_strategy
import ai_strategy
from strategy import Event

# ============================================================================
# Core Server Setup
# ============================================================================
app = FastAPI(title="Swing Fibonacci Strategy Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STRATEGIES_FILE = "strategies.json"
SIGNALS_FILE = "signals_history.json"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Make sure static directory exists
os.makedirs(STATIC_DIR, exist_ok=True)

# Helper to load strategies
def load_strategies() -> List[Dict[str, Any]]:
    if not os.path.exists(STRATEGIES_FILE):
        return []
    try:
        with open(STRATEGIES_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading strategies: {e}")
        return []

# Helper to save strategies
def save_strategies(strategies: List[Dict[str, Any]]):
    try:
        with open(STRATEGIES_FILE, "w") as f:
            json.dump(strategies, f, indent=2)
    except Exception as e:
        print(f"Error saving strategies: {e}")

# Helper to save signal to history file
def save_signal_to_history(signal_data: Dict[str, Any]):
    try:
        history = []
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, "r") as f:
                history = json.load(f)
        history.append(signal_data)
        with open(SIGNALS_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving signal to history: {e}")

# ============================================================================
# Bot Workers & Thread Coordinator
# ============================================================================
class BotWorker:
    def __init__(self, strategy_config: Dict[str, Any]):
        self.config = strategy_config
        self.running = False
        self.stop_event = threading.Event()
        self.thread = None
        self.logs = collections.deque(maxlen=150)
        self.last_run = None
        self.last_alert_time = None
        self.error_count = 0

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}"
        print(f"[{self.config['name']}] {log_line}")
        self.logs.append(log_line)

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.log("Worker daemon thread started.")

        # Send Telegram startup notification if enabled (asynchronously)
        if self.config.get("telegram_enabled", False):
            def send_telegram_async():
                try:
                    import telegram_notifier
                    msg = f"🤖 <b>[Bot Dashboard: {self.config['name']}]</b>\n🟢 Bot is now <b>ONLINE</b> and watching <code>{self.config['instrument']} ({self.config['granularity']})</code>."
                    telegram_notifier.send_message(msg)
                except Exception as telegram_err:
                    self.log(f"Telegram startup notification error: {telegram_err}")
            threading.Thread(target=send_telegram_async, daemon=True).start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.log("Worker stop requested. Joining thread...")
        if self.thread:
            self.thread.join(timeout=2)
        self.log("Worker stopped.")

        # Send Telegram stop notification if enabled (asynchronously)
        if self.config.get("telegram_enabled", False):
            def send_telegram_async():
                try:
                    import telegram_notifier
                    msg = f"🤖 <b>[Bot Dashboard: {self.config['name']}]</b>\n🔴 Bot is now <b>OFFLINE</b> (stopped)."
                    telegram_notifier.send_message(msg)
                except Exception as telegram_err:
                    self.log(f"Telegram stop notification error: {telegram_err}")
            threading.Thread(target=send_telegram_async, daemon=True).start()

    def _run_loop(self):
        class ConfigMock:
            pass

        cfg_mock = ConfigMock()
        
        # Load all global config variables from config.py as defaults
        for attr in dir(cfg):
            if attr.isupper():
                setattr(cfg_mock, attr, getattr(cfg, attr))
        
        # Map JSON keys to uppercase config attributes
        for k, v in self.config.items():
            setattr(cfg_mock, k.upper(), v)
            
        cfg_mock._current_instrument = self.config["instrument"]
        cfg_mock.MIN_FIB_RANGE_OVERRIDES = {}
        cfg_mock.CANDLE_HISTORY_COUNT = self.config.get("candle_history_count", 300)

        # Stagger startup based on its list position to avoid Twelve Data rate-limiting spikes
        if self.stop_event.wait(timeout=2):
            return
        self.log(f"Worker initialized. Priming candle history...")

        try:
            df = twelvedata_feed.get_candles(
                self.config["instrument"],
                count=cfg_mock.CANDLE_HISTORY_COUNT,
                granularity=self.config["granularity"],
                stop_event=self.stop_event
            )
            # Route to correct strategy execution logic
            strat_type = self.config.get("strategy_type", "Fibonacci")
            if strat_type == "MomentumBreakout":
                events = breakout_strategy.run_strategy(df, cfg_mock)
            elif strat_type == "AIClaude":
                events = ai_strategy.run_strategy(df, cfg_mock)
            else:
                events = fib_strategy.run_strategy(df, cfg_mock)

            if events:
                self.last_alert_time = events[-1].time
                self.log(f"Primed successfully. Last historical signal found at {events[-1].time.strftime('%Y-%m-%d %H:%M UTC')}")
            else:
                self.log("Primed successfully. No historical signals found.")
        except Exception as e:
            self.log(f"Priming failed: {str(e)}")

        while not self.stop_event.is_set():
            self.last_run = datetime.now()
            try:
                df = twelvedata_feed.get_candles(
                    self.config["instrument"],
                    count=cfg_mock.CANDLE_HISTORY_COUNT,
                    granularity=self.config["granularity"],
                    stop_event=self.stop_event
                )
                
                if df.empty:
                    self.log("Warning: Fetched empty data frame.")
                else:
                    strat_type = self.config.get("strategy_type", "Fibonacci")
                    if strat_type == "MomentumBreakout":
                        events = breakout_strategy.run_strategy(df, cfg_mock)
                    elif strat_type == "AIClaude":
                        events = ai_strategy.run_strategy(df, cfg_mock)
                    else:
                        events = fib_strategy.run_strategy(df, cfg_mock)

                    new_events = [e for e in events if self.last_alert_time is None or e.time > self.last_alert_time]
                    
                    for event in new_events:
                        arrow = "🟢 BUY" if event.kind == "BUY" else "🔴 SELL"
                        self.log(f"ALERT: New signal generated -> {arrow} @ {event.price:.5f}")
                        
                        signal_data = {
                            "strategy_id": self.config["id"],
                            "strategy_name": self.config["name"],
                            "instrument": self.config["instrument"],
                            "granularity": self.config["granularity"],
                            "kind": event.kind,
                            "time": event.time.isoformat(),
                            "price": event.price,
                            "tp": event.tp,
                            "sl": event.sl,
                            "fib_low": event.fib_low,
                            "fib_high": event.fib_high,
                            "timestamp": datetime.now().isoformat()
                        }
                        save_signal_to_history(signal_data)
                        
                        if self.config.get("telegram_enabled", False):
                            try:
                                import telegram_notifier
                                formatted = telegram_notifier.format_signal(self.config["instrument"], self.config["granularity"], event)
                                text = f"🤖 <b>[Bot Dashboard: {self.config['name']}]</b>\n{formatted}"
                                telegram_notifier.send_message(text)
                                self.log("Telegram alert message dispatched.")
                            except Exception as telegram_err:
                                self.log(f"Telegram alerting error: {telegram_err}")
                                
                    if new_events:
                        self.last_alert_time = new_events[-1].time
                
                self.error_count = 0  # reset error counter on success
            except Exception as loop_err:
                self.error_count += 1
                self.log(f"Execution Error (Count: {self.error_count}): {traceback.format_exc()}")
                
            # Sleep for 60 seconds or until stop_event is set
            if self.stop_event.wait(timeout=60):
                break

# Active running worker threads dictionary
workers: Dict[str, BotWorker] = {}

def init_workers():
    strategies = load_strategies()
    for strat in strategies:
        if strat.get("status") == "active":
            worker = BotWorker(strat)
            workers[strat["id"]] = worker
            worker.start()

@app.on_event("startup")
def startup_event():
    init_workers()

@app.on_event("shutdown")
def shutdown_event():
    for w_id, worker in list(workers.items()):
        worker.stop()

# ============================================================================
# API Model Schemas
# ============================================================================
class StrategyConfigSchema(BaseModel):
    id: str
    name: str
    instrument: str
    granularity: str
    use_time_filter: bool
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    use_no_trade_1: bool
    nt1_start_hour: int
    nt1_start_minute: int
    nt1_end_hour: int
    nt1_end_minute: int
    use_no_trade_2: bool
    nt2_start_hour: int
    nt2_start_minute: int
    nt2_end_hour: int
    nt2_end_minute: int
    left_bars: int
    right_bars: int
    min_swing_size: float
    min_fib_range: float
    min_bars_between_swings: int
    price_source: str
    fib_direction: str
    require_alternating_swings: bool
    recalculate_on_extreme: bool
    signal_level: str
    bull_tp_level: str
    bull_sl_level: str
    bear_tp_level: str
    bear_sl_level: str
    use_departure_filter: bool
    departure_value: float
    departure_mode: str
    use_candle_confirmation: bool
    confirmation_type: str
    minimum_wick_ratio: float
    use_trend_filter: bool
    trend_ma_type: str
    trend_length: int
    trend_slope_bars: int
    minimum_slope: float
    use_consolidation_filter: bool
    consolidation_length: int
    consolidation_atr_length: int
    max_consolidation_atr: float
    telegram_enabled: bool
    status: str
    strategy_type: str = "Fibonacci"

class BacktestRequestSchema(BaseModel):
    strategy_id: str
    count: int = 500
    force_refresh: bool = False
    instrument: Optional[str] = None
    granularity: Optional[str] = None

class AnalyzeRequestSchema(BaseModel):
    instrument: str
    granularity: str
    strategy_type: str
    count: int = 300


# ============================================================================
# API Routes
# ============================================================================

@app.get("/api/strategies")
def get_strategies():
    return load_strategies()

@app.post("/api/strategies")
def create_or_update_strategy(strat: StrategyConfigSchema):
    strategies = load_strategies()
    existing_idx = next((i for i, s in enumerate(strategies) if s["id"] == strat.id), None)
    
    strat_dict = strat.dict()
    
    if existing_idx is not None:
        # Preserve running state logic
        old_status = strategies[existing_idx].get("status", "inactive")
        strategies[existing_idx] = strat_dict
        
        # If it was active, restart worker with updated config parameters
        if old_status == "active":
            if strat.id in workers:
                workers[strat.id].stop()
            worker = BotWorker(strat_dict)
            workers[strat.id] = worker
            worker.start()
    else:
        strategies.append(strat_dict)
        # If created in active state
        if strat.status == "active":
            worker = BotWorker(strat_dict)
            workers[strat.id] = worker
            worker.start()
            
    save_strategies(strategies)
    return {"status": "success", "data": strat_dict}

@app.delete("/api/strategies/{strat_id}")
def delete_strategy(strat_id: str):
    strategies = load_strategies()
    existing_idx = next((i for i, s in enumerate(strategies) if s["id"] == strat_id), None)
    
    if existing_idx is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
        
    # Stop background worker if active
    if strat_id in workers:
        workers[strat_id].stop()
        del workers[strat_id]
        
    strategies.pop(existing_idx)
    save_strategies(strategies)
    return {"status": "success", "message": f"Strategy {strat_id} deleted."}

@app.post("/api/bot/start/{strat_id}")
def start_bot(strat_id: str):
    strategies = load_strategies()
    strat = next((s for s in strategies if s["id"] == strat_id), None)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy config not found.")
        
    if strat_id in workers and workers[strat_id].running:
        return {"status": "already_running"}
        
    # Set config file status
    strat["status"] = "active"
    save_strategies(strategies)
    
    # Spawn worker
    worker = BotWorker(strat)
    workers[strat_id] = worker
    worker.start()
    return {"status": "started"}

@app.post("/api/bot/stop/{strat_id}")
def stop_bot(strat_id: str):
    strategies = load_strategies()
    strat = next((s for s in strategies if s["id"] == strat_id), None)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy config not found.")
        
    # Update config file
    strat["status"] = "inactive"
    save_strategies(strategies)
    
    # Stop worker thread
    if strat_id in workers:
        workers[strat_id].stop()
        del workers[strat_id]
    return {"status": "stopped"}

@app.get("/api/status")
def get_bot_status():
    strategies = load_strategies()
    status_list = []
    
    for s in strategies:
        w_id = s["id"]
        worker = workers.get(w_id)
        
        status_list.append({
            "id": w_id,
            "name": s["name"],
            "instrument": s["instrument"],
            "granularity": s["granularity"],
            "status": "running" if (worker and worker.running) else "stopped",
            "last_run": worker.last_run.isoformat() if (worker and worker.last_run) else None,
            "error_count": worker.error_count if worker else 0,
            "logs": list(worker.logs) if worker else []
        })
    return status_list

@app.get("/api/signals")
def get_signals():
    if not os.path.exists(SIGNALS_FILE):
        return []
    try:
        with open(SIGNALS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def get_pip_scale(instrument: str) -> float:
    """Returns pip scale factor for pip calculations."""
    if "JPY" in instrument:
        return 0.01
    elif "XAU" in instrument or "XAG" in instrument:
        return 1.0
    return 0.0001

# ============================================================================
# Backtester Simulator Implementation (Real Market Simulation)
# ============================================================================
def simulate_trades(df: pd.DataFrame, events: List[Event], instrument: str = "EUR_USD") -> tuple:
    simulated = []
    wins = 0
    losses = 0
    total_pnl_pct = 0.0
    pip_scale = get_pip_scale(instrument)

    # Map timestamps to index for fast O(1) loop iteration index resolution
    time_to_idx = {row["time"]: idx for idx, row in df.iterrows()}

    for e in events:
        start_idx = time_to_idx.get(e.time)
        if start_idx is None:
            continue

        outcome = "OPEN"
        exit_price = df.iloc[-1]["close"]
        exit_time = df.iloc[-1]["time"]
        pnl_points = 0.0
        pnl_pct = 0.0

        # Calculate Risk-Reward Ratio
        if e.kind == "BUY":
            risk = e.price - e.sl
            reward = e.tp - e.price
        else:
            risk = e.sl - e.price
            reward = e.price - e.tp
        rrr = (reward / risk) if risk > 0 else 0.0

        # Run forward trade simulation strictly starting from the subsequent candle (start_idx + 1)
        # to eliminate within-candle retrospective lookahead bias
        for idx in range(start_idx + 1, len(df)):
            row = df.iloc[idx]
            h, l, c = row["high"], row["low"], row["close"]

            if e.kind == "BUY":
                hit_tp = h >= e.tp
                hit_sl = l <= e.sl
                if hit_tp and hit_sl:
                    # Intrabar collision: assume conservative Stop-Loss first
                    outcome = "LOSS"
                    exit_price = e.sl
                    exit_time = row["time"]
                    pnl_points = e.sl - e.price
                    pnl_pct = (pnl_points / e.price) * 100.0
                    losses += 1
                    break
                elif hit_tp:
                    outcome = "WIN"
                    exit_price = e.tp
                    exit_time = row["time"]
                    pnl_points = e.tp - e.price
                    pnl_pct = (pnl_points / e.price) * 100.0
                    wins += 1
                    break
                elif hit_sl:
                    outcome = "LOSS"
                    exit_price = e.sl
                    exit_time = row["time"]
                    pnl_points = e.sl - e.price
                    pnl_pct = (pnl_points / e.price) * 100.0
                    losses += 1
                    break
            else:  # SELL
                hit_tp = l <= e.tp
                hit_sl = h >= e.sl
                if hit_tp and hit_sl:
                    # Intrabar collision: assume conservative Stop-Loss first
                    outcome = "LOSS"
                    exit_price = e.sl
                    exit_time = row["time"]
                    pnl_points = e.price - e.sl
                    pnl_pct = (pnl_points / e.price) * 100.0
                    losses += 1
                    break
                elif hit_tp:
                    outcome = "WIN"
                    exit_price = e.tp
                    exit_time = row["time"]
                    pnl_points = e.price - e.tp
                    pnl_pct = (pnl_points / e.price) * 100.0
                    wins += 1
                    break
                elif hit_sl:
                    outcome = "LOSS"
                    exit_price = e.sl
                    exit_time = row["time"]
                    pnl_points = e.price - e.sl
                    pnl_pct = (pnl_points / e.price) * 100.0
                    losses += 1
                    break
        else:
            # Trade remains open at the most recent candle close
            outcome = "OPEN"
            exit_price = df.iloc[-1]["close"]
            exit_time = df.iloc[-1]["time"]
            if e.kind == "BUY":
                pnl_points = exit_price - e.price
            else:
                pnl_points = e.price - exit_price
            pnl_pct = (pnl_points / e.price) * 100.0

        total_pnl_pct += pnl_pct
        pips = pnl_points / pip_scale

        simulated.append({
            "type": e.kind,
            "entry_time": e.time.strftime('%Y-%m-%d %H:%M UTC'),
            "entry_price": float(e.price),
            "tp": float(e.tp),
            "sl": float(e.sl),
            "exit_time": exit_time.strftime('%Y-%m-%d %H:%M UTC'),
            "exit_price": float(exit_price),
            "outcome": outcome,
            "pnl_points": float(pnl_points),
            "pnl_pct": float(pnl_pct),
            "pips": float(pips),
            "rrr": float(rrr),
            "cumulative_pnl_pct": float(total_pnl_pct)
        })

    return simulated, wins, losses

@app.post("/api/backtest")
def run_backtest(req: BacktestRequestSchema):
    strategies = load_strategies()
    strat = next((s for s in strategies if s["id"] == req.strategy_id), None)
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy config not found.")

    # Apply instrument and granularity overrides if provided
    target_instrument = req.instrument or strat.get("instrument", "EUR_USD")
    target_granularity = req.granularity or strat.get("granularity", "M15")

    strat["instrument"] = target_instrument
    strat["granularity"] = target_granularity

    # Adjust default minimum fib range if instrument changed
    min_fib = 3.0
    if "EUR_USD" in target_instrument:
        min_fib = 0.0030
    elif "GBP_USD" in target_instrument:
        min_fib = 0.0035
    elif "USD_JPY" in target_instrument:
        min_fib = 0.30
    elif "XAU_USD" in target_instrument:
        min_fib = 3.0
    else:
        min_fib = 0.0030
    strat["min_fib_range"] = min_fib

    class ConfigMock:
        pass
        
    cfg_mock = ConfigMock()
    # Load all global config variables from config.py as defaults
    for attr in dir(cfg):
        if attr.isupper():
            setattr(cfg_mock, attr, getattr(cfg, attr))
            
    for k, v in strat.items():
        setattr(cfg_mock, k.upper(), v)
        setattr(cfg_mock, k.lower(), v)
        
    cfg_mock._current_instrument = target_instrument
    cfg_mock.MIN_FIB_RANGE_OVERRIDES = {}
    cfg_mock.CANDLE_HISTORY_COUNT = req.count

    try:
        # Fetch authentic real market candles from Twelve Data
        df = twelvedata_feed.get_candles(
            target_instrument,
            count=req.count,
            granularity=target_granularity,
            force_refresh=req.force_refresh
        )
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Twelve Data returned no candle data.")

        strat_type = strat.get("strategy_type", "Fibonacci")
        if strat_type == "MomentumBreakout":
            events = breakout_strategy.run_strategy(df, cfg_mock)
        elif strat_type == "AIClaude":
            events = ai_strategy.run_strategy(df, cfg_mock)
        else:
            events = fib_strategy.run_strategy(df, cfg_mock)

        trades, wins, losses = simulate_trades(df, events, target_instrument)

        # Calculate metrics
        total_trades = len(trades)
        open_trades = sum(1 for t in trades if t["outcome"] == "OPEN")
        closed_trades = total_trades - open_trades
        win_rate = (wins / closed_trades * 100) if closed_trades > 0 else 0
        net_profit_pct = sum(t["pnl_pct"] for t in trades)
        net_pips = sum(t["pips"] for t in trades)
        
        # Profit Factor
        gross_profit_points = sum(t["pnl_points"] for t in trades if t["outcome"] == "WIN")
        gross_loss_points = abs(sum(t["pnl_points"] for t in trades if t["outcome"] == "LOSS"))
        profit_factor = (gross_profit_points / gross_loss_points) if gross_loss_points > 0 else (99.0 if gross_profit_points > 0 else 0.0)

        # Max drawdown based on cumulative PnL
        max_drawdown = 0.0
        peak = 0.0
        for t in trades:
            peak = max(peak, t["cumulative_pnl_pct"])
            drawdown = peak - t["cumulative_pnl_pct"]
            max_drawdown = max(max_drawdown, drawdown)

        # Format real price history for chart rendering
        chart_candles = []
        for _, row in df.iterrows():
            chart_candles.append({
                "time": row["time"].strftime('%Y-%m-%d %H:%M UTC'),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"])
            })

        return {
            "strategy": strat["name"],
            "instrument": target_instrument,
            "granularity": target_granularity,
            "period": {
                "start": df.iloc[0]["time"].strftime('%Y-%m-%d %H:%M UTC'),
                "end": df.iloc[-1]["time"].strftime('%Y-%m-%d %H:%M UTC'),
                "bars": len(df)
            },
            "metrics": {
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "open_trades": open_trades,
                "win_rate": round(win_rate, 2),
                "net_profit_pct": round(net_profit_pct, 4),
                "net_pips": round(net_pips, 1),
                "profit_factor": round(profit_factor, 2),
                "max_drawdown_pct": round(max_drawdown, 4)
            },
            "trades": trades,
            "candles": chart_candles
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backtest execution error: {str(e)}")

@app.get("/api/quotes")
def get_live_quotes():
    """Provides current price, change, and 24h summary for watchlist tickers."""
    watchlist_symbols = ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"]
    quotes = []
    
    for symbol in watchlist_symbols:
        try:
            df = twelvedata_feed.get_candles(symbol, count=2, granularity="M15", force_refresh=False)
            if not df.empty and len(df) >= 1:
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) >= 2 else latest
                current_price = float(latest["close"])
                prev_price = float(prev["close"])
                change = current_price - prev_price
                change_pct = (change / prev_price * 100.0) if prev_price > 0 else 0.0
                
                quotes.append({
                    "symbol": symbol,
                    "display": symbol.replace("_", "/"),
                    "price": current_price,
                    "change": round(change, 5),
                    "change_pct": round(change_pct, 2),
                    "high": float(latest["high"]),
                    "low": float(latest["low"]),
                    "volume": float(latest.get("volume", 0) or 0),
                    "time": latest["time"].strftime('%H:%M:%S UTC')
                })
        except Exception as e:
            quotes.append({
                "symbol": symbol,
                "display": symbol.replace("_", "/"),
                "price": 0.0,
                "change": 0.0,
                "change_pct": 0.0,
                "high": 0.0,
                "low": 0.0,
                "volume": 0.0,
                "time": "Error"
            })
    return quotes

@app.post("/api/analyze")
def analyze_chart(req: AnalyzeRequestSchema):
    min_fib = 3.0
    if "EUR_USD" in req.instrument:
        min_fib = 0.0030
    elif "GBP_USD" in req.instrument:
        min_fib = 0.0035
    elif "USD_JPY" in req.instrument:
        min_fib = 0.30
    elif "XAU_USD" in req.instrument:
        min_fib = 3.0
    else:
        min_fib = 0.0030

    class ConfigMock:
        pass
        
    cfg_mock = ConfigMock()
    for attr in dir(cfg):
        if attr.isupper():
            setattr(cfg_mock, attr, getattr(cfg, attr))
            
    cfg_mock.MIN_SWING_SIZE = 0.0
    cfg_mock.MIN_FIB_RANGE = min_fib
    cfg_mock.LEFT_BARS = 5
    cfg_mock.RIGHT_BARS = 5
    cfg_mock.PRICE_SOURCE = "Wick"
    cfg_mock.SIGNAL_LEVEL = "0.618"
    cfg_mock.BULL_TP_LEVEL = "0"
    cfg_mock.BULL_SL_LEVEL = "1"
    cfg_mock.BEAR_TP_LEVEL = "0"
    cfg_mock.BEAR_SL_LEVEL = "1"
    cfg_mock._current_instrument = req.instrument
    cfg_mock.MIN_FIB_RANGE_OVERRIDES = {}
    cfg_mock.CANDLE_HISTORY_COUNT = req.count

    try:
        df = twelvedata_feed.get_candles(
            req.instrument,
            count=req.count,
            granularity=req.granularity,
            force_refresh=False
        )
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Twelve Data returned no candle data.")

        if req.strategy_type == "MomentumBreakout":
            events = breakout_strategy.run_strategy(df, cfg_mock)
        elif req.strategy_type == "AIClaude":
            events = ai_strategy.run_strategy(df, cfg_mock)
        else:
            events = fib_strategy.run_strategy(df, cfg_mock)

        chart_candles = []
        volume_series = []
        for _, row in df.iterrows():
            unix_time = int(row["time"].timestamp())
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            v = float(row.get("volume", 0) or 0)
            
            chart_candles.append({
                "time": unix_time,
                "datetime": row["time"].strftime('%Y-%m-%d %H:%M UTC'),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v
            })
            
            volume_series.append({
                "time": unix_time,
                "value": v,
                "color": "rgba(8, 153, 129, 0.35)" if c >= o else "rgba(242, 54, 69, 0.35)"
            })

        signals = []
        for e in events:
            signals.append({
                "kind": e.kind,
                "time": int(e.time.timestamp()),
                "datetime": e.time.strftime('%Y-%m-%d %H:%M UTC'),
                "price": float(e.price),
                "tp": float(e.tp) if e.tp else None,
                "sl": float(e.sl) if e.sl else None,
                "fib_low": float(e.fib_low) if hasattr(e, 'fib_low') else None,
                "fib_high": float(e.fib_high) if hasattr(e, 'fib_high') else None
            })

        reasoning = None
        if req.strategy_type == "AIClaude":
            reasoning = ai_strategy.get_last_reasoning()

        latest_close = float(df.iloc[-1]["close"])
        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else latest_close
        price_diff = latest_close - prev_close
        price_diff_pct = (price_diff / prev_close * 100.0) if prev_close > 0 else 0.0

        # Latest Fib bounds if applicable
        last_event = events[-1] if events else None
        fib_bounds = None
        if last_event and hasattr(last_event, 'fib_low') and last_event.fib_low > 0:
            fib_bounds = {
                "low": last_event.fib_low,
                "high": last_event.fib_high,
                "tp": last_event.tp,
                "sl": last_event.sl
            }

        return {
            "instrument": req.instrument,
            "display_symbol": req.instrument.replace("_", "/"),
            "granularity": req.granularity,
            "strategy_type": req.strategy_type,
            "candles": chart_candles,
            "volume": volume_series,
            "signals": signals,
            "reasoning": reasoning,
            "fib_bounds": fib_bounds,
            "market_summary": {
                "price": latest_close,
                "change": round(price_diff, 5),
                "change_pct": round(price_diff_pct, 2),
                "high": float(df["high"].max()),
                "low": float(df["low"].min()),
                "bars": len(df)
            }
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chart analysis error: {str(e)}")

# ============================================================================
# Static Files Routing
# ============================================================================
# Serve SPA
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Start server
    print("Starting Swing Fib Web Dashboard server...")
    print("Navigate to http://localhost:8000 to manage bots.")
    uvicorn.run("dashboard_server:app", host="127.0.0.1", port=8000, log_level="info")
