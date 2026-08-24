const API_BASE = window.location.origin;
const state = {
    strategies: [],
    equityChartInstance: null
};

function showToast(message, type = "info") {
    const container = document.getElementById("tv-toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `tv-toast ${type}`;
    toast.innerHTML = `
        <span class="tv-toast-message">${message}</span>
        <button class="tv-toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

async function fetchBotStatuses() {
    try {
        const resp = await fetch(API_BASE + "/api/status");
        if (!resp.ok) return;
        const bots = await resp.json();
        
        const sideList = document.getElementById("sidebar-bots-list");
        if (sideList) {
            sideList.innerHTML = "";
            if (bots.length === 0) {
                sideList.innerHTML = `<div style="grid-column: 1/-1; padding: 40px 0; text-align: center; color: var(--tv-text-secondary);">No bot workers deployed yet. Use the deployer form on the left to start one!</div>`;
                return;
            }
            bots.forEach(b => {
                const isRunning = b.status === "running";
                const card = document.createElement("div");
                card.className = "bot-card-custom";
                
                card.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 700; color: var(--tv-text-bright); font-size: 13.5px;">${b.name}</span>
                        <span class="badge-signal ${isRunning ? 'buy' : 'sell'}" style="font-size: 9.5px; padding: 3px 8px; border-radius: 3px;">${b.status.toUpperCase()}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--tv-text-primary); margin-bottom: 12px; display: flex; flex-direction: column; gap: 4px;">
                        <div>Instrument: <code style="background: var(--tv-bg-base); padding: 2px 4px; border-radius: 3px;">${b.instrument}</code></div>
                        <div>Granularity: <code style="background: var(--tv-bg-base); padding: 2px 4px; border-radius: 3px;">${b.granularity}</code></div>
                        <div>Error Count: <span class="${b.error_count > 0 ? 'text-red' : ''}" style="font-weight: 600;">${b.error_count}</span></div>
                        <div>Last Run: <span style="color: var(--tv-text-secondary);">${b.last_run ? new Date(b.last_run).toLocaleTimeString() : 'Never'}</span></div>
                    </div>
                    <div style="display: flex; gap: 8px; margin-top: auto;">
                        ${isRunning
                            ? `<button class="tv-btn-secondary btn-block text-red" style="padding: 6px 12px; font-size: 12px; font-weight: 500;" onclick="toggleBotWorker('${b.id}', 'stop')">Stop Worker</button>`
                            : `<button class="tv-btn-primary btn-block" style="padding: 6px 12px; font-size: 12px; font-weight: 500;" onclick="toggleBotWorker('${b.id}', 'start')">Start Worker</button>`
                        }
                    </div>
                `;
                sideList.appendChild(card);
            });
        }
    } catch (e) {
        console.error(e);
        showToast("Failed to fetch bot statuses: " + e.message, "danger");
    }
}

async function toggleBotWorker(stratId, action) {
    try {
        const resp = await fetch(API_BASE + "/api/bot/" + action + "/" + stratId, { method: "POST" });
        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || "Server error");
        }
        showToast(`Bot worker ${action}ped successfully!`, "success");
        fetchBotStatuses();
    } catch (e) {
        showToast(`Failed to ${action} bot worker: ${e.message}`, "danger");
    }
}

