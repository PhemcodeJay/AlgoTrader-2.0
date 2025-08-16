import streamlit as st
from datetime import datetime, timezone
from db import Signal  # ✅ Signal model
from utils import format_currency


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
    # Ensure all trades are dicts and have a 'virtual' field
    all_trades = [t if isinstance(t, dict) else t.to_dict() for t in all_trades]
    for t in all_trades:
        t["virtual"] = t.get("virtual") or False

    real_trades = [t for t in all_trades if not t["virtual"]]
    virtual_trades = [t for t in all_trades if t["virtual"]]

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # === Load recent signals safely ===
    recent_signals = []
    try:
        with db_manager.get_session() as session:
            signal_objs = (
                session.query(Signal)
                .order_by(Signal.created_at.desc())
                .limit(5)
                .all()
            )
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
                score = signal.get("score")
                score = round(float(score) if score is not None else 0.0, 1)
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
        trades_for_chart = real_trades + virtual_trades  # combine both
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

    # === Trade Summary Tabs ===
    st.subheader("🔍 Trade Summary")
    tab1, tab2 = st.tabs(["📈 Real Trades", "🧪 Virtual Trades"])

    # --- Real Trades Table ---
    with tab1:
        if real_trades:
            try:
                dashboard.display_trades_table(real_trades)
            except Exception:
                st.info("⚠️ Unable to display real trades table")
        else:
            st.info("No real trades available.")

    # --- Virtual Trades Table ---
    with tab2:
        if virtual_trades:
            try:
                dashboard.display_trades_table(virtual_trades)
            except Exception:
                st.info("⚠️ Unable to display virtual trades table")
        else:
            st.info("No virtual trades available.")
