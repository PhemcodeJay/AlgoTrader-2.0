import streamlit as st
from datetime import datetime, timezone
from utils import format_trades  # Assumes you have a formatting helper

# =========================
# Main Render Function
# =========================
def render(trading_engine, dashboard):
    st.set_page_config(page_title="💼 Wallet Summary", layout="wide")
    st.image("logo.png", width=80)
    st.title("💼 Wallet Summary")

    # ---------------------------
    # Wallet Overview
    # ---------------------------
    try:
        capital_data = trading_engine.load_capital("all") or {}
        real = capital_data.get("real") or {}
        virtual = capital_data.get("virtual") or {}

        # Safely extract values
        real_capital = safe_float(real.get("capital"))
        real_available = safe_float(real.get("available") or real.get("capital"))
        virtual_capital = safe_float(virtual.get("capital"))
        virtual_available = safe_float(virtual.get("available") or virtual.get("capital"))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Real Balance", f"${real_capital:,.2f}")
        col2.metric("Available Real", f"${real_available:,.2f}")
        col3.metric("🧪 Virtual Balance", f"${virtual_capital:,.2f}")
        col4.metric("Available Virtual", f"${virtual_available:,.2f}")

    except Exception as e:
        st.error(f"Error loading wallet data: {e}")

    st.markdown("---")

    # ---------------------------
    # Tabs
    # ---------------------------
    tabs = st.tabs(["🔄 All Trades", "📂 Open Trades", "✅ Closed Trades"])
    tab_types = ["all", "open", "closed"]
    for idx, trade_type in enumerate(tab_types):
        with tabs[idx]:
            render_trades_tab(trading_engine, dashboard, trade_type, idx)


# =========================
# Trades Tab Renderer
# =========================
def render_trades_tab(trading_engine, dashboard, trade_type, tab_index):
    mode = st.radio("Mode", ["All", "Real", "Virtual"], key=f"mode_{trade_type}", horizontal=True)

    trades = fetch_trades(trading_engine, trade_type, mode)
    trades = [ensure_dict(t) for t in trades]

    # Compute unrealized PnL & trade age
    for t in trades:
        entry_price = safe_float(t.get("entry_price"))
        qty = safe_float(t.get("qty"))
        side_safe = (t.get("side") or "buy").lower()

        # Recalculate PnL if trade is open
        if (t.get("status") or "").lower() == "open":
            try:
                if t.get("virtual"):
                    t["pnl"] = safe_float(trading_engine.calculate_virtual_pnl(t))
                else:
                    ticker = trading_engine.get_ticker(t.get("symbol") or "")
                    if ticker:
                        last_price = safe_float(ticker.get("lastPrice"), entry_price)
                        t["pnl"] = (last_price - entry_price) * qty if side_safe == "buy" else (entry_price - last_price) * qty
            except Exception:
                t["pnl"] = safe_float(t.get("pnl"))
        else:
            t["pnl"] = safe_float(t.get("pnl"))

        # Trade age
        ts = t.get("timestamp")
        try:
            ts_dt = None
            if isinstance(ts, str):
                ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, datetime):
                ts_dt = ts
            t["trade_age"] = (datetime.now(timezone.utc) - ts_dt).total_seconds() / 3600 if ts_dt else None
        except Exception:
            t["trade_age"] = None

    capital, available, start_balance, _ = load_capital(trading_engine, mode)
    display_metrics(trading_engine, trades, capital, available, start_balance)

    # ---------------------------
    # Charts & Stats
    # ---------------------------
    left, right = st.columns([2, 1])
    with left:
        st.subheader("📈 Assets Performance")
        if trades:
            try:
                fig = dashboard.create_detailed_performance_chart(trades, capital)
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.info("⚠️ Unable to render performance chart.")
        else:
            st.info("No trade data available.")

    with right:
        st.subheader("📊 Trade Stats")
        if trades:
            try:
                stats = trading_engine.calculate_trade_statistics(trades)
                dashboard.display_trade_statistics(stats)
            except Exception:
                st.info("⚠️ Unable to display stats.")
        else:
            st.info("No stats available.")

    # ---------------------------
    # Trades Table
    # ---------------------------
    st.markdown("---")
    st.subheader("🧾 Trades Table")
    paginated_trades = paginate(trades, f"page_{tab_index}")
    if trade_type == "open":
        manage_open_trades(paginated_trades, trading_engine)
    else:
        dashboard.display_trades_table(paginated_trades)


# =========================
# Helper Functions
# =========================
def fetch_trades(trading_engine, trade_type, mode):
    mode = mode.lower()
    if trade_type == "all":
        trades = trading_engine.get_recent_trades(limit=100) or []
    elif trade_type == "open":
        trades = trading_engine.get_open_trades() or []
    elif trade_type == "closed":
        trades = trading_engine.get_closed_trades() or []
    else:
        trades = []

    if mode == "real":
        trades = [t for t in trades if not t.get("virtual")]
    elif mode == "virtual":
        trades = [t for t in trades if t.get("virtual")]

    return trades