async function handleStrategySave(e) {
    e.preventDefault();
    const name = document.getElementById("side-strat-name").value;
    const type = document.getElementById("side-strat-type").value;
    const instrument = document.getElementById("side-strat-instrument").value;
    const granularity = document.getElementById("side-strat-granularity").value;
    const priceSource = document.getElementById("side-strat-price-source").value;
    const telegram = document.getElementById("side-strat-telegram").checked;

    const left = parseInt(document.getElementById("side-strat-left").value) || 5;
    const right = parseInt(document.getElementById("side-strat-right").value) || 5;
    const level = document.getElementById("side-strat-signal-level").value;
    const minFib = parseFloat(document.getElementById("side-strat-min-fib").value) || 0.0030;
    
    const bullTp = document.getElementById("side-strat-bull-tp").value;
    const bullSl = document.getElementById("side-strat-bull-sl").value;
    const bearTp = document.getElementById("side-strat-bear-tp").value;
    const bearSl = document.getElementById("side-strat-bear-sl").value;
    
    const requireAlt = document.getElementById("side-strat-require-alt").checked;
    const recalcExtreme = document.getElementById("side-strat-recalc-extreme").checked;

    const useTrend = document.getElementById("side-strat-use-trend").checked;
    const trendLen = parseInt(document.getElementById("side-strat-trend-len").value) || 50;
    const trendMaType = document.getElementById("side-strat-trend-ma-type").value;

    const useCandle = document.getElementById("side-strat-use-candle").checked;
    const candleType = document.getElementById("side-strat-candle-type").value;
    const wickRatio = parseFloat(document.getElementById("side-strat-wick-ratio").value) || 0.5;

    const useTimeFilter = document.getElementById("side-strat-use-time-filter").checked;
    const startHour = parseInt(document.getElementById("side-strat-start-hour").value) || 8;
    const startMinute = parseInt(document.getElementById("side-strat-start-minute").value) || 0;
    const endHour = parseInt(document.getElementById("side-strat-end-hour").value) || 16;
    const endMinute = parseInt(document.getElementById("side-strat-end-minute").value) || 0;

    const useNt1 = document.getElementById("side-strat-use-nt1").checked;
    const useConsolidation = document.getElementById("side-strat-use-consolidation").checked;

    const payload = {
        id: "strat_" + Math.random().toString(36).substr(2, 9),
        status: "active",
        name: name,
        instrument: instrument,
        granularity: granularity,
        telegram_enabled: telegram,
        price_source: priceSource,
        signal_level: level,
        strategy_type: type,
        bull_tp_level: bullTp,
        bull_sl_level: bullSl,
        bear_tp_level: bearTp,
        bear_sl_level: bearSl,
        left_bars: left,
        right_bars: right,
        min_swing_size: 0.0,
        min_fib_range: minFib,
        min_bars_between_swings: 1,
        require_alternating_swings: requireAlt,
        recalculate_on_extreme: recalcExtreme,
        use_time_filter: useTimeFilter,
        start_hour: startHour,
        start_minute: startMinute,
        end_hour: endHour,
        end_minute: endMinute,
        use_no_trade_1: useNt1,
        nt1_start_hour: 9,
        nt1_start_minute: 30,
        nt1_end_hour: 10,
        nt1_end_minute: 0,
        use_no_trade_2: false,
        nt2_start_hour: 0,
        nt2_start_minute: 0,
        nt2_end_hour: 0,
        nt2_end_minute: 0,
        use_trend_filter: useTrend,
        trend_ma_type: trendMaType,
        trend_length: trendLen,
        trend_slope_bars: 5,
        minimum_slope: 0.0,
        use_candle_confirmation: useCandle,
        confirmation_type: candleType,
        minimum_wick_ratio: wickRatio,
        use_consolidation_filter: useConsolidation,
        consolidation_length: 20,
        consolidation_atr_length: 14,
        max_consolidation_atr: 3.0
    };

    try {
        const resp = await fetch(API_BASE + "/api/strategies", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || "Server error");
        }
        showToast("Configuration saved and live worker deployed!", "success");
        fetchBotStatuses();
    } catch (err) {
        showToast("Error saving: " + err.message, "danger");
    }
}

async function handleQuickStrategySave(e) {
    e.preventDefault();
    const name = document.getElementById("quick-strat-name").value;
    const left = parseInt(document.getElementById("quick-strat-left").value);
    const right = parseInt(document.getElementById("quick-strat-right").value);
    const level = document.getElementById("quick-strat-signal-level").value;
    const minFib = parseFloat(document.getElementById("quick-strat-min-fib").value);
    const trend = document.getElementById("quick-strat-trend").checked;
    const candle = document.getElementById("quick-strat-candle").checked;
    const telegram = document.getElementById("quick-strat-telegram").checked;

    const payload = {
        id: "strat_" + Math.random().toString(36).substr(2, 9),
        status: "active",
        name: name,
        instrument: "EUR_USD",
        granularity: "M15",
        telegram_enabled: telegram,
        price_source: "Wick",
        signal_level: level,
        strategy_type: "Fibonacci",
        bull_tp_level: "0", bull_sl_level: "1", bear_tp_level: "0", bear_sl_level: "1",
        left_bars: left, right_bars: right, min_swing_size: 0.0, min_fib_range: minFib,
        min_bars_between_swings: 1, require_alternating_swings: true, recalculate_on_extreme: false,
        use_time_filter: false, start_hour: 8, start_minute: 0, end_hour: 16, end_minute: 0,
        use_no_trade_1: true, nt1_start_hour: 9, nt1_start_minute: 30, nt1_end_hour: 10, nt1_end_minute: 0,
        use_no_trade_2: false, nt2_start_hour: 0, nt2_start_minute: 0, nt2_end_hour: 0, nt2_end_minute: 0,
        use_trend_filter: trend, trend_ma_type: "SMA", trend_length: 50, trend_slope_bars: 5, minimum_slope: 0.0,
        use_candle_confirmation: candle, confirmation_type: "Rejection Candle", minimum_wick_ratio: 0.5,
        use_consolidation_filter: false, consolidation_length: 20, consolidation_atr_length: 14, max_consolidation_atr: 3.0
    };

    try {
        const resp = await fetch(API_BASE + "/api/strategies", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || "Server error");
        }
        showToast("Quick Bot deployed successfully!", "success");
        fetchBotStatuses();
    } catch (err) {
        showToast("Error saving quick config: " + err.message, "danger");
    }
}

