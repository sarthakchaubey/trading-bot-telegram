# Guide: Adding and Writing Custom Strategies

This guide details how to add a new strategy configuration via the web dashboard and how to write a custom technical strategy in Python.

---

## 1. Adding a New Strategy Preset via Web UI (No Coding)

If you want to create a new instance of the **Swing Fibonacci** strategy (e.g., watching a different instrument or changing the swing lookback parameters):

1. Open the Web Dashboard: `http://localhost:8000`.
2. Click **New Strategy** (in the header or sidebar).
3. Fill in the parameters:
   * **General**: Give it a name (e.g., `GBP/USD H1 Standard`), choose the instrument (e.g., `GBP_USD`), choose granularity (e.g., `H1`), and set the target TP/SL levels.
   * **Pivot & Fib**: Define the pivot lookback window (`Left Pivot Bars` & `Right Pivot Bars`) and change the `Min Fib Range` (e.g., for `GBP_USD` you want `0.0035`).
   * **Filters & Times**: Toggle the Trend Filter, Time Windows, or Candle Confirmation filters if desired.
4. Click **Save Configuration**. The strategy is written to `strategies.json` and immediately shows up on your dashboard.
5. You can now:
   * Run a quick historical backtest on it.
   * Click **Play** to start live polling and alerting on Telegram.

---

## 2. Writing a Custom Technical Strategy in Python (Coding)

If you want to implement a completely new technical strategy (e.g. Moving Average crossover, RSI, MACD, etc.):

### Step A: Implement your Logic in a Python file
We have created a template file for you: [`custom_strategy_template.py`](file:///c:/Users/sarth/Downloads/bot%2004/custom_strategy_template.py).
1. Copy or edit `custom_strategy_template.py`.
2. Modify the indicators calculations and trigger rules inside `run_strategy(df, cfg)`.
3. Ensure it returns a list of standard `Event` objects, containing:
   * `kind`: `"BUY"` or `"SELL"`
   * `time`: Time stamp of the trigger candle
   * `price`: Entry price
   * `tp`: Take Profit price target
   * `sl`: Stop Loss price target

### Step B: Wire it into the Dashboard Server
To let the web dashboard execute your new strategy instead of the default Fibonacci one:

1. Open [`dashboard_server.py`](file:///c:/Users/sarth/Downloads/bot%2004/dashboard_server.py).
2. Import your new strategy module:
   ```python
   import custom_strategy_template as custom_strat
   ```
3. Locate where `run_strategy` is called inside `dashboard_server.py` (which occurs in two locations: `_run_loop` for live workers and `run_backtest` for the backtester).
4. Update the call to execute your custom module:
   * **In `BotWorker._run_loop`**:
     ```python
     # Replace: events = run_strategy(df, cfg_mock)
     events = custom_strat.run_strategy(df, cfg_mock)
     ```
   * **In `run_backtest`**:
     ```python
     # Replace: events = run_strategy(df, cfg_mock)
     events = custom_strat.run_strategy(df, cfg_mock)
     ```
5. Restart the dashboard server (`python dashboard_server.py`) to apply the changes.

*Tip: If you want to support multiple strategy types dynamically, you can add a `"strategy_type"` field in `strategies.json` and use an `if/else` statement in `dashboard_server.py` to route to `run_strategy` or `custom_strat.run_strategy`!*
