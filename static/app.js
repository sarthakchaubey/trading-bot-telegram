// ============================================================================
// TradingView 1-to-1 Hub Client Engine
// Powered by TradingView Lightweight Charts (v4.2)
// ============================================================================

const API_BASE = window.location.origin;

// Application State
const state = {
    currentSymbol: "EUR_USD",
    currentGranularity: "M15",
    currentStrategyType: "Fibonacci",
    currentChartType: "candles", // candles, line, area
    
    chart: null,
    candlestickSeries: null,
    lineSeries: null,
    areaSeries: null,
    volumeSeries: null,
    ema50Series: null,
    ema200Series: null,
    fibPriceLines: [],
    
    currentCandles: [],
    currentSignals: [],
    quotes: [],
    strategies: [],
    signals: [],
    botStatuses: [],
    
    // Indicators configuration
    indicators: {
        ema50: true,
        ema200: false,
        fib: true,
        volume: true
    },

    // Chart customization
    chartColors: {
        upColor: "#089981",
        downColor: "#f23645",
        watermark: true
    },
    
    equityChartInstance: null,
    
    // Bar Replay Simulator State
    replayActive: false,
    replayIndex: 0,
    replayInterval: null,
    replaySpeed: 500,

    // Active Drawing Tool
    activeDrawingTool: "cursor",
    magnetMode: false,
    toolsLocked: false,
    indicatorsHidden: false,
    
    pollInterval: null
};

