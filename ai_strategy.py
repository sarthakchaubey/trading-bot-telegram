"""
AI strategy using OpenRouter API to analyze candlestick patterns and generate trading signals.
"""

import os
import json
import requests
import pandas as pd
from typing import List
from strategy import Event

# Global variable to cache the last reasoning to display on the dashboard
last_ai_reasoning = "No AI analysis has run yet. Click 'Update Chart' with Claude AI Analyst strategy selected."

def get_last_reasoning() -> str:
    global last_ai_reasoning
    return last_ai_reasoning

def run_strategy(df: pd.DataFrame, cfg) -> List[Event]:
    global last_ai_reasoning
    
    # Load settings from environment variables (loaded via dotenv in config.py)
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://openrouter.ai/api").strip()
    model = os.getenv("ANTHROPIC_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free").strip()
    
    if not api_key:
        msg = "Error: OpenRouter API key not configured. Please set OPENROUTER_API_KEY or ANTHROPIC_AUTH_TOKEN in your .env file."
        print(f"[AI Strategy] {msg}")
        last_ai_reasoning = msg
        return []
        
    if len(df) < 15:
        msg = f"Error: Not enough candles to analyze. Minimum required is 15, got {len(df)}."
        print(f"[AI Strategy] {msg}")
        last_ai_reasoning = msg
        return []
        
    # Analyze the last 20 candles
    candles_to_analyze = df.tail(20)
    
    candle_list = []
    for idx, row in candles_to_analyze.iterrows():
        candle_list.append({
            "time": row["time"].strftime("%Y-%m-%d %H:%M UTC") if isinstance(row["time"], pd.Timestamp) else str(row["time"]),
            "open": round(float(row["open"]), 5),
            "high": round(float(row["high"]), 5),
            "low": round(float(row["low"]), 5),
            "close": round(float(row["close"]), 5),
            "volume": int(row["volume"]) if "volume" in row and not pd.isna(row["volume"]) else 0
        })
        
    instrument = getattr(cfg, "_current_instrument", "Asset")
    granularity = getattr(cfg, "GRANULARITY", "Unknown")
    
    prompt = f"""You are a master quantitative trader and technical analyst.
Analyze the following last 20 OHLCV candles for {instrument} on the {granularity} timeframe:

{json.dumps(candle_list, indent=2)}

Look for standard candlestick patterns (like engulfing, pinbars, dojis), support/resistance levels, trend directions (higher highs, lower lows), momentum indicators, and volume expansions.
Determine if there is a high-probability entry signal (BUY, SELL, or HOLD) at the CLOSE of the last candle.

You MUST respond strictly in the following JSON format:
{{
    "signal": "BUY" | "SELL" | "HOLD",
    "price": <close price of the last candle as float>,
    "tp": <suggested take profit target price as float or null if HOLD>,
    "sl": <suggested stop loss target price as float or null if HOLD>,
    "reasoning": "<brief paragraph explanation of your technical analysis, support/resistance levels, and observations>"
}}
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/google/antigravity", # Optional referer for OpenRouter
        "X-Title": "Antigravity Trading Bot"
    }
    
    url = base_url
    if not url.endswith("/chat/completions"):
        if url.endswith("/"):
            url += "v1/chat/completions"
        else:
            url += "/v1/chat/completions"
            
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    
    print(f"[AI Strategy] Querying model {model} via {url} for {instrument} {granularity}...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        res_data = response.json()
        
        if "choices" not in res_data or len(res_data["choices"]) == 0:
            raise RuntimeError(f"Invalid API response structure: {res_data}")
            
        content = res_data["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        signal = result.get("signal", "HOLD").upper()
        reasoning = result.get("reasoning", "No reasoning provided.")
        last_ai_reasoning = f"[{model}] {reasoning}"
        
        print(f"[AI Strategy] Model result: {signal} at {result.get('price')}. Reasoning: {reasoning[:120]}...")
        
        if signal in ["BUY", "SELL"]:
            last_candle = df.iloc[-1]
            entry_price = float(result.get("price") or last_candle["close"])
            
            # Simple logical fallbacks for TP/SL if model returned null/incorrect values
            default_tp = entry_price * 1.01 if signal == "BUY" else entry_price * 0.99
            default_sl = entry_price * 0.995 if signal == "BUY" else entry_price * 1.005
            
            tp = float(result.get("tp") or default_tp)
            sl = float(result.get("sl") or default_sl)
            
            event = Event(
                kind=signal,
                time=last_candle["time"],
                price=entry_price,
                tp=tp,
                sl=sl,
                fib_high=max(entry_price, tp, sl),
                fib_low=min(entry_price, tp, sl)
            )
            # Dynamically set reasoning attribute
            setattr(event, 'reasoning', reasoning)
            return [event]
            
    except Exception as e:
        error_msg = f"Failed to generate AI signal. Error: {e}"
        print(f"[AI Strategy] {error_msg}")
        last_ai_reasoning = error_msg
        
    return []