def ensure_dict(trade):
    if isinstance(trade, dict):
        return trade
    if hasattr(trade, "to_dict"):
        return trade.to_dict()
    return {k: getattr(trade, k, None) for k in [
        "symbol", "side", "qty", "entry_price", "exit_price", "pnl",
        "status", "timestamp", "virtual", "order_id", "stop_loss", "take_profit"
    ]}


def load_capital(trading_engine, mode):
    balances = trading_engine.load_capital("all") if mode.lower() == "all" else trading_engine.load_capital(mode.lower())
    real = balances.get("real") or {}
    virtual = balances.get("virtual") or {}
    capital = safe_float(real.get("capital")) + safe_float(virtual.get("capital"))
    available = safe_float(real.get("available") or real.get("capital")) + safe_float(virtual.get("available") or virtual.get("capital"))
    start_balance = safe_float(real.get("start_balance")) + safe_float(virtual.get("start_balance"))
    currency = real.get("currency") or virtual.get("currency") or "USD"
    return capital, available, start_balance, currency


def display_metrics(trading_engine, trades, capital, available, start_balance):
    # Ensure all values are floats
    capital = safe_float(capital)
    available = safe_float(available)
    start_balance = safe_float(start_balance)
    total_return_pct = ((capital - start_balance) / start_balance * 100) if start_balance else 0.0
    win_rate = safe_float(trading_engine.calculate_win_rate(trades))
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_pnl = sum(safe_float(t.get("pnl")) for t in trades if str(t.get("timestamp") or "").startswith(today_str))

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Capital", f"${capital:,.2f}")
    col2.metric("Available", f"${available:,.2f}")
    col3.metric("Total Return", f"{total_return_pct:+.2f}%")
    col4.metric("Daily P&L", f"${daily_pnl:+.2f}")
    col5.metric("Win Rate", f"{win_rate:.2f}%")


def paginate(trades, key, page_size=10):
    total_pages = max((len(trades) - 1) // page_size + 1, 1)
    page_num = st.number_input("Page", min_value=1, max_value=total_pages, step=1, key=key)
    start, end = (page_num - 1) * page_size, page_num * page_size
    return trades[start:end]


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_timestamp(ts):
    """Convert timestamp to UTC datetime string or return 'N/A' if invalid."""
    if not ts:
        return "N/A"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, datetime):
            dt = ts
        else:
            return "N/A"
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return "N/A"


def manage_open_trades(trades, trading_engine):
    """
    Display open trades with live PnL updates, color-highlighted by profit/loss.
    """
    for idx, trade in enumerate(trades):
        symbol = trade.get("symbol") or "N/A"
        side = trade.get("side") or "buy"
        entry = safe_float(trade.get("entry_price"))
        qty = safe_float(trade.get("qty"))
        sl = safe_float(trade.get("stop_loss"))
        tp = safe_float(trade.get("take_profit"))
        pnl = safe_float(trade.get("pnl"))
        status = trade.get("status") or "N/A"
        virtual = trade.get("virtual") or False
        ts = safe_timestamp(trade.get("timestamp"))
        trade_id = trade.get("order_id") or f"{symbol}_{idx}"

        pnl_key = f"pnl_{trade_id}"
        close_key = f"close_{trade_id}"

        if pnl_key not in st.session_state:
            st.session_state[pnl_key] = pnl

        # Live PnL update
        if (status or "").lower() == "open":
            try:
                if virtual:
                    st.session_state[pnl_key] = safe_float(trading_engine.calculate_virtual_pnl(trade))
                else:
                    ticker = trading_engine.get_ticker(symbol)
                    if ticker:
                        last_price = safe_float(ticker.get("lastPrice"), entry)
                        side_safe = side.lower()
                        st.session_state[pnl_key] = (last_price - entry) * qty if side_safe == "buy" else (entry - last_price) * qty
            except Exception:
                st.session_state[pnl_key] = pnl

        pnl_display = safe_float(st.session_state.get(pnl_key, 0.0))
        color = "green" if pnl_display >= 0 else "red"

        with st.expander(f"{symbol} | {side} | Entry: {entry:.2f} | PnL: {pnl_display:+.2f}", expanded=True):
            cols = st.columns(4)
            cols[0].markdown(f"**Qty:** {safe_float(qty):.2f}")
            cols[1].markdown(f"**SL:** {safe_float(sl):.2f}")
            cols[2].markdown(f"**TP:** {safe_float(tp):.2f}")
            cols[3].markdown(f"**PnL:** <span style='color:{color}'>{pnl_display:+.2f}</span>", unsafe_allow_html=True)
            st.markdown(f"**Status:** {status} | **Mode:** {'Virtual' if virtual else 'Real'} ⏱ `{ts}`")

            # Close trade button
            if (status or "").lower() == "open":
                if st.button("❌ Close Trade", key=close_key):
                    success = trading_engine.close_trade(str(trade_id), virtual)
                    if success:
                        st.success(f"{'Virtual' if virtual else 'Real'} trade closed successfully.")
                        trade["status"] = "closed"
                        trade["pnl"] = st.session_state[pnl_key]
                    else:
                        st.error("Failed to close trade.")
