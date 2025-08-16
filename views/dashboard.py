import streamlit as st
from datetime import datetime, timezone
from db import Signal
from utils import format_currency

# =========================
# Main Render Function
# =========================
def render(trading_engine, dashboard, db_manager):
    st.image("logo.png", width=80)
    st.title("🚀 AlgoTrader Dashboard")

    # === Load wallet data safely ===
    capital_data = trading_engine.load_capital("all") or {}
    real = capital_data.get("real") or {}
    virtual = capital_data.get("virtual") or {}

    real_total = float(real.get("capital") or 0.0)
    real_available = float(real.get("available") or real_total)

    virtual_total = float(virtual.get("capital") or 0.0)
    virtual_available = float(virtual.get("available") or virtual_total)

    # === Load recent trades safely ===
    all_trades = trading_engine.get_recent_trades(limit=100) or []
    all_trades = [t if isinstance(t, dict) else t.to_dict() for t in all_trades]

    # Add default fields and compute PnL safely
    for t in all_trades:
        t["virtual"] = t.get("virtual") or False
        t["entry_price"] = float(t.get("entry_price") or 0.0)
        t["qty"] = float(t.get("qty") or 0.0)
        t["side"] = (t.get("side") or "buy").lower()
        t["status"] = (t.get("status") or "open").lower()
        # Calculate unrealized PnL for open trades
        try:
            if t["status"] == "open":
                if t["virtual"]:
                    t["pnl"] = trading_engine.calculate_virtual_pnl(t)
                else:
                    ticker = trading_engine.get_ticker(t.get("symbol") or "")
                    last_price = float(ticker.get("lastPrice", t["entry_price"])) if ticker else t["entry_price"]
                    t["pnl"] = (last_price - t["entry_price"]) * t["qty"] if t["side"] == "buy" else (t["entry_price"] - last_price) * t["qty"]
            else:
                t["pnl"] = float(t.get("pnl") or 0.0)
        except Exception:
            t["pnl"] = float(t.get("pnl") or 0.0)

    real_trades = [t for t in all_trades if not t["virtual"]]
    virtual_trades = [t for t in all_trades if t["virtual"]]

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # === Load recent signals safely ===
    recent_signals = []
    try:
        with db_manager.get_session() as session:
            signal_objs = session.query(Signal).order_by(Signal.created_at.desc()).limit(5).all()
            recent_signals = [s.to_dict() for s in signal_objs]
    except Exception as e:
        st.warning(f"Failed to load recent signals: {e}")

    # === KPI Metrics ===
    st.markdown("### 📈 Overview")
    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "💰 Real Wallet",
        format_currency(real_available),
        f"Total: {format_currency(real_total)}"
    )
    col2.metric(
        "🧪 Virtual Wallet",
        format_currency(virtual_available),
        f"Total: {format_currency(virtual_total)}"
    )
    col3.metric(
        "📡 Active Signals",
        len(recent_signals),
        "Recent"
    )
    col4.metric(
        "📅 Real Trades Today",
        len([t for t in real_trades if str(t.get("timestamp") or "").startswith(today_str)]),
    )

    st.markdown("---")

    # === Left: Recent Signals / Right: Wallet chart ===
    col_left, col_right = st.columns(2)

    # --- Recent Signals ---
    with col_left:
        st.subheader("📡 Latest Signals")
        if recent_signals:
            for i, signal in enumerate(recent_signals):
                symbol = signal.get("symbol") or "N/A"
                signal_type = signal.get("signal_type") or "N/A"
                score = round(float(signal.get("score") or 0.0), 1)
                with st.expander(f"{symbol} - {signal_type} ({score}%)", expanded=(i == 0)):
                    try:
                        dashboard.display_signal_card(signal)
                    except Exception:
                        st.write("⚠️ Unable to display signal")
        else:
            st.info("No recent signals available.")

    # --- Trades Overview Chart ---
    with col_right:
        st.subheader("📊 Trades Overview")
        trades_for_chart = real_trades + virtual_trades
        total_capital = real_total + virtual_total
        if trades_for_chart:
            try:
                fig = dashboard.create_portfolio_performance_chart(trades_for_chart, total_capital)
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.info("⚠️ Unable to render trades chart")
        else:
            st.info("No trade history available.")

    st.markdown("---")

    # === Trade Summary Tabs with Live PnL ===
    st.subheader("🔍 Trade Summary")
    tab1, tab2 = st.tabs(["📈 Real Trades", "🧪 Virtual Trades"])

    # --- Real Trades Table ---
    with tab1:
        if real_trades:
            manage_trades_table(real_trades, trading_engine)
        else:
            st.info("No real trades available.")

    # --- Virtual Trades Table ---
    with tab2:
        if virtual_trades:
            manage_trades_table(virtual_trades, trading_engine)
        else:
            st.info("No virtual trades available.")


# =========================
# Helper to display trades with live PnL
# =========================
def manage_trades_table(trades, trading_engine):
    for idx, trade in enumerate(trades):
        symbol = trade.get("symbol") or "N/A"
        side = trade.get("side") or "buy"
        entry = float(trade.get("entry_price") or 0.0)
        qty = float(trade.get("qty") or 0.0)
        status = trade.get("status") or "open"
        pnl = float(trade.get("pnl") or 0.0)
        virtual = trade.get("virtual") or False
        ts = trade.get("timestamp") or ""
        trade_id = trade.get("order_id") or f"{symbol}_{idx}"

        pnl_key = f"pnl_{trade_id}"
        if pnl_key not in st.session_state:
            st.session_state[pnl_key] = pnl

        # Live PnL update for open trades
        if status.lower() == "open":
            try:
                if virtual:
                    st.session_state[pnl_key] = trading_engine.calculate_virtual_pnl(trade)
                else:
                    ticker = trading_engine.get_ticker(symbol)
                    if ticker:
                        last_price = float(ticker.get("lastPrice", entry))
                        st.session_state[pnl_key] = (last_price - entry) * qty if side.lower() == "buy" else (entry - last_price) * qty
            except Exception:
                st.session_state[pnl_key] = pnl

        pnl_display = st.session_state[pnl_key]
        color = "green" if pnl_display >= 0 else "red"

        with st.expander(f"{symbol} | {side} | Entry: {entry:.2f} | PnL: {pnl_display:+.2f}", expanded=True):
            cols = st.columns(4)
            cols[0].markdown(f"**Qty:** {qty}")
            cols[1].markdown(f"**Status:** {status}")
            cols[2].markdown(f"**Mode:** {'Virtual' if virtual else 'Real'}")
            cols[3].markdown(f"**PnL:** <span style='color:{color}'>{pnl_display:+.2f}</span>", unsafe_allow_html=True)
            st.markdown(f"⏱ `{ts}`")
