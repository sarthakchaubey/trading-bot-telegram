"""
Configuration for the Swing Fibonacci Telegram Alert Bot.

Fill in your OANDA and Telegram credentials below, then adjust the
STRATEGY settings to match the inputs you used on the Pine Script
version. Every setting here maps 1:1 to an input() in the original
TradingView strategy.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================================
# Twelve Data (data source)
# ============================================================================
# Free account -> https://twelvedata.com
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "PUT_YOUR_TWELVE_DATA_API_KEY_HERE")

# Instruments to watch, using OANDA's naming convention.
# Examples: "EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"
INSTRUMENTS = ["EUR_USD", "XAU_USD"]

# OANDA granularity codes: M1, M5, M15, M30, H1, H4, D
GRANULARITY = "M15"

# How often (seconds) the bot polls Twelve Data for a newly closed candle.
POLL_SECONDS = 60

# ============================================================================
# TELEGRAM
# ============================================================================
# Create a bot with @BotFather, then message your bot once and hit
# https://api.telegram.org/bot<token>/getUpdates to find your chat_id.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "PUT_YOUR_TELEGRAM_CHAT_ID_HERE")

# ============================================================================
# 01 - TIME SETTINGS
# ============================================================================
USE_TIME_FILTER = False
START_HOUR, START_MINUTE = 8, 0
END_HOUR, END_MINUTE = 16, 0
TIME_ZONE = "America/New_York"  # any IANA tz name

# ============================================================================
# 02/03 - NO TRADE WINDOWS
# ============================================================================
USE_NO_TRADE_1 = True
NT1_START_HOUR, NT1_START_MINUTE = 9, 30
NT1_END_HOUR, NT1_END_MINUTE = 10, 0

USE_NO_TRADE_2 = False
NT2_START_HOUR, NT2_START_MINUTE = 11, 30
NT2_END_HOUR, NT2_END_MINUTE = 12, 30

# ============================================================================
# 04 - SWING DETECTION
# ============================================================================
LEFT_BARS = 5
RIGHT_BARS = 5
MIN_SWING_SIZE = 0.0
MIN_FIB_RANGE = 30.0          # NOTE: in Pine-strategy "points" of the source symbol.
                               # For FX pairs you likely want something like 0.0030,
                               # for XAU_USD something like 3.0. Tune per instrument
                               # using the per-instrument overrides below.
MIN_BARS_BETWEEN_SWINGS = 1
PRICE_SOURCE = "Wick"         # "Wick" or "Body"

# Per-instrument override for MIN_FIB_RANGE (recommended, since pips/points
# differ hugely between e.g. EUR_USD and XAU_USD).
MIN_FIB_RANGE_OVERRIDES = {
    "EUR_USD": 0.0030,
    "GBP_USD": 0.0035,
    "USD_JPY": 0.30,
    "XAU_USD": 3.0,
}

# ============================================================================
# 05 - FIB DIRECTION
# ============================================================================
FIB_DIRECTION = "Follow Trend"   # "Follow Trend" | "Both Directions" | "Bullish Only" | "Bearish Only"
REQUIRE_ALTERNATING_SWINGS = True

# ============================================================================
# 06 - FIB STRUCTURE
# ============================================================================
RECALCULATE_ON_EXTREME = False

# ============================================================================
# 11 - SIGNAL SETTINGS
# ============================================================================
ENABLE_SIGNALS = True
SIGNAL_LEVEL = "0.618"   # one of "0","0.25","0.5","0.618","0.786","0.9","1"

# ============================================================================
# 12 - TP / SL FIB LEVELS
# ============================================================================
BULL_TP_LEVEL = "0"
BULL_SL_LEVEL = "1"
BEAR_TP_LEVEL = "0"
BEAR_SL_LEVEL = "1"

# ============================================================================
# 13 - MINIMUM DEPARTURE FILTER
# ============================================================================
USE_DEPARTURE_FILTER = False
DEPARTURE_VALUE = 10.0
DEPARTURE_MODE = "Points"   # "Points" or "Percent"

# ============================================================================
# 14 - CANDLE CONFIRMATION
# ============================================================================
USE_CANDLE_CONFIRMATION = False
CONFIRMATION_TYPE = "Rejection Candle"  # "Touch Only" | "Close Confirmation" | "Rejection Candle" | "Engulfing Candle"
MINIMUM_WICK_RATIO = 0.5

# ============================================================================
# 15 - TREND FILTER
# ============================================================================
USE_TREND_FILTER = False
TREND_MA_TYPE = "SMA"     # "SMA" or "EMA"
TREND_LENGTH = 50
TREND_SLOPE_BARS = 5
MINIMUM_SLOPE = 0.0

# ============================================================================
# 16 - CONSOLIDATION FILTER
# ============================================================================
USE_CONSOLIDATION_FILTER = False
CONSOLIDATION_LENGTH = 20
CONSOLIDATION_ATR_LENGTH = 14
MAX_CONSOLIDATION_ATR = 3.0

# How many historical candles to fetch on each poll (needs to comfortably
# cover MA/ATR lookback + swing detection window).
CANDLE_HISTORY_COUNT = max(300, TREND_LENGTH + CONSOLIDATION_LENGTH + 100)