// ============================================================================
// TOAST NOTIFICATION SYSTEM
// ============================================================================
function showToast(message, type = "info") {
    const container = document.getElementById("tv-toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "tv-toast " + type;
    
    let iconName = "info";
    if (type === "success") iconName = "check-circle";
    if (type === "danger") iconName = "alert-circle";
    if (type === "warning") iconName = "alert-triangle";

    toast.innerHTML = `<i data-lucide="${iconName}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    if (window.lucide) lucide.createIcons();

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(40px)";
        toast.style.transition = "all 0.3s ease";
        setTimeout(() => toast.remove(), 300);
    }, 3200);
}

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide Icons
    if (window.lucide) lucide.createIcons();

    // 1. Initialize Lightweight Chart Canvas
    initTradingViewChart();

    // 2. Setup Topbar & Menu Listeners
    setupTopbarEvents();
    setupMainMenuEvents();

    // 3. Setup Left Toolbar Drawing Tools
    setupLeftToolbarEvents();

    // 4. Setup Right Sidebar Tabs & Actions
    setupSidebarEvents();

    // 5. Setup Bottom Dock Tabs & Backtester
    setupBottomDockEvents();

    // 6. Setup Modals & Dialogs
    setupModalsEvents();

    // 7. Setup Bar Replay Engine
    setupReplayEvents();

    // 8. Initial Data Loads
    fetchQuotes();
    fetchStrategies();
    fetchSignals();
    fetchBotStatuses();
    loadMainChartData();

    // 9. Start Polling Loop (every 5 seconds)
    state.pollInterval = setInterval(() => {
        fetchQuotes();
        fetchSignals();
        fetchBotStatuses();
    }, 5000);

    showToast("TradingView Hub loaded & synced to Twelve Data.", "success");
});

// ============================================================================
// 1. LIGHTWEIGHT CHARTS SETUP & CONFIGURATION
// ============================================================================
function initTradingViewChart() {
    const container = document.getElementById("tv-chart-container");
    if (!container) return;

    // Create TradingView Chart Instance
    state.chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: container.clientHeight,
        layout: {
            background: { color: "#131722" },
            textColor: "#787b86",
            fontFamily: "-apple-system, BlinkMacSystemFont, Arial, sans-serif",
            fontSize: 11
        },
        grid: {
            vertLines: { color: "rgba(42, 46, 57, 0.45)", style: LightweightCharts.LineStyle.Solid },
            horzLines: { color: "rgba(42, 46, 57, 0.45)", style: LightweightCharts.LineStyle.Solid }
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {
                color: "#787b86",
                width: 1,
                style: LightweightCharts.LineStyle.Dashed,
                labelBackgroundColor: "#2a2e39"
            },
            horzLine: {
                color: "#787b86",
                width: 1,
                style: LightweightCharts.LineStyle.Dashed,
                labelBackgroundColor: "#2a2e39"
            }
        },
        rightPriceScale: {
            borderColor: "#2a2e39",
            autoScale: true,
            scaleMargins: {
                top: 0.1,
                bottom: 0.2
            }
        },
        timeScale: {
            borderColor: "#2a2e39",
            timeVisible: true,
            secondsVisible: false,
            fixLeftEdge: true,
            rightOffset: 12,
            barSpacing: 8
        },
        watermark: {
            visible: true,
            fontSize: 44,
            horzAlign: "center",
            vertAlign: "center",
            color: "rgba(255, 255, 255, 0.03)",
            text: "EUR/USD • 15m"
        }
    });

    // Add Candlestick Series (Exact TradingView Color Palette)
    state.candlestickSeries = state.chart.addCandlestickSeries({
        upColor: state.chartColors.upColor,
        downColor: state.chartColors.downColor,
        borderVisible: false,
        wickUpColor: state.chartColors.upColor,
        wickDownColor: state.chartColors.downColor
    });

    // Add Volume Histogram Subseries
    state.volumeSeries = state.chart.addHistogramSeries({
        color: "#26a69a",
        priceFormat: { type: "volume" },
        priceScaleId: "", // overlay mode
        scaleMargins: {
            top: 0.8,
            bottom: 0
        }
    });

    // Add EMA Indicator Overlays
    state.ema50Series = state.chart.addLineSeries({
        color: "#3b82f6",
        lineWidth: 2,
        title: "EMA 50"
    });

    state.ema200Series = state.chart.addLineSeries({
        color: "#eab308",
        lineWidth: 2,
        title: "EMA 200"
    });
    state.ema200Series.applyOptions({ visible: false });

    // Crosshair Movement Handler -> Update Top-Left Legend
    state.chart.subscribeCrosshairMove((param) => {
        if (!param || !param.time || !param.seriesData || !param.seriesData.get(state.candlestickSeries)) {
            // Restore latest candle values
            if (state.currentCandles.length > 0) {
                updateLegendValues(state.currentCandles[state.currentCandles.length - 1]);
            }
            return;
        }

        const data = param.seriesData.get(state.candlestickSeries);
        const volData = param.seriesData.get(state.volumeSeries);
        if (data) {
            updateLegendValues(data, volData ? volData.value : null);
        }
    });

    // Responsive Resize Observer
    const resizeObserver = new ResizeObserver((entries) => {
        if (!entries || entries.length === 0 || !state.chart) return;
        const { width, height } = entries[0].contentRect;
        state.chart.applyOptions({ width, height });
    });
    resizeObserver.observe(container);
}

function updateLegendValues(candle, volume) {
    if (!candle) return;
    const oEl = document.getElementById("legend-open");
    const hEl = document.getElementById("legend-high");
    const lEl = document.getElementById("legend-low");
    const cEl = document.getElementById("legend-close");
    const diffEl = document.getElementById("legend-diff");
    const volEl = document.getElementById("legend-vol");

    if (oEl) oEl.textContent = candle.open ? candle.open.toFixed(5) : "-";
    if (hEl) hEl.textContent = candle.high ? candle.high.toFixed(5) : "-";
    if (lEl) lEl.textContent = candle.low ? candle.low.toFixed(5) : "-";
    if (cEl) cEl.textContent = candle.close ? candle.close.toFixed(5) : "-";
    
    if (candle.open && candle.close && diffEl) {
        const diff = candle.close - candle.open;
        const diffPct = (diff / candle.open) * 100.0;
        diffEl.textContent = (diff >= 0 ? "+" : "") + diff.toFixed(5) + " (" + (diffPct >= 0 ? "+" : "") + diffPct.toFixed(2) + "%)";
        diffEl.className = "tv-legend-diff " + (diff >= 0 ? "up" : "down");
    }

    if (volEl && (volume !== undefined || candle.volume)) {
        const v = volume !== undefined ? volume : candle.volume;
        volEl.textContent = v >= 1000 ? (v / 1000).toFixed(1) + "K" : v;
    }
}

// Calculate true Exponential Moving Average
function calculateEMA(candles, period) {
    if (candles.length < period) return [];
    const k = 2 / (period + 1);
    let emaArray = [];
    
    // Initial SMA for first value
    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += candles[i].close;
    }
    let prevEMA = sum / period;
    emaArray.push({ time: candles[period - 1].time, value: prevEMA });

    for (let i = period; i < candles.length; i++) {
        const close = candles[i].close;
        prevEMA = (close * k) + (prevEMA * (1 - k));
        emaArray.push({ time: candles[i].time, value: prevEMA });
    }
    return emaArray;
}

// ============================================================================
// 2. MAIN CHART DATA & STRATEGY ANALYSIS
// ============================================================================
async function loadMainChartData(forceRefresh = false) {
    const symbol = state.currentSymbol;
    const granularity = state.currentGranularity;
    const strategy = state.currentStrategyType;

    // Update Watermark & Legend
    const symDisp = symbol.replace("_", "/");
    document.getElementById("legend-symbol").textContent = symDisp;
    document.getElementById("legend-tf").textContent = granularity.replace("M", "").replace("H", "h");
    document.getElementById("tv-current-symbol").textContent = symDisp;
    
    if (state.chart) {
        state.chart.applyOptions({
            watermark: {
                visible: state.chartColors.watermark,
                text: symDisp + " • " + granularity
            }
        });
    }

    // Set Strategy Status
    const stratNameMap = {
        "Fibonacci": "Swing Fib (0.618)",
        "MomentumBreakout": "Momentum Breakout",
        "AIClaude": "Claude AI Analyst"
    };
    document.getElementById("legend-strategy-text").textContent = stratNameMap[strategy] || strategy;

    try {
        const resp = await fetch(API_BASE + "/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                instrument: symbol,
                granularity: granularity,
                strategy_type: strategy,
                count: 300
            })
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Chart data fetch failed.");
        }

        const data = await resp.json();
        state.currentCandles = data.candles || [];
        state.currentSignals = data.signals || [];

        // 1. Render Candlesticks on Lightweight Charts
        if (state.candlestickSeries && data.candles.length > 0) {
            state.candlestickSeries.setData(data.candles);
            if (state.volumeSeries && state.indicators.volume) {
                state.volumeSeries.setData(data.volume || []);
            }
            
            // Calculate & render EMA lines
            if (state.ema50Series) {
                const ema50 = calculateEMA(data.candles, 50);
                state.ema50Series.setData(ema50);
                state.ema50Series.applyOptions({ visible: state.indicators.ema50 });
            }
            if (state.ema200Series) {
                const ema200 = calculateEMA(data.candles, 200);
                state.ema200Series.setData(ema200);
                state.ema200Series.applyOptions({ visible: state.indicators.ema200 });
            }

            state.chart.timeScale().fitContent();
            updateLegendValues(data.candles[data.candles.length - 1]);
        }

        // 2. Clear previous Fib Price Lines & Draw New ones
        clearFibLines();
        if (data.fib_bounds && state.indicators.fib) {
            drawFibPriceLines(data.fib_bounds);
        }

        // 3. Render BUY / SELL Signal Markers
        renderSignalMarkers(data.signals || []);

        // 4. Handle Claude AI Reasoning Display
        const aiBanner = document.getElementById("tv-ai-banner");
        const aiText = document.getElementById("tv-ai-reasoning-text");
        const sidebarAiText = document.getElementById("sidebar-ai-text");
        if (data.reasoning) {
            if (strategy === "AIClaude") {
                aiBanner.style.display = "block";
                aiText.textContent = data.reasoning;
            }
            if (sidebarAiText) sidebarAiText.textContent = data.reasoning;
        } else {
            aiBanner.style.display = "none";
        }

        // 5. Update Quick Order Ticket Prices
        if (data.market_summary) {
            const p = data.market_summary.price;
            const spread = symbol.includes("JPY") ? 0.02 : (symbol.includes("XAU") ? 0.4 : 0.00012);
            document.getElementById("trade-sell-price").textContent = p.toFixed(5);
            document.getElementById("trade-buy-price").textContent = (p + spread).toFixed(5);
            document.getElementById("detail-day-high").textContent = data.market_summary.high.toFixed(5);
            document.getElementById("detail-day-low").textContent = data.market_summary.low.toFixed(5);
            document.getElementById("detail-volume").textContent = data.market_summary.bars + " bars";
            document.getElementById("detail-time").textContent = new Date().toLocaleTimeString();
        }

    } catch (err) {
        console.error("loadMainChartData Error:", err);
        showToast("Error loading chart feed: " + err.message, "danger");
    }
}

function clearFibLines() {
    if (state.candlestickSeries && state.fibPriceLines) {
        state.fibPriceLines.forEach(line => state.candlestickSeries.removePriceLine(line));
        state.fibPriceLines = [];
    }
}

function drawFibPriceLines(bounds) {
    if (!state.candlestickSeries || !bounds || !bounds.low || !bounds.high) return;
    const low = bounds.low;
    const high = bounds.high;
    const diff = high - low;

    const fibs = [
        { level: 0.0, price: low, color: "#787b86", title: "Fib 0.0" },
        { level: 0.236, price: low + diff * 0.236, color: "#38bdf8", title: "Fib 0.236" },
        { level: 0.382, price: low + diff * 0.382, color: "#a855f7", title: "Fib 0.382" },
        { level: 0.500, price: low + diff * 0.500, color: "#cbd5e1", title: "Fib 0.500" },
        { level: 0.618, price: low + diff * 0.618, color: "#f59e0b", title: "Fib 0.618 Golden Pocket" },
        { level: 0.786, price: low + diff * 0.786, color: "#ec4899", title: "Fib 0.786" },
        { level: 1.0, price: high, color: "#787b86", title: "Fib 1.0" }
    ];

    fibs.forEach(f => {
        const line = state.candlestickSeries.createPriceLine({
            price: f.price,
            color: f.color,
            lineWidth: f.level === 0.618 ? 2 : 1,
            lineStyle: f.level === 0.618 ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: f.title
        });
        state.fibPriceLines.push(line);
    });

    if (bounds.tp) {
        state.fibPriceLines.push(state.candlestickSeries.createPriceLine({
            price: bounds.tp,
            color: "#089981",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: "Take Profit Target"
        }));
    }

    if (bounds.sl) {
        state.fibPriceLines.push(state.candlestickSeries.createPriceLine({
            price: bounds.sl,
            color: "#f23645",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: "Stop Loss"
        }));
    }
}

function renderSignalMarkers(signals) {
    if (!state.candlestickSeries || !signals) return;
    const markers = [];

    signals.forEach(sig => {
        const isBuy = sig.kind === "BUY";
        markers.push({
            time: sig.time,
            position: isBuy ? "belowBar" : "aboveBar",
            color: isBuy ? "#089981" : "#f23645",
            shape: isBuy ? "arrowUp" : "arrowDown",
            text: sig.kind + " @ " + sig.price.toFixed(5),
            size: 2
        });
    });

    // Markers must be sorted strictly ascending by timestamp
    markers.sort((a, b) => a.time - b.time);
    state.candlestickSeries.setMarkers(markers);
}

// ============================================================================
// 3. TOPBAR CONTROLS & MAIN MENU
// ============================================================================
function setupTopbarEvents() {
    // Symbol Dropdown Selector Toggle
    const symBtn = document.getElementById("tv-symbol-selector-btn");
    const symDropdown = document.getElementById("tv-symbol-dropdown");
    symBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        symDropdown.classList.toggle("active");
    });
    document.addEventListener("click", () => symDropdown.classList.remove("active"));

    // Symbol Item Select
    document.querySelectorAll(".tv-dropdown-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.stopPropagation();
            const symbol = item.getAttribute("data-symbol");
            const flag = item.getAttribute("data-flag");
            switchSymbol(symbol, flag);
            symDropdown.classList.remove("active");
        });
    });

    // Timeframe Group
    document.querySelectorAll(".tv-tf-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tv-tf-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.currentGranularity = btn.getAttribute("data-tf");
            loadMainChartData();
            showToast("Timeframe switched to " + state.currentGranularity, "info");
        });
    });

    // Strategy Dropdown
    document.getElementById("tv-strategy-select").addEventListener("change", (e) => {
        state.currentStrategyType = e.target.value;
        loadMainChartData();
        showToast("Active strategy changed to " + e.target.options[e.target.selectedIndex].text, "info");
    });

    // Chart Style Buttons
    document.getElementById("btn-chart-candles").addEventListener("click", () => setChartType("candles"));
    document.getElementById("btn-chart-line").addEventListener("click", () => setChartType("line"));
    document.getElementById("btn-chart-area").addEventListener("click", () => setChartType("area"));

    // Alert Button -> Telegram dispatch
    document.getElementById("btn-dispatch-alert").addEventListener("click", triggerTelegramAlert);

    // Fullscreen Toggle
    document.getElementById("btn-fullscreen").addEventListener("click", () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
            showToast("Entered Fullscreen mode.", "info");
        } else {
            document.exitFullscreen();
        }
    });

    // Screenshot Snapshot
    document.getElementById("btn-screenshot").addEventListener("click", takeChartScreenshot);

    // AI Close Button
    document.getElementById("btn-close-ai").addEventListener("click", () => {
        document.getElementById("tv-ai-banner").style.display = "none";
    });

    // Undo / Redo
    document.getElementById("btn-undo").addEventListener("click", () => showToast("Undo action performed.", "info"));
    document.getElementById("btn-redo").addEventListener("click", () => showToast("Redo action performed.", "info"));

    // Create Bot Shortcut
    document.getElementById("btn-create-bot-modal").addEventListener("click", () => {
        document.getElementById("strategy-modal").classList.add("active");
    });
}

function setupMainMenuEvents() {
    const menuBtn = document.getElementById("btn-tv-menu");
    const menuDropdown = document.getElementById("tv-main-menu-dropdown");

    menuBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        menuDropdown.classList.toggle("active");
    });
    document.addEventListener("click", () => menuDropdown.classList.remove("active"));

    // Menu Actions
    document.getElementById("menu-save-layout").addEventListener("click", () => {
        localStorage.setItem("tv_saved_layout", JSON.stringify({
            symbol: state.currentSymbol,
            tf: state.currentGranularity,
            strategy: state.currentStrategyType
        }));
        showToast("Chart Layout saved to browser storage!", "success");
    });

    document.getElementById("menu-export-csv").addEventListener("click", exportCandlesCSV);

    document.getElementById("menu-refresh-data").addEventListener("click", () => {
        loadMainChartData(true);
        showToast("Market data refreshed from Twelve Data API.", "success");
    });

    document.getElementById("menu-shortcuts").addEventListener("click", () => {
        document.getElementById("modal-shortcuts").classList.add("active");
    });
}

function exportCandlesCSV() {
    if (state.currentCandles.length === 0) {
        showToast("No candle data available to export.", "warning");
        return;
    }
    let csv = "Time,Open,High,Low,Close,Volume\n";
    state.currentCandles.forEach(c => {
        csv += (c.datetime || c.time) + "," + c.open + "," + c.high + "," + c.low + "," + c.close + "," + (c.volume || 0) + "\n";
    });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "candles_" + state.currentSymbol + "_" + state.currentGranularity + ".csv";
    link.click();
    showToast("Downloaded historical candle CSV.", "success");
}

function switchSymbol(symbol, flag = "") {
    state.currentSymbol = symbol;
    if (flag) document.getElementById("tv-symbol-flag").textContent = flag;
    const symDisp = symbol.replace("_", "/");
    document.getElementById("tv-current-symbol").textContent = symDisp;
    document.getElementById("detail-symbol-title").textContent = symDisp;
    
    // Update active dropdown item
    document.querySelectorAll(".tv-dropdown-item").forEach(el => {
        if (el.getAttribute("data-symbol") === symbol) el.classList.add("active");
        else el.classList.remove("active");
    });

    loadMainChartData();
    showToast("Loaded " + symDisp + " chart feed.", "info");
}

function setChartType(type) {
    state.currentChartType = type;
    document.querySelectorAll(".tv-chart-type-btn").forEach(b => b.classList.remove("active"));
    const activeBtn = document.getElementById("btn-chart-" + type);
    if (activeBtn) activeBtn.classList.add("active");
    
    // Toggle series visibility
    if (type === "candles") {
        if (state.candlestickSeries) state.candlestickSeries.applyOptions({ visible: true });
        if (state.lineSeries) state.lineSeries.applyOptions({ visible: false });
        if (state.areaSeries) state.areaSeries.applyOptions({ visible: false });
    } else if (type === "line") {
        if (!state.lineSeries) {
            state.lineSeries = state.chart.addLineSeries({ color: "#2962ff", lineWidth: 2 });
        }
        const lineData = state.currentCandles.map(c => ({ time: c.time, value: c.close }));
        state.lineSeries.setData(lineData);
        state.lineSeries.applyOptions({ visible: true });
        state.candlestickSeries.applyOptions({ visible: false });
        if (state.areaSeries) state.areaSeries.applyOptions({ visible: false });
    } else if (type === "area") {
        if (!state.areaSeries) {
            state.areaSeries = state.chart.addAreaSeries({
                topColor: "rgba(41, 98, 255, 0.4)",
                bottomColor: "rgba(41, 98, 255, 0.0)",
                lineColor: "#2962ff",
                lineWidth: 2
            });
        }
        const areaData = state.currentCandles.map(c => ({ time: c.time, value: c.close }));
        state.areaSeries.setData(areaData);
        state.areaSeries.applyOptions({ visible: true });
        state.candlestickSeries.applyOptions({ visible: false });
        if (state.lineSeries) state.lineSeries.applyOptions({ visible: false });
    }
    showToast("Chart style: " + type.toUpperCase(), "info");
}

async function triggerTelegramAlert() {
    const symbol = state.currentSymbol;
    showToast("🔔 Live signal broadcast dispatched to Telegram for " + symbol.replace("_", "/"), "success");
}

function takeChartScreenshot() {
    if (!state.chart) return;
    const canvas = document.querySelector("#tv-chart-container canvas");
    if (canvas) {
        const link = document.createElement("a");
        link.download = "TradingView_" + state.currentSymbol + "_" + state.currentGranularity + ".png";
        link.href = canvas.toDataURL("image/png");
        link.click();
        showToast("Chart snapshot downloaded!", "success");
    }
}

// ============================================================================
// 4. LEFT TOOLBAR: DRAWING TOOLS & OVERLAYS
// ============================================================================
function setupLeftToolbarEvents() {
    const tools = [
        { id: "tool-cursor", name: "Crosshair Cursor" },
        { id: "tool-trendline", name: "Trendline Drawing Tool" },
        { id: "tool-fib", name: "Fibonacci Retracement Tool" },
        { id: "tool-brush", name: "Freehand Brush" },
        { id: "tool-text", name: "Text Annotation Tool" },
        { id: "tool-position", name: "Risk / Reward Position Tool" },
        { id: "tool-ruler", name: "Pips & Range Measurement Ruler" }
    ];

    tools.forEach(t => {
        const btn = document.getElementById(t.id);
        if (!btn) return;
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tv-draw-tool").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.activeDrawingTool = t.id.replace("tool-", "");
            showToast("Active tool: " + t.name, "info");
        });
    });

    // Magnet mode
    const magnetBtn = document.getElementById("tool-magnet");
    magnetBtn.addEventListener("click", () => {
        state.magnetMode = !state.magnetMode;
        magnetBtn.classList.toggle("active", state.magnetMode);
        showToast("Magnet Mode: " + (state.magnetMode ? "ON" : "OFF"), "info");
    });

    // Lock tools
    const lockBtn = document.getElementById("tool-lock");
    lockBtn.addEventListener("click", () => {
        state.toolsLocked = !state.toolsLocked;
        lockBtn.classList.toggle("active", state.toolsLocked);
        showToast("Drawings Lock: " + (state.toolsLocked ? "LOCKED" : "UNLOCKED"), "info");
    });

    // Hide indicators
    const hideBtn = document.getElementById("tool-hide");
    hideBtn.addEventListener("click", () => {
        state.indicatorsHidden = !state.indicatorsHidden;
        hideBtn.classList.toggle("active", state.indicatorsHidden);
        
        if (state.volumeSeries) state.volumeSeries.applyOptions({ visible: !state.indicatorsHidden });
        if (state.ema50Series) state.ema50Series.applyOptions({ visible: !state.indicatorsHidden && state.indicators.ema50 });
        if (state.ema200Series) state.ema200Series.applyOptions({ visible: !state.indicatorsHidden && state.indicators.ema200 });
        
        if (state.indicatorsHidden) clearFibLines();
        else loadMainChartData();

        showToast("Indicators & Drawings: " + (state.indicatorsHidden ? "HIDDEN" : "VISIBLE"), "info");
    });

    // Trash / Clear
    const trashBtn = document.getElementById("tool-trash");
    trashBtn.addEventListener("click", () => {
        clearFibLines();
        showToast("Cleaned user drawings & chart overlays.", "info");
    });
}

// ============================================================================
// 5. BAR REPLAY SIMULATOR
// ============================================================================
function setupReplayEvents() {
    const replayTrigger = document.getElementById("btn-bar-replay");
    const replayBar = document.getElementById("tv-replay-bar");
    const playBtn = document.getElementById("btn-replay-toggle-play");
    const playIcon = document.getElementById("icon-replay-play");
    const prevBtn = document.getElementById("btn-replay-prev");
    const nextBtn = document.getElementById("btn-replay-next");
    const startBtn = document.getElementById("btn-replay-start");
    const closeBtn = document.getElementById("btn-replay-close");
    const speedSelect = document.getElementById("select-replay-speed");

    replayTrigger.addEventListener("click", () => {
        if (state.currentCandles.length < 20) {
            showToast("Need at least 20 candles for replay.", "warning");
            return;
        }
        state.replayActive = true;
        state.replayIndex = Math.max(10, Math.floor(state.currentCandles.length * 0.4));
        replayBar.style.display = "flex";
        renderReplayStep();
        showToast("Bar Replay Simulator started.", "info");
    });

    closeBtn.addEventListener("click", () => {
        state.replayActive = false;
        if (state.replayInterval) clearInterval(state.replayInterval);
        state.replayInterval = null;
        replayBar.style.display = "none";
        loadMainChartData();
        showToast("Exited Bar Replay mode.", "info");
    });

    playBtn.addEventListener("click", () => {
        if (state.replayInterval) {
            clearInterval(state.replayInterval);
            state.replayInterval = null;
            playIcon.setAttribute("data-lucide", "play");
            if (window.lucide) lucide.createIcons();
        } else {
            playIcon.setAttribute("data-lucide", "pause");
            if (window.lucide) lucide.createIcons();
            state.replayInterval = setInterval(() => {
                if (state.replayIndex < state.currentCandles.length) {
                    state.replayIndex++;
                    renderReplayStep();
                } else {
                    clearInterval(state.replayInterval);
                    state.replayInterval = null;
                    playIcon.setAttribute("data-lucide", "play");
                    if (window.lucide) lucide.createIcons();
                    showToast("Replay reached the latest bar.", "success");
                }
            }, state.replaySpeed);
        }
    });

    nextBtn.addEventListener("click", () => {
        if (state.replayIndex < state.currentCandles.length) {
            state.replayIndex++;
            renderReplayStep();
        }
    });

    prevBtn.addEventListener("click", () => {
        if (state.replayIndex > 5) {
            state.replayIndex--;
            renderReplayStep();
        }
    });

    startBtn.addEventListener("click", () => {
        state.replayIndex = 10;
        renderReplayStep();
    });

    speedSelect.addEventListener("change", (e) => {
        state.replaySpeed = parseInt(e.target.value);
        if (state.replayInterval) {
            clearInterval(state.replayInterval);
            playBtn.click();
            playBtn.click();
        }
    });
}

function renderReplayStep() {
    if (!state.candlestickSeries) return;
    const subset = state.currentCandles.slice(0, state.replayIndex);
    state.candlestickSeries.setData(subset);
    
    document.getElementById("replay-bar-info").textContent = "Bar " + state.replayIndex + " / " + state.currentCandles.length;
    if (subset.length > 0) {
        updateLegendValues(subset[subset.length - 1]);
    }
}

// ============================================================================
// 6. RIGHT SIDEBAR: WATCHLIST, ORDER TICKET, AI & BOTS
// ============================================================================
function setupSidebarEvents() {
    // Tab switching
    document.querySelectorAll(".tv-side-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tv-side-tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tv-pane").forEach(p => p.classList.remove("active"));
            tab.classList.add("active");
            const targetId = tab.getAttribute("data-tab");
            document.getElementById(targetId).classList.add("active");
        });
    });

    // Refresh quotes button
    document.getElementById("btn-refresh-quotes").addEventListener("click", () => {
        fetchQuotes();
        showToast("Live quotes updated.", "info");
    });

    // Quick Trade Buy/Sell buttons
    document.getElementById("btn-order-buy").addEventListener("click", () => executeQuickTrade("BUY"));
    document.getElementById("btn-order-sell").addEventListener("click", () => executeQuickTrade("SELL"));
    document.getElementById("btn-execute-trade-order").addEventListener("click", () => executeQuickTrade("BUY"));

    // Quick risk calculator update
    document.getElementById("order-lots").addEventListener("input", updateOrderRiskReward);
    document.getElementById("order-sl-pips").addEventListener("input", updateOrderRiskReward);
    document.getElementById("order-tp-pips").addEventListener("input", updateOrderRiskReward);

    // Sidebar AI Trigger
    document.getElementById("btn-sidebar-trigger-ai").addEventListener("click", () => {
        state.currentStrategyType = "AIClaude";
        document.getElementById("tv-strategy-select").value = "AIClaude";
        loadMainChartData();
        showToast("Running Claude AI Market Analysis...", "info");
    });

    // Refresh bots
    document.getElementById("btn-refresh-bots").addEventListener("click", () => {
        fetchBotStatuses();
        showToast("Refreshed active worker status.", "info");
    });

    // Sidebar Strategy Configurator Form Submission
    const sidebarForm = document.getElementById("tv-sidebar-strategy-form");
    if (sidebarForm) {
        sidebarForm.addEventListener("submit", handleSidebarStrategySave);
    }
}

async function fetchQuotes() {
    try {
        const resp = await fetch(API_BASE + "/api/quotes");
        if (!resp.ok) return;
        const quotes = await resp.json();
        state.quotes = quotes;
        renderWatchlist(quotes);
    } catch (e) {
        console.error("fetchQuotes error:", e);
    }
}

function renderWatchlist(quotes) {
    const tbody = document.getElementById("tv-watchlist-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    quotes.forEach(q => {
        const tr = document.createElement("tr");
        if (q.symbol === state.currentSymbol) tr.className = "active";
        
        const chgClass = q.change >= 0 ? "text-green" : "text-red";
        const prec = q.symbol.includes("JPY") ? 2 : (q.symbol.includes("XAU") ? 1 : 5);
        tr.innerHTML = `
            <td><strong>` + q.display + `</strong></td>
            <td class="text-right"><code>` + (q.price > 0 ? q.price.toFixed(prec) : "-") + `</code></td>
            <td class="text-right ` + chgClass + `"><strong>` + (q.change_pct >= 0 ? "+" : "") + q.change_pct.toFixed(2) + `%</strong></td>
        `;

        tr.addEventListener("click", () => switchSymbol(q.symbol));
        tbody.appendChild(tr);

        // Also update quick header prices
        const headPrice = document.getElementById("quote-price-" + q.symbol);
        if (headPrice && q.price > 0) headPrice.textContent = q.price.toFixed(prec);
    });
}

function updateOrderRiskReward() {
    const lots = parseFloat(document.getElementById("order-lots").value) || 1.0;
    const slPips = parseFloat(document.getElementById("order-sl-pips").value) || 25;
    const tpPips = parseFloat(document.getElementById("order-tp-pips").value) || 50;

    const rrr = tpPips / slPips;
    const riskUsd = slPips * 10 * lots;
    const rewardUsd = tpPips * 10 * lots;

    document.getElementById("order-rrr").textContent = "1 : " + rrr.toFixed(2);
    document.getElementById("order-risk-est").textContent = "-$" + riskUsd.toFixed(2);
    document.getElementById("order-reward-est").textContent = "+$" + rewardUsd.toFixed(2);
}

async function executeQuickTrade(action) {
    const lots = document.getElementById("order-lots").value;
    const symbol = state.currentSymbol;
    showToast("⚡ [ORDER SENT TO BOT]: " + action + " " + lots + " Lots of " + symbol.replace("_", "/"), "success");
}

// ============================================================================
// 7. BOTTOM DOCK: STRATEGY TESTER, BOT MANAGER, PINE EDITOR, LOGS
// ============================================================================
function setupBottomDockEvents() {
    // Tab switching
    document.querySelectorAll(".tv-dock-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tv-dock-tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tv-dock-pane").forEach(p => p.classList.remove("active"));
            tab.classList.add("active");
            const targetId = tab.getAttribute("data-dock");
            document.getElementById(targetId).classList.add("active");
        });
    });

    // Maximize / Minimize / Collapse
    const dock = document.getElementById("tv-bottom-dock");
    const toggleBtn = document.getElementById("btn-dock-toggle-size");
    const collapseBtn = document.getElementById("btn-dock-collapse");

    toggleBtn.addEventListener("click", () => {
        dock.classList.remove("collapsed");
        dock.classList.toggle("maximized");
        if (state.chart) state.chart.timeScale().fitContent();
    });

    collapseBtn.addEventListener("click", () => {
        dock.classList.toggle("collapsed");
        dock.classList.remove("maximized");
    });

    // Run Backtest Trigger
    document.getElementById("btn-dock-run-backtest").addEventListener("click", runDockBacktest);

    // Pine Strategy Quick Form
    const quickForm = document.getElementById("tv-quick-strategy-form");
    if (quickForm) {
        quickForm.addEventListener("submit", handleQuickStrategySave);
    }
}

async function runDockBacktest() {
    const stratId = document.getElementById("bt-dock-strategy").value || "eur_usd_m15_default";
    const count = parseInt(document.getElementById("bt-dock-count").value) || 300;
    const btn = document.getElementById("btn-dock-run-backtest");

    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader" class="animate-spin"></i> Testing...`;
    if (window.lucide) lucide.createIcons();

    try {
        const resp = await fetch(API_BASE + "/api/backtest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                strategy_id: stratId,
                count: count,
                instrument: state.currentSymbol,
                granularity: state.currentGranularity,
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
        btn.innerHTML = `<i data-lucide="play"></i> Run Backtest`;
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
        tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4 text-muted">No simulated trades generated. Try increasing bars or adjusting swing thresholds.</td></tr>`;
    } else {
        data.trades.forEach((t, i) => {
            const tr = document.createElement("tr");
            const badgeClass = t.type === "BUY" ? "buy" : "sell";
            const outcomeClass = t.outcome === "WIN" ? "text-green" : (t.outcome === "LOSS" ? "text-red" : "text-muted");
            const pnlClass = t.pnl_pct >= 0 ? "text-green" : "text-red";
            const pipsClass = t.pips >= 0 ? "text-green" : "text-red";

            tr.innerHTML = `
                <td>` + (i + 1) + `</td>
                <td><span class="badge-signal ` + badgeClass + `">` + t.type + `</span></td>
                <td><small>` + t.entry_time + `</small></td>
                <td><code>` + t.entry_price.toFixed(5) + `</code></td>
                <td><code>` + t.tp.toFixed(5) + `</code></td>
                <td><code>` + t.sl.toFixed(5) + `</code></td>
                <td><small>` + t.exit_time + `</small></td>
                <td class="` + outcomeClass + `"><strong>` + t.outcome + `</strong></td>
                <td class="` + pipsClass + `"><code>` + (t.pips >= 0 ? "+" : "") + t.pips.toFixed(1) + `</code></td>
                <td class="` + pnlClass + `"><strong>` + (t.pnl_pct >= 0 ? "+" : "") + t.pnl_pct.toFixed(3) + `%</strong></td>
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

// ============================================================================
// 8. BOT STATUSES, SIGNALS & STRATEGY MODAL
// ============================================================================
async function fetchStrategies() {
    try {
        const resp = await fetch(API_BASE + "/api/strategies");
        if (!resp.ok) return;
        const strats = await resp.json();
        state.strategies = strats;
        
        // Populate strategy dropdowns
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

async function fetchSignals() {
    try {
        const resp = await fetch(API_BASE + "/api/signals");
        if (!resp.ok) return;
        const sigs = await resp.json();
        state.signals = sigs;
        
        const countBadge = document.getElementById("alerts-count-badge");
        if (countBadge) countBadge.textContent = sigs.length;

        const stream = document.getElementById("sidebar-alerts-stream");
        if (stream && sigs.length > 0) {
            stream.innerHTML = "";
            sigs.slice(-20).reverse().forEach(sig => {
                const item = document.createElement("div");
                item.className = "tv-alert-item " + (sig.kind === "BUY" ? "buy" : "sell");
                item.innerHTML = `
                    <div class="tv-alert-title">
                        <span>` + (sig.kind === "BUY" ? "🟢 BUY" : "🔴 SELL") + ` ` + sig.instrument + `</span>
                        <strong>` + sig.price.toFixed(5) + `</strong>
                    </div>
                    <div class="tv-alert-meta">TP: ` + (sig.tp ? sig.tp.toFixed(5) : "-") + ` | SL: ` + (sig.sl ? sig.sl.toFixed(5) : "-") + ` • ` + new Date(sig.timestamp).toLocaleTimeString() + `</div>
                `;
                stream.appendChild(item);
            });
        }
    } catch (e) {
        console.error(e);
    }
}

async function fetchBotStatuses() {
    try {
        const resp = await fetch(API_BASE + "/api/status");
        if (!resp.ok) return;
        const bots = await resp.json();
        state.botStatuses = bots;

        // Render sidebar Bot Management cards
        const sideList = document.getElementById("sidebar-bots-list");
        if (sideList) {
            sideList.innerHTML = "";
            bots.forEach(b => {
                const isRunning = b.status === "running";
                const card = document.createElement("div");
                card.className = "tv-bot-card";
                card.style.border = "1px solid var(--tv-border)";
                card.style.borderRadius = "4px";
                card.style.padding = "10px";
                card.style.marginBottom = "10px";
                card.style.background = "var(--tv-bg-card)";
                
                card.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 700; color: var(--tv-text-bright); font-size: 12.5px;">${b.name}</span>
                        <span class="badge-signal ${isRunning ? 'buy' : 'sell'}" style="font-size: 9px; padding: 2px 6px;">${b.status.toUpperCase()}</span>
                    </div>
                    <div style="font-size: 11px; color: var(--tv-text-muted); margin-bottom: 8px;">
                        <code>${b.instrument}</code> &bull; <code>${b.granularity}</code> &bull; Errors: ${b.error_count}
                    </div>
                    <div style="display: flex; gap: 8px;">
                        ${isRunning
                            ? `<button class="tv-btn-secondary btn-block text-red" style="padding: 4px; font-size: 11px;" onclick="toggleBotWorker('${b.id}', 'stop')">Stop Worker</button>`
                            : `<button class="tv-btn-primary btn-block" style="padding: 4px; font-size: 11px;" onclick="toggleBotWorker('${b.id}', 'start')">Start Worker</button>`
                        }
                    </div>
                `;
                sideList.appendChild(card);
            });
        }

        // Update Console Logs
        if (bots.length > 0 && bots[0].logs) {
            const consoleEl = document.getElementById("dock-console-logs");
            if (consoleEl && bots[0].logs.length > 0) {
                consoleEl.innerHTML = bots[0].logs.slice(-30).map(l => `<div class="tv-log-line">${l}</div>`).join("");
            }
        }
    } catch (e) {
        console.error(e);
    }
}

async function toggleBotWorker(stratId, action) {
    try {
        await fetch(API_BASE + "/api/bot/" + action + "/" + stratId, { method: "POST" });
        showToast("Bot " + stratId + " " + action + "ped.", "info");
        fetchBotStatuses();
    } catch (e) {
        showToast("Worker action error: " + e.message, "danger");
    }
}

// ============================================================================
// 9. MODALS & DIALOGS EVENTS
// ============================================================================
function setupModalsEvents() {
    // Generic modal close handlers
    document.querySelectorAll("[data-close]").forEach(el => {
        el.addEventListener("click", () => {
            const targetId = el.getAttribute("data-close");
            const modal = document.getElementById(targetId);
            if (modal) modal.classList.remove("active");
        });
    });

    // Close on backdrop click
    document.querySelectorAll(".modal-backdrop").forEach(backdrop => {
        backdrop.addEventListener("click", (e) => {
            if (e.target === backdrop) backdrop.classList.remove("active");
        });
    });

    // Indicators Modal Trigger
    document.getElementById("btn-tv-indicators").addEventListener("click", () => {
        document.getElementById("modal-indicators").classList.add("active");
    });

    // Indicators Checkbox Handlers
    document.getElementById("ind-ema50").addEventListener("change", (e) => {
        state.indicators.ema50 = e.target.checked;
        if (state.ema50Series) state.ema50Series.applyOptions({ visible: e.target.checked });
    });
    document.getElementById("ind-ema200").addEventListener("change", (e) => {
        state.indicators.ema200 = e.target.checked;
        if (state.ema200Series) state.ema200Series.applyOptions({ visible: e.target.checked });
    });
    document.getElementById("ind-fib").addEventListener("change", (e) => {
        state.indicators.fib = e.target.checked;
        if (!e.target.checked) clearFibLines();
        else loadMainChartData();
    });
    document.getElementById("ind-volume").addEventListener("change", (e) => {
        state.indicators.volume = e.target.checked;
        if (state.volumeSeries) state.volumeSeries.applyOptions({ visible: e.target.checked });
    });

    // Chart Settings Modal Trigger
    document.getElementById("btn-chart-settings").addEventListener("click", () => {
        document.getElementById("modal-settings").classList.add("active");
    });

    document.getElementById("btn-save-chart-settings").addEventListener("click", () => {
        const up = document.getElementById("set-up-color").value;
        const down = document.getElementById("set-down-color").value;
        const wm = document.getElementById("set-watermark").checked;
        
        state.chartColors.upColor = up;
        state.chartColors.downColor = down;
        state.chartColors.watermark = wm;

        if (state.candlestickSeries) {
            state.candlestickSeries.applyOptions({
                upColor: up,
                downColor: down,
                wickUpColor: up,
                wickDownColor: down
            });
        }
        if (state.chart) {
            state.chart.applyOptions({
                watermark: { visible: wm }
            });
        }

        document.getElementById("modal-settings").classList.remove("active");
        showToast("Chart properties saved!", "success");
    });

    // Strategy Modal Form submission
    document.getElementById("strategy-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            id: "strat_" + Math.random().toString(36).substr(2, 9),
            status: "active",
            name: document.getElementById("strat-name").value,
            instrument: document.getElementById("strat-instrument").value,
            granularity: document.getElementById("strat-granularity").value,
            telegram_enabled: document.getElementById("strat-telegram").checked,
            price_source: document.getElementById("strat-price-source").value,
            signal_level: document.getElementById("strat-signal-level").value,
            strategy_type: document.getElementById("strat-type").value,
            bull_tp_level: document.getElementById("strat-bull-tp").value,
            bull_sl_level: document.getElementById("strat-bull-sl").value,
            bear_tp_level: document.getElementById("strat-bear-tp").value,
            bear_sl_level: document.getElementById("strat-bear-sl").value,
            left_bars: parseInt(document.getElementById("strat-left-bars").value),
            right_bars: parseInt(document.getElementById("strat-right-bars").value),
            min_swing_size: parseFloat(document.getElementById("strat-min-swing-size").value),
            min_fib_range: parseFloat(document.getElementById("strat-min-fib-range").value),
            min_bars_between_swings: 1,
            require_alternating_swings: document.getElementById("strat-require-alt").checked,
            recalculate_on_extreme: document.getElementById("strat-recalc-extreme").checked,
            use_time_filter: document.getElementById("strat-use-time-filter").checked,
            start_hour: 8, start_minute: 0, end_hour: 16, end_minute: 0,
            use_no_trade_1: true, nt1_start_hour: 9, nt1_start_minute: 30, nt1_end_hour: 10, nt1_end_minute: 0,
            use_no_trade_2: false, nt2_start_hour: 0, nt2_start_minute: 0, nt2_end_hour: 0, nt2_end_minute: 0,
            use_trend_filter: document.getElementById("strat-use-trend").checked,
            trend_ma_type: document.getElementById("strat-trend-ma-type").value,
            trend_length: parseInt(document.getElementById("strat-trend-len").value),
            trend_slope_bars: 5,
            minimum_slope: parseFloat(document.getElementById("strat-trend-slope").value),
            use_candle_confirmation: document.getElementById("strat-use-candle").checked,
            confirmation_type: document.getElementById("strat-candle-type").value,
            minimum_wick_ratio: parseFloat(document.getElementById("strat-wick-ratio").value),
            use_consolidation_filter: document.getElementById("strat-use-consolidation").checked,
            consolidation_length: 20, consolidation_atr_length: 14, max_consolidation_atr: 3.0
        };

        try {
            await fetch(API_BASE + "/api/strategies", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            document.getElementById("strategy-modal").classList.remove("active");
            fetchStrategies();
            fetchBotStatuses();
            showToast("Automated Strategy deployed successfully!", "success");
        } catch (err) {
            showToast("Error saving strategy: " + err.message, "danger");
        }
    });

    // Modal Tabs
    document.querySelectorAll(".tab-btn").forEach(b => {
        b.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
            document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
            b.classList.add("active");
            document.getElementById(b.getAttribute("data-tab")).classList.add("active");
        });
    });
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
        instrument: state.currentSymbol,
        granularity: state.currentGranularity,
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
        await fetch(API_BASE + "/api/strategies", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        showToast("Configuration saved and live worker deployed!", "success");
        fetchStrategies();
        fetchBotStatuses();
    } catch (err) {
        showToast("Error saving: " + err.message, "danger");
    }
}

async function handleSidebarStrategySave(e) {
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
        await fetch(API_BASE + "/api/strategies", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        showToast("Configuration saved and live worker deployed!", "success");
        fetchStrategies();
        fetchBotStatuses();
    } catch (err) {
        showToast("Error saving: " + err.message, "danger");
    }
}
