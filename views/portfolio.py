import streamlit as st
from datetime import datetime, timezone
from utils import format_trades  # Make sure this exists


# =========================
# Main Render Function
# =========================
def render(trading_engine, dashboard):
    st.set_page_config(page_title="💼 Wallet Summary", layout="wide")
    st.image("logo.png", width=80)
    st.title("💼 Wallet Summary")

    # Wallet Overview
    try:
        capital_data = trading_engine.load_capital("all") or {}
        real = capital_data.get("real", {}) or {}
        virtual = capital_data.get("virtual", {}) or {}

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Real Balance", f"${float(real.get('capital') or 0.0):,.2f}")
        col2.metric("Available Real", f"${float(real.get('available') or real.get('capital') or 0.0):,.2f}")
        col3.metric("🧪 Virtual Balance", f"${float(virtual.get('capital') or 0.0):,.2f}")
        col4.metric("Available Virtual", f"${float(virtual.get('available') or virtual.get('capital') or 0.0):,.2f}")
    except Exception as e:
        st.error(f"Error loading wallet data: {e}")

    st.markdown("---")

    # Tabs
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

    # Compute trade age safely
    for t in trades:
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

    # Charts and stats
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

    # Trades table
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
        trades = (trading_engine.get_open_real_trades() or []) + (trading_engine.get_open_virtual_trades() or [])
        if mode == "real":
            trades = trading_engine.get_open_real_trades() or []
        elif mode == "virtual":
            trades = trading_engine.get_open_virtual_trades() or []
    elif trade_type == "closed":
        trades = (trading_engine.get_closed_real_trades() or []) + (trading_engine.get_closed_virtual_trades() or [])
        if mode == "real":
            trades = trading_engine.get_closed_real_trades() or []
        elif mode == "virtual":
            trades = trading_engine.get_closed_virtual_trades() or []
    else:
        trades = []
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
    real = balances.get("real", {}) or {}
    virtual = balances.get("virtual", {}) or {}
    capital = float(real.get("capital") or 0.0) + float(virtual.get("capital") or 0.0)
    available = float(real.get("available") or real.get("capital") or 0.0) + float(virtual.get("available") or virtual.get("capital") or 0.0)
    start_balance = float(real.get("start_balance") or 0.0) + float(virtual.get("start_balance") or 0.0)
    currency = real.get("currency") or virtual.get("currency") or "USD"
    return capital, available, start_balance, currency


def display_metrics(trading_engine, trades, capital, available, start_balance):
    total_return_pct = ((capital - start_balance) / start_balance * 100) if start_balance else 0.0
    win_rate = float(trading_engine.calculate_win_rate(trades) or 0.0)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_pnl = sum(float(t.get("pnl") or 0.0) for t in trades if str(t.get("timestamp") or "").startswith(today_str))

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


def manage_open_trades(trades, trading_engine):
    for trade in trades:
        symbol = trade.get("symbol") or "N/A"
        side = trade.get("side") or "N/A"
        entry = float(trade.get("entry_price") or 0.0)
        qty = float(trade.get("qty") or 0.0)
        sl = float(trade.get("stop_loss") or 0.0)
        tp = float(trade.get("take_profit") or 0.0)
        pnl = float(trade.get("pnl") or 0.0)
        status = trade.get("status") or "N/A"
        virtual = trade.get("virtual") or False
        ts = trade.get("timestamp") or ""
        trade_id = trade.get("order_id")

        with st.expander(f"{symbol} | {side} | Entry: {entry}"):
            cols = st.columns(4)
            cols[0].markdown(f"**Qty:** {qty}")
            cols[1].markdown(f"**SL:** {sl}")
            cols[2].markdown(f"**TP:** {tp}")
            cols[3].markdown(f"**PnL:** {pnl}")
            st.markdown(f"**Status:** {status} | **Mode:** {'Virtual' if virtual else 'Real'} ⏱ `{ts}`")

            if status.lower() == "open" and trade_id:
                if st.button("❌ Close Trade", key=f"close_{symbol}_{trade_id}_{ts}"):
                    if trading_engine.close_trade(str(trade_id), virtual):
                        st.success(f"{'Virtual' if virtual else 'Real'} trade closed successfully.")
                        st.rerun()
                    else:
                        st.error("Failed to close trade.")