// Bind events
document.getElementById("tv-sidebar-strategy-form").addEventListener("submit", handleStrategySave);

const quickForm = document.getElementById("tv-quick-strategy-form");
if (quickForm) {
    quickForm.addEventListener("submit", handleQuickStrategySave);
}

document.getElementById("btn-refresh-bots").addEventListener("click", () => {
    fetchBotStatuses();
    showToast("Refreshed active worker status.", "info");
});

// Deployer Tab Switching
const btnTabQuick = document.getElementById("btn-tab-quick");
const btnTabAdvanced = document.getElementById("btn-tab-advanced");
const paneDeployQuick = document.getElementById("pane-deploy-quick");
const paneDeployAdvanced = document.getElementById("pane-deploy-advanced");

if (btnTabQuick && btnTabAdvanced) {
    btnTabQuick.addEventListener("click", () => {
        btnTabQuick.classList.add("active");
        btnTabAdvanced.classList.remove("active");
        paneDeployQuick.style.display = "flex";
        paneDeployAdvanced.style.display = "none";
    });
    btnTabAdvanced.addEventListener("click", () => {
        btnTabAdvanced.classList.add("active");
        btnTabQuick.classList.remove("active");
        paneDeployAdvanced.style.display = "flex";
        paneDeployQuick.style.display = "none";
    });
}

// Right Panel Tab Switching (Active Bots / Strategy Tester)
const btnTabBots = document.getElementById("btn-tab-bots-list");
const btnTabTester = document.getElementById("btn-tab-tester");
const paneBotsList = document.getElementById("pane-bots-list");
const paneTester = document.getElementById("pane-tester");

if (btnTabBots && btnTabTester) {
    btnTabBots.addEventListener("click", () => {
        btnTabBots.classList.add("active");
        btnTabTester.classList.remove("active");
        paneBotsList.style.display = "flex";
        paneTester.style.display = "none";
    });
    btnTabTester.addEventListener("click", () => {
        btnTabTester.classList.add("active");
        btnTabBots.classList.remove("active");
        paneTester.style.display = "flex";
        paneBotsList.style.display = "none";
        // Re-fit Chart if instance exists
        if (state.equityChartInstance) {
            state.equityChartInstance.resize();
        }
    });
}

// ============================================================================
// STRATEGY TESTER ENGINE
// ============================================================================
async function fetchStrategies() {
    try {
        const resp = await fetch(API_BASE + "/api/strategies");
        if (!resp.ok) return;
        const strats = await resp.json();
        state.strategies = strats;
        
        // Populate strategy dropdown
        const btSelect = document.getElementById("bt-dock-strategy");
        if (btSelect) {
            btSelect.innerHTML = "";
            strats.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s.id;
                opt.textContent = s.name + " (" + s.instrument + ")";
                btSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error(e);
    }
}

async function runDockBacktest() {
    const stratId = document.getElementById("bt-dock-strategy").value;
    if (!stratId) {
        showToast("Please create/deploy a strategy first to run backtests.", "warning");
        return;
    }
    const count = parseInt(document.getElementById("bt-dock-count").value) || 300;
    const btn = document.getElementById("btn-dock-run-backtest");

    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;"></i> Testing...`;
    if (window.lucide) lucide.createIcons();

    // Find the strategy configuration to resolve instrument/granularity
    const stratConfig = state.strategies.find(s => s.id === stratId);
    const instrument = stratConfig ? stratConfig.instrument : "EUR_USD";
    const granularity = stratConfig ? stratConfig.granularity : "M15";

    try {
        const resp = await fetch(API_BASE + "/api/backtest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                strategy_id: stratId,
                count: count,
                instrument: instrument,
                granularity: granularity,
                force_refresh: false
            })
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Backtest failed.");
        }

        const data = await resp.json();
        renderBacktestDockResults(data);
        showToast("Backtest simulation completed!", "success");
    } catch (e) {
        showToast("Backtest execution error: " + e.message, "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="play" style="width:14px;height:14px;"></i> Run Backtest`;
        if (window.lucide) lucide.createIcons();
    }
}

