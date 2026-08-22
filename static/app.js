// ============================================================================
// STATE & CONFIG
// ============================================================================
const API_BASE = window.location.origin;

let state = {
    strategies: [],
    signals: [],
    botStatuses: [],
    activeView: 'dashboard',
    selectedLogStrategyId: '',
    logInterval: null,
    statusInterval: null,
    equityChartInstance: null
};

// ============================================================================
// DOM INITS & INITIAL LISTENERS
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    // Lucide Icons Initialization
    lucide.createIcons();

    // Sidebar navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.getAttribute('data-view');
            switchView(view);
        });
    });

    // Strategy Modal Close button
    document.getElementById('modal-close-btn').addEventListener('click', closeModal);
    document.getElementById('btn-modal-cancel').addEventListener('click', closeModal);

    // Strategy Modal Tabs switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Strategy Modal Filter checkbox disclosures
    setupDisclosure('strat-use-time-filter', 'time-filter-inputs');
    setupDisclosure('strat-use-trend', 'trend-inputs');
    setupDisclosure('strat-use-candle', 'candle-inputs');
    setupDisclosure('strat-use-consolidation', 'consolidation-inputs');

    // Strategy creation & save
    document.getElementById('btn-add-strategy').addEventListener('click', () => openStrategyModal());
    document.getElementById('btn-create-strategy-shortcut').addEventListener('click', () => openStrategyModal());
    document.getElementById('strategy-form').addEventListener('submit', handleSaveStrategy);

    // Refresh bot statuses
    document.getElementById('refresh-status').addEventListener('click', fetchBotStatuses);

    // Log console select dropdown
    document.getElementById('log-strategy-select').addEventListener('change', (e) => {
        state.selectedLogStrategyId = e.target.value;
        renderLogs();
    });

    // Backtest Form Submission
    document.getElementById('backtest-form').addEventListener('submit', handleRunBacktest);
    
    // Backtest candle history slider
    const slider = document.getElementById('backtest-count');
    const sliderVal = document.getElementById('backtest-count-val');
    slider.addEventListener('input', (e) => {
        sliderVal.textContent = e.target.value;
    });

    // Initial data fetch
    fetchStrategies();
    fetchSignals();
    fetchBotStatuses();

    // Setup periodic polling loops (every 3 seconds)
    state.statusInterval = setInterval(() => {
        fetchBotStatuses();
        fetchSignals();
    }, 4000);
});

