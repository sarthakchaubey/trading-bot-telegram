# Swing Fibonacci Telegram Alert Bot

A Python port of the Pine Script "Swing Fibonacci Strategy" that watches
forex pairs and XAU/USD via OANDA's free API, replays the same swing /
Fibonacci / signal logic bar-by-bar, and pushes BUY/SELL alerts (with TP
and SL) to a Telegram chat. It does **not** place real trades — alerts only.

## 1. Get OANDA API access (free)

1. Create a free practice account: https://www.oanda.com/apply/demo/
2. In the account portal, generate a **Personal Access Token** (this is your `OANDA_API_KEY`).
3. Note your **Account ID** (format like `101-004-1234567-001`), shown on the same page.

## 2. Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts.
2. Copy the token it gives you → `TELEGRAM_BOT_TOKEN`.
3. Send any message to your new bot, then visit:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   and find `"chat":{"id": ...}` → that number is your `TELEGRAM_CHAT_ID`.

## 3. Install

```bash
pip install -r requirements.txt
```

## 4. Configure

Open `config.py` and either edit the values directly or set environment
variables:

```bash
export OANDA_API_KEY="your_token"
export OANDA_ACCOUNT_ID="your_account_id"
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Also review/adjust in `config.py`:
- `INSTRUMENTS` — e.g. `["EUR_USD", "XAU_USD", "GBP_USD"]`
- `GRANULARITY` — `M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D`
- `MIN_FIB_RANGE_OVERRIDES` — **important**: the original script's
  "Minimum Fib Range" of `30.0` is in raw price points. That number means
  something very different for EUR_USD (~1.10) vs XAU_USD (~2400). Tune the
  per-instrument overrides in `config.py` to match how you used this setting
  on TradingView.
- Every other block (time filters, no-trade windows, swing detection,
  fib direction, signal level, TP/SL levels, departure filter, candle
  confirmation, trend filter, consolidation filter) mirrors an `input()`
  from the Pine script one-for-one — same names, same defaults.

## 5. Run

```bash
python main.py
```

The bot will:
1. On startup, silently "catch up" — it won't spam you with every historical
   signal, only the ones from now on.
2. Poll OANDA every `POLL_SECONDS` for the latest closed candles.
3. Replay the strategy over the fetched history.
4. Send a Telegram message for any signal newer than the last one it already sent.

## 6. Run it 24/7

For a bot that needs to run continuously, use a small always-on Linux VPS
(or your own always-on machine) with something like:

```bash
nohup python3 main.py >> bot.log 2>&1 &
```

or set it up as a `systemd` service so it restarts automatically on reboot/crash.

## Notes on fidelity to the original script

- Pivot detection uses the same `left`/`right` bar window as
  `ta.pivothigh`/`ta.pivotlow`, with the same confirmation lag (a pivot at
  bar `i` is only known `right` bars later).
- A signal only fires once per fib, and a new fib only forms once the prior
  one's virtual TP or SL would have been hit — this replicates the original
  strategy's `strategy.position_size == 0` gating without actually trading.
- Time filters use the IANA timezone you set in `TIME_ZONE`, matching Pine's
  `timeZone` input.
- Chart drawing (fib lines, TP/SL boxes, labels) is not reproduced — this is
  an alerting bot, not a charting one. If you also want the visual fib on
  TradingView, keep the original Pine script running there for the chart and
  use this bot purely for phone notifications.