function renderBacktestDockResults(data) {
    const m = data.metrics;
    
    if (data.period) {
        document.getElementById("dock-period-range").textContent = data.period.start + " → " + data.period.end + " (" + data.period.bars + " bars)";
    }

    const netProfitEl = document.getElementById("dock-net-profit");
    netProfitEl.textContent = (m.net_profit_pct >= 0 ? "+" : "") + m.net_profit_pct.toFixed(2) + "%";
    netProfitEl.className = "m-val " + (m.net_profit_pct >= 0 ? "text-green" : "text-red");

    const pipsEl = document.getElementById("dock-net-pips");
    pipsEl.textContent = (m.net_pips >= 0 ? "+" : "") + m.net_pips.toFixed(1) + " pips";
    pipsEl.className = "m-sub " + (m.net_pips >= 0 ? "text-green" : "text-red");

    const pfEl = document.getElementById("dock-profit-factor");
    pfEl.textContent = m.profit_factor >= 99 ? "∞" : m.profit_factor.toFixed(2);
    pfEl.className = "m-val " + (m.profit_factor >= 1.0 ? "text-green" : "text-red");

    document.getElementById("dock-win-rate").textContent = m.win_rate + "%";
    document.getElementById("dock-win-loss").textContent = m.wins + " W / " + m.losses + " L";
    document.getElementById("dock-max-drawdown").textContent = m.max_drawdown_pct.toFixed(2) + "%";
    document.getElementById("dock-total-trades").textContent = m.total_trades;
    document.getElementById("dock-open-trades").textContent = m.open_trades + " Open";

    // Render Simulated Trades Table
    const tbody = document.getElementById("dock-trades-tbody");
    tbody.innerHTML = "";

    if (!data.trades || data.trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="padding: 20px; text-align: center; color: var(--tv-text-secondary);">No simulated trades generated. Try increasing bars or adjusting swing thresholds.</td></tr>`;
    } else {
        data.trades.forEach((t, i) => {
            const tr = document.createElement("tr");
            const badgeClass = t.type === "BUY" ? "buy" : "sell";
            const outcomeClass = t.outcome === "WIN" ? "text-green" : (t.outcome === "LOSS" ? "text-red" : "text-muted");
            const pnlClass = t.pnl_pct >= 0 ? "text-green" : "text-red";
            const pipsClass = t.pips >= 0 ? "text-green" : "text-red";

            tr.innerHTML = `
                <td style="padding: 10px;">${i + 1}</td>
                <td style="padding: 10px;"><span class="badge-signal ${badgeClass}">${t.type}</span></td>
                <td style="padding: 10px;"><small>${t.entry_time}</small></td>
                <td style="padding: 10px;"><code>${t.entry_price.toFixed(5)}</code></td>
                <td style="padding: 10px;"><code>${t.tp.toFixed(5)}</code></td>
                <td style="padding: 10px;"><code>${t.sl.toFixed(5)}</code></td>
                <td style="padding: 10px;"><small>${t.exit_time}</small></td>
                <td style="padding: 10px;" class="${outcomeClass}"><strong>${t.outcome}</strong></td>
                <td style="padding: 10px;" class="${pipsClass}"><code>${(t.pips >= 0 ? "+" : "") + t.pips.toFixed(1)}</code></td>
                <td style="padding: 10px;" class="${pnlClass}"><strong>${(t.pnl_pct >= 0 ? "+" : "") + t.pnl_pct.toFixed(3)}%</strong></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Render Equity Curve Growth Chart
    renderDockEquityCurve(data.trades);
}

function renderDockEquityCurve(trades) {
    const canvas = document.getElementById("dock-equity-chart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    if (state.equityChartInstance) {
        state.equityChartInstance.destroy();
    }

    const labels = ["Start"];
    const values = [0.0];
    trades.forEach((t, idx) => {
        labels.push("T" + (idx + 1));
        values.push(t.cumulative_pnl_pct);
    });

    const gradient = ctx.createLinearGradient(0, 0, 0, 150);
    gradient.addColorStop(0, "rgba(8, 153, 129, 0.35)");
    gradient.addColorStop(1, "rgba(8, 153, 129, 0.0)");

    state.equityChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: "Cumulative PnL (%)",
                data: values,
                borderColor: "#089981",
                borderWidth: 2,
                backgroundColor: gradient,
                fill: true,
                tension: 0.2,
                pointRadius: values.length < 40 ? 3 : 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#1e222d",
                    titleColor: "#f0f3fa",
                    bodyColor: "#d1d4dc",
                    borderColor: "#2a2e39",
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { color: "rgba(255, 255, 255, 0.02)" },
                    ticks: { color: "#787b86", font: { size: 10 } }
                },
                y: {
                    grid: { color: "rgba(255, 255, 255, 0.04)" },
                    ticks: { color: "#787b86", font: { size: 10 }, callback: v => v.toFixed(1) + "%" }
                }
            }
        }
    });
}

// Bind backtester button
const btnBacktest = document.getElementById("btn-dock-run-backtest");
if (btnBacktest) {
    btnBacktest.addEventListener("click", runDockBacktest);
}

// Initial fetch
fetchBotStatuses();
fetchStrategies();

// Auto refresh every 5 seconds
setInterval(fetchBotStatuses, 5000);