// ============================================================================
// GENERAL VIEW ROUTING
// ============================================================================
function switchView(viewName) {
    state.activeView = viewName;

    // Toggle nav classes
    document.querySelectorAll('.nav-item').forEach(item => {
        if (item.getAttribute('data-view') === viewName) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Toggle view elements
    document.querySelectorAll('.content-view').forEach(view => {
        if (view.id === `view-${viewName}`) {
            view.classList.add('active');
        } else {
            view.classList.remove('active');
        }
    });

    // Update Header title
    const titles = {
        dashboard: { main: 'Dashboard Overview', sub: 'Real-time status and alerts summary' },
        strategies: { main: 'Strategy Configurations', sub: 'Manage, customize, and deploy strategy presets' },
        backtesting: { main: 'Historical Backtester', sub: 'Test strategy presets against historical candles' }
    };
    document.getElementById('page-title').textContent = titles[viewName].main;
    document.getElementById('page-subtitle').textContent = titles[viewName].sub;

    // Perform fresh fetch on switch
    if (viewName === 'dashboard') {
        fetchBotStatuses();
        fetchSignals();
    } else if (viewName === 'strategies') {
        fetchStrategies();
    } else if (viewName === 'backtesting') {
        populateBacktestSelector();
    }
}

// Helper for conditional checkbox inputs
function setupDisclosure(checkboxId, targetId) {
    const box = document.getElementById(checkboxId);
    const target = document.getElementById(targetId);

    box.addEventListener('change', () => {
        if (box.type === 'checkbox') {
            if (box.checked) {
                target.style.opacity = '1';
                target.style.pointerEvents = 'auto';
                target.style.display = 'block';
                if (target.classList.contains('form-row')) {
                    target.style.display = 'flex';
                }
            } else {
                target.style.opacity = '0.5';
                target.style.pointerEvents = 'none';
                target.style.display = 'none';
                if (checkboxId === 'strat-use-time-filter') {
                    // Start/End time is nested inside opacity wrapper, preserve display layout
                    target.style.display = 'flex';
                }
            }
        }
    });
}

// ============================================================================
// DATA FETCHING & API INTERFACES
// ============================================================================
async function fetchStrategies() {
    try {
        const resp = await fetch(`${API_BASE}/api/strategies`);
        if (!resp.ok) throw new Error("Failed to load strategies.");
        state.strategies = await resp.json();
        renderStrategies();
        populateLogSelector();
    } catch (err) {
        console.error(err);
    }
}

async function fetchSignals() {
    try {
        const resp = await fetch(`${API_BASE}/api/signals`);
        if (!resp.ok) throw new Error("Failed to load signals.");
        state.signals = await resp.json();
        renderSignals();
    } catch (err) {
        console.error(err);
    }
}

async function fetchBotStatuses() {
    try {
        const resp = await fetch(`${API_BASE}/api/status`);
        if (!resp.ok) throw new Error("Failed to load status.");
        state.botStatuses = await resp.json();
        renderBotStatuses();
        renderLogs();
        updateOverviewCards();
    } catch (err) {
        console.error(err);
    }
}

// ============================================================================
// DOM RENDERING & TEMPLATES
// ============================================================================

// Overview count cards
function updateOverviewCards() {
    const runningCount = state.botStatuses.filter(b => b.status === 'running').length;
    document.getElementById('stat-active-bots').textContent = runningCount;
    document.getElementById('stat-total-signals').textContent = state.signals.length;
    
    if (state.botStatuses.length > 0) {
        const times = state.botStatuses.map(b => b.last_run).filter(Boolean);
        if (times.length > 0) {
            const latest = new Date(Math.max(...times.map(t => new Date(t))));
            document.getElementById('stat-last-check').textContent = latest.toLocaleTimeString();
            return;
        }
    }
    document.getElementById('stat-last-check').textContent = 'Never';
}

// Render active bot cards on dashboard
function renderBotStatuses() {
    const container = document.getElementById('active-bots-list');
    container.innerHTML = '';

    if (state.botStatuses.length === 0) {
        container.innerHTML = '<p class="empty-message">No strategies configured yet.</p>';
        return;
    }

    state.botStatuses.forEach(bot => {
        const isRunning = bot.status === 'running';
        const card = document.createElement('div');
        card.className = 'bot-status-item';

        card.innerHTML = `
            <div class="bot-info">
                <span class="bot-title">${bot.name}</span>
                <span class="bot-subtitle">${bot.instrument} (${bot.granularity})</span>
            </div>
            <div class="bot-state">
                <span class="bot-badge ${bot.status}">${bot.status}</span>
                <div class="bot-controls">
                    ${isRunning 
                        ? `<button class="btn-icon stop-btn" onclick="toggleBot('${bot.id}', 'stop')" title="Stop Bot"><i data-lucide="square"></i></button>`
                        : `<button class="btn-icon play-btn" onclick="toggleBot('${bot.id}', 'start')" title="Start Bot"><i data-lucide="play"></i></button>`
                    }
                </div>
            </div>
        `;
        container.appendChild(card);
    });

    lucide.createIcons();
}

// Dropdown mapping
function populateLogSelector() {
    const select = document.getElementById('log-strategy-select');
    const val = select.value;
    select.innerHTML = '<option value="">Select Strategy</option>';
    state.strategies.forEach(s => {
        select.innerHTML += `<option value="${s.id}">${s.name}</option>`;
    });
    select.value = val;
}

// Log Terminal content
function renderLogs() {
    const terminal = document.getElementById('terminal-logs');
    if (!state.selectedLogStrategyId) {
        terminal.innerHTML = '<p class="text-muted">// Select a strategy above to view live logs...</p>';
        return;
    }

    const bot = state.botStatuses.find(b => b.id === state.selectedLogStrategyId);
    if (!bot) {
        terminal.innerHTML = '<p class="text-red">// Selected strategy not found.</p>';
        return;
    }

    if (bot.status !== 'running' && bot.logs.length === 0) {
        terminal.innerHTML = `<p class="text-muted">// Strategy [${bot.name}] is offline. No logs to show.</p>`;
        return;
    }

    terminal.innerHTML = '';
    bot.logs.forEach(line => {
        const lineEl = document.createElement('p');
        if (line.includes('ERROR') || line.includes('Failed')) {
            lineEl.className = 'text-red';
        } else if (line.includes('ALERT') || line.includes('NEW SIGNAL')) {
            lineEl.className = 'text-green';
        } else if (line.includes('Rate limit hit')) {
            lineEl.className = 'text-muted';
            lineEl.style.color = '#fbbf24'; // warning orange
        }
        lineEl.textContent = line;
        terminal.appendChild(lineEl);
    });

    // Auto-scroll to bottom
    terminal.scrollTop = terminal.scrollHeight;
}

// Render dynamic signals log table
function renderSignals() {
    const tbody = document.getElementById('signals-log-tbody');
    tbody.innerHTML = '';

    if (state.signals.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-4 text-muted">No signals captured yet.</td>
            </tr>
        `;
        return;
    }

    // Sort descending
    const sorted = [...state.signals].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    sorted.forEach(sig => {
        const tr = document.createElement('tr');
        const badgeClass = sig.kind === 'BUY' ? 'buy' : 'sell';
        const formattedTime = new Date(sig.time).toLocaleString();

        tr.innerHTML = `
            <td><span class="badge-signal ${badgeClass}">${sig.kind}</span></td>
            <td><strong>${sig.strategy_name}</strong></td>
            <td><code>${sig.instrument} (${sig.granularity})</code></td>
            <td><code>${sig.price.toFixed(5)}</code></td>
            <td class="text-muted">${formattedTime}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Render strategy manager cards
function renderStrategies() {
    const grid = document.getElementById('strategies-card-grid');
    grid.innerHTML = '';

    if (state.strategies.length === 0) {
        grid.innerHTML = '<p class="empty-message">No strategies configured. Click Add Strategy to create one.</p>';
        return;
    }

    state.strategies.forEach(strat => {
        const isActive = strat.status === 'active';
        const card = document.createElement('div');
        card.className = 'strategy-card';

        card.innerHTML = `
            <div class="strat-card-header">
                <div>
                    <h3>${strat.name}</h3>
                    <p>${strat.instrument} &bull; ${strat.granularity}</p>
                </div>
                <span class="bot-badge ${strat.status}">${strat.status}</span>
            </div>
            
            <div class="strat-grid-info">
                <div class="strat-info-item">
                    <span>Pivot Left/Right</span>
                    <span>${strat.left_bars} / ${strat.right_bars}</span>
                </div>
                <div class="strat-info-item">
                    <span>Fib Level</span>
                    <span>${strat.signal_level}</span>
                </div>
                <div class="strat-info-item">
                    <span>Price Source</span>
                    <span>${strat.price_source}</span>
                </div>
                <div class="strat-info-item">
                    <span>Trend Filter</span>
                    <span>${strat.use_trend_filter ? 'On' : 'Off'}</span>
                </div>
                <div class="strat-info-item">
                    <span>Confirm Type</span>
                    <span>${strat.use_candle_confirmation ? 'On' : 'Off'}</span>
                </div>
                <div class="strat-info-item">
                    <span>Telegram</span>
                    <span>${strat.telegram_enabled ? 'On' : 'Off'}</span>
                </div>
            </div>

            <div class="strat-card-footer">
                <div class="bot-controls">
                    ${isActive 
                        ? `<button class="btn btn-secondary btn-icon stop-btn" onclick="toggleBot('${strat.id}', 'stop')" title="Stop Live Alerts"><i data-lucide="square"></i></button>`
                        : `<button class="btn btn-primary btn-icon play-btn" onclick="toggleBot('${strat.id}', 'start')" title="Start Live Alerts"><i data-lucide="play"></i></button>`
                    }
                </div>
                <div class="strat-actions-wrapper">
                    <button class="btn btn-secondary btn-icon" onclick="openStrategyModal('${strat.id}')" title="Edit Strategy Parameters"><i data-lucide="edit"></i></button>
                    <button class="btn btn-secondary btn-icon" onclick="runQuickBacktest('${strat.id}')" title="Run Backtest Preset"><i data-lucide="line-chart"></i></button>
                    <button class="btn btn-secondary btn-icon text-red" onclick="deleteStrategy('${strat.id}')" title="Delete Preset"><i data-lucide="trash-2"></i></button>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });

    lucide.createIcons();
}

// Backtest selectors populate
function populateBacktestSelector() {
    const select = document.getElementById('backtest-strat-select');
    const curVal = select.value;
    select.innerHTML = '<option value="">Choose Strategy Preset</option>';
    state.strategies.forEach(s => {
        select.innerHTML += `<option value="${s.id}">${s.name} (${s.instrument} @ ${s.granularity})</option>`;
    });
    select.value = curVal;
}

// ============================================================================
// STRATEGY ACTIONS (CRUD)
// ============================================================================
function openStrategyModal(stratId = '') {
    const modal = document.getElementById('strategy-modal');
    const form = document.getElementById('strategy-form');
    const title = document.getElementById('modal-title');
    
    // Clear tabs
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelector('.tab-btn[data-tab="tab-general"]').classList.add('active');
    document.getElementById('tab-general').classList.add('active');

    form.reset();

    if (stratId) {
        // Edit Mode
        title.textContent = "Edit Strategy Configuration";
        const strat = state.strategies.find(s => s.id === stratId);
        
        document.getElementById('strat-id').value = strat.id;
        document.getElementById('strat-status').value = strat.status;
        document.getElementById('strat-name').value = strat.name;
        document.getElementById('strat-instrument').value = strat.instrument;
        document.getElementById('strat-granularity').value = strat.granularity;
        document.getElementById('strat-telegram').checked = strat.telegram_enabled;
        document.getElementById('strat-price-source').value = strat.price_source;
        document.getElementById('strat-signal-level').value = strat.signal_level;
        
        document.getElementById('strat-bull-tp').value = strat.bull_tp_level;
        document.getElementById('strat-bull-sl').value = strat.bull_sl_level;
        document.getElementById('strat-bear-tp').value = strat.bear_tp_level;
        document.getElementById('strat-bear-sl').value = strat.bear_sl_level;

        document.getElementById('strat-left-bars').value = strat.left_bars;
        document.getElementById('strat-right-bars').value = strat.right_bars;
        document.getElementById('strat-min-swing-size').value = strat.min_swing_size;
        document.getElementById('strat-min-fib-range').value = strat.min_fib_range;
        document.getElementById('strat-min-bars-between').value = strat.min_bars_between_swings;
        document.getElementById('strat-require-alt').checked = strat.require_alternating_swings;
        document.getElementById('strat-recalc-extreme').checked = strat.recalculate_on_extreme;

        document.getElementById('strat-use-time-filter').checked = strat.use_time_filter;
        document.getElementById('strat-start-hour').value = strat.start_hour;
        document.getElementById('strat-start-minute').value = strat.start_minute;
        document.getElementById('strat-end-hour').value = strat.end_hour;
        document.getElementById('strat-end-minute').value = strat.end_minute;

        document.getElementById('strat-use-nt1').checked = strat.use_no_trade_1;
        document.getElementById('strat-nt1-start-h').value = strat.nt1_start_hour;
        document.getElementById('strat-nt1-start-m').value = strat.nt1_start_minute;
        document.getElementById('strat-nt1-end-h').value = strat.nt1_end_hour;
        document.getElementById('strat-nt1-end-m').value = strat.nt1_end_minute;

        document.getElementById('strat-use-trend').checked = strat.use_trend_filter;
        document.getElementById('strat-trend-ma-type').value = strat.trend_ma_type;
        document.getElementById('strat-trend-len').value = strat.trend_length;
        document.getElementById('strat-trend-slope').value = strat.minimum_slope;

        document.getElementById('strat-use-candle').checked = strat.use_candle_confirmation;
        document.getElementById('strat-candle-type').value = strat.confirmation_type;
        document.getElementById('strat-wick-ratio').value = strat.minimum_wick_ratio;

        document.getElementById('strat-use-consolidation').checked = strat.use_consolidation_filter;
        document.getElementById('strat-consolidation-len').value = strat.consolidation_length;
        document.getElementById('strat-consolidation-atr').value = strat.max_consolidation_atr;
    } else {
        // Create Mode
        title.textContent = "Create New Strategy";
        document.getElementById('strat-id').value = '';
        document.getElementById('strat-status').value = 'inactive';
        
        // Populate standard default parameters
        document.getElementById('strat-left-bars').value = 5;
        document.getElementById('strat-right-bars').value = 5;
        document.getElementById('strat-min-swing-size').value = 0.0;
        document.getElementById('strat-min-fib-range').value = 0.0030; // standard EUR/USD
        document.getElementById('strat-min-bars-between').value = 1;
        document.getElementById('strat-require-alt').checked = true;
        document.getElementById('strat-recalc-extreme').checked = false;
        
        document.getElementById('strat-use-time-filter').checked = false;
        document.getElementById('strat-use-nt1').checked = true;
        document.getElementById('strat-use-trend').checked = false;
        document.getElementById('strat-use-candle').checked = false;
        document.getElementById('strat-use-consolidation').checked = false;
    }

    // Trigger manual checkmark updates on setup disclosures
    const events = ['strat-use-time-filter', 'strat-use-trend', 'strat-use-candle', 'strat-use-consolidation'];
    events.forEach(evId => {
        const box = document.getElementById(evId);
        box.dispatchEvent(new Event('change'));
    });

    modal.classList.add('active');
}

function closeModal() {
    document.getElementById('strategy-modal').classList.remove('active');
}

async function handleSaveStrategy(e) {
    e.preventDefault();

    let stratId = document.getElementById('strat-id').value;
    if (!stratId) {
        // Generate random strategy ID
        stratId = 'strat_' + Math.random().toString(36).substr(2, 9);
    }

    const payload = {
        id: stratId,
        status: document.getElementById('strat-status').value || 'inactive',
        name: document.getElementById('strat-name').value,
        instrument: document.getElementById('strat-instrument').value,
        granularity: document.getElementById('strat-granularity').value,
        telegram_enabled: document.getElementById('strat-telegram').checked,
        price_source: document.getElementById('strat-price-source').value,
        signal_level: document.getElementById('strat-signal-level').value,
        bull_tp_level: document.getElementById('strat-bull-tp').value,
        bull_sl_level: document.getElementById('strat-bull-sl').value,
        bear_tp_level: document.getElementById('strat-bear-tp').value,
        bear_sl_level: document.getElementById('strat-bear-sl').value,
        
        left_bars: parseInt(document.getElementById('strat-left-bars').value),
        right_bars: parseInt(document.getElementById('strat-right-bars').value),
        min_swing_size: parseFloat(document.getElementById('strat-min-swing-size').value),
        min_fib_range: parseFloat(document.getElementById('strat-min-fib-range').value),
        min_bars_between_swings: parseInt(document.getElementById('strat-min-bars-between').value),
        require_alternating_swings: document.getElementById('strat-require-alt').checked,
        recalculate_on_extreme: document.getElementById('strat-recalc-extreme').checked,

        use_time_filter: document.getElementById('strat-use-time-filter').checked,
        start_hour: parseInt(document.getElementById('strat-start-hour').value) || 0,
        start_minute: parseInt(document.getElementById('strat-start-minute').value) || 0,
        end_hour: parseInt(document.getElementById('strat-end-hour').value) || 0,
        end_minute: parseInt(document.getElementById('strat-end-minute').value) || 0,

        use_no_trade_1: document.getElementById('strat-use-nt1').checked,
        nt1_start_hour: parseInt(document.getElementById('strat-nt1-start-h').value) || 0,
        nt1_start_minute: parseInt(document.getElementById('strat-nt1-start-m').value) || 0,
        nt1_end_hour: parseInt(document.getElementById('strat-nt1-end-h').value) || 0,
        nt1_end_minute: parseInt(document.getElementById('strat-nt1-end-m').value) || 0,

        use_no_trade_2: false, // fallback preset defaults
        nt2_start_hour: 0,
        nt2_start_minute: 0,
        nt2_end_hour: 0,
        nt2_end_minute: 0,

        use_trend_filter: document.getElementById('strat-use-trend').checked,
        trend_ma_type: document.getElementById('strat-trend-ma-type').value || 'SMA',
        trend_length: parseInt(document.getElementById('strat-trend-len').value) || 50,
        trend_slope_bars: 5,
        minimum_slope: parseFloat(document.getElementById('strat-trend-slope').value) || 0.0,

        use_candle_confirmation: document.getElementById('strat-use-candle').checked,
        confirmation_type: document.getElementById('strat-candle-type').value || 'Rejection Candle',
        minimum_wick_ratio: parseFloat(document.getElementById('strat-wick-ratio').value) || 0.5,

        use_consolidation_filter: document.getElementById('strat-use-consolidation').checked,
        consolidation_length: parseInt(document.getElementById('strat-consolidation-len').value) || 20,
        consolidation_atr_length: 14,
        max_consolidation_atr: parseFloat(document.getElementById('strat-consolidation-atr').value) || 3.0
    };

    try {
        const resp = await fetch(`${API_BASE}/api/strategies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) throw new Error("Failed to save strategy config.");
        
        closeModal();
        fetchStrategies();
        fetchBotStatuses();
    } catch (err) {
        alert(err.message);
    }
}

async function deleteStrategy(stratId) {
    if (!confirm("Are you sure you want to delete this strategy?")) return;

    try {
        const resp = await fetch(`${API_BASE}/api/strategies/${stratId}`, {
            method: 'DELETE'
        });
        if (!resp.ok) throw new Error("Failed to delete strategy.");
        fetchStrategies();
        fetchBotStatuses();
    } catch (err) {
        alert(err.message);
    }
}

// ============================================================================
// BOT RUN/STOP CONTROLS
// ============================================================================
async function toggleBot(stratId, action) {
    try {
        const endpoint = `${API_BASE}/api/bot/${action}/${stratId}`;
        const resp = await fetch(endpoint, { method: 'POST' });
        if (!resp.ok) throw new Error(`Failed to ${action} bot.`);
        
        fetchBotStatuses();
        fetchStrategies();
    } catch (err) {
        alert(err.message);
    }
}

// ============================================================================
// BACKTEST EXECUTION
// ============================================================================
async function handleRunBacktest(e) {
    e.preventDefault();

    const stratId = document.getElementById('backtest-strat-select').value;
    const count = parseInt(document.getElementById('backtest-count').value);
    const forceRefresh = document.getElementById('backtest-refresh').checked;

    if (!stratId) return;

    const btn = document.getElementById('btn-run-backtest');
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader" class="animate-spin"></i> Running simulation...`;
    lucide.createIcons();

    try {
        const resp = await fetch(`${API_BASE}/api/backtest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                strategy_id: stratId,
                count: count,
                force_refresh: forceRefresh
            })
        });

        if (!resp.ok) {
            const errBody = await resp.json();
            throw new Error(errBody.detail || "Backtest failed.");
        }

        const data = await resp.json();
        displayBacktestResults(data);
    } catch (err) {
        alert("Backtest Error: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="play"></i> Run Backtest`;
        lucide.createIcons();
    }
}

function runQuickBacktest(stratId) {
    switchView('backtesting');
    document.getElementById('backtest-strat-select').value = stratId;
    const form = document.getElementById('backtest-form');
    // programmatically trigger submit
    form.dispatchEvent(new Event('submit'));
}

function displayBacktestResults(data) {
    document.getElementById('backtest-results').style.display = 'block';

    const m = data.metrics;
    document.getElementById('bt-win-rate').textContent = `${m.win_rate}%`;
    document.getElementById('bt-wins-losses').textContent = `${m.wins} Wins / ${m.losses} Losses`;
    
    const profitEl = document.getElementById('bt-net-profit');
    profitEl.textContent = `${m.net_profit_pct > 0 ? '+' : ''}${m.net_profit_pct.toFixed(2)}%`;
    profitEl.className = `metric-val ${m.net_profit_pct >= 0 ? 'text-green' : 'text-red'}`;

    document.getElementById('bt-drawdown').textContent = `${m.max_drawdown_pct.toFixed(2)}%`;
    document.getElementById('bt-total-trades').textContent = m.total_trades;
    document.getElementById('bt-open-trades').textContent = `${m.open_trades} Open Trades`;

    // Render Trade table
    const tbody = document.getElementById('backtest-trades-tbody');
    tbody.innerHTML = '';

    if (data.trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-muted">No simulated trades executed. Try increasing candle count or adjusting swing bounds.</td></tr>`;
    } else {
        data.trades.forEach(t => {
            const tr = document.createElement('tr');
            const badgeClass = t.type === 'BUY' ? 'buy' : 'sell';
            const outcomeClass = t.outcome === 'WIN' ? 'text-green' : (t.outcome === 'LOSS' ? 'text-red' : 'text-muted');
            const pnlClass = t.pnl_pct >= 0 ? 'text-green' : 'text-red';
            
            tr.innerHTML = `
                <td><span class="badge-signal ${badgeClass}">${t.type}</span></td>
                <td><small>${t.entry_time}</small></td>
                <td><code>${t.entry_price.toFixed(5)}</code></td>
                <td><code>${t.tp.toFixed(5)}</code></td>
                <td><code>${t.sl.toFixed(5)}</code></td>
                <td><small>${t.exit_time}</small></td>
                <td><code>${t.exit_price.toFixed(5)}</code></td>
                <td class="${outcomeClass}"><strong>${t.outcome}</strong></td>
                <td class="${pnlClass}"><strong>${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct.toFixed(3)}%</strong></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Render Growth Line Chart
    renderEquityChart(data.trades);
}

// Chart.js helper
function renderEquityChart(trades) {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    
    // Destroy previous Chart instance
    if (state.equityChartInstance) {
        state.equityChartInstance.destroy();
    }

    const labels = ['Start'];
    const values = [0.0];

    trades.forEach((t, i) => {
        labels.push(`Trade ${i + 1}`);
        values.push(t.cumulative_pnl_pct);
    });

    state.equityChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Cumulative Performance (%)',
                data: values,
                borderColor: '#3b82f6',
                borderWidth: 3,
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.25,
                pointRadius: values.length < 50 ? 4 : 1,
                pointBackgroundColor: '#2563eb',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1f2937',
                    titleColor: '#f3f4f6',
                    bodyColor: '#9ca3af',
                    borderColor: '#374151',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            return `Growth: ${context.parsed.y.toFixed(2)}%`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#9ca3af', font: { size: 11 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#9ca3af',
                        font: { size: 11 },
                        callback: function(value) { return value.toFixed(1) + '%'; }
                    }
                }
            }
        }
    });
}
