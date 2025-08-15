import streamlit as st
from datetime import datetime, timezone
from db import Signal
from utils import format_currency

def render(trading_engine, dashboard, db_manager=None):
    st.image("logo.png", width=80)
    st.title("🚀 AlgoTrader Dashboard")

    # --- Wallet Data ---
    capital_data = trading_engine.load_capital("all") or {}
    real = capital_data.get("real", {})
    virtual = capital_data.get("virtual", {})

    real_total = float(real.get("capital", 0.0))
    real_available = float(real.get("available", 0.0))
    virtual_total = float(virtual.get("capital", 0.0))
    virtual_available = float(virtual.get("available", 0.0))

    # --- Recent Trades ---
    all_trades = trading_engine.get_recent_trades(limit=100) or []
    real_trades = [t for t in all_trades if not t.get("virtual")]
    virtual_trades = [t for t in all_trades if t.get("virtual")]

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # --- Recent Signals ---
    if db_manager:
        with db_manager.get_session() as session:
            signal_objs = session.query(Signal).order_by(Signal.created_at.desc()).limit(10).all()
            recent_signals = [s.to_dict() for s in signal_objs]
    else:
        recent_signals = []

    # --- KPI Metrics ---
    st.markdown("### 📈 Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Real Wallet", format_currency(real_available), f"Total: {format_currency(real_total)}")
    col2.metric("🧪 Virtual Wallet", format_currency(virtual_available), f"Total: {format_currency(virtual_total)}")
    col3.metric("📡 Active Signals", len(recent_signals), "Recent")
    col4.metric(
        "📅 Real Trades Today",
        len([t for t in real_trades if str(t.get("timestamp", "")).startswith(today_str)])
    )

    st.markdown("---")

    # --- Latest Signals ---
    st.subheader("📡 Latest Signals")
    if recent_signals:
        cols = st.columns(3)
        for i, signal in enumerate(recent_signals):
            col = cols[i % 3]
            col.markdown(
                f"""
                <div style='border-radius:12px;padding:15px;background-color:#f0f2f6;margin-bottom:10px;box-shadow:0 2px 8px rgba(0,0,0,0.1);'>
                    <h4 style='margin:0'>{signal.get("symbol","N/A")}</h4>
                    <p style='margin:5px 0'>{signal.get("signal_type","N/A")} | Score: {round(float(signal.get("score") or 0),1)}%</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            if hasattr(dashboard, "display_signal_card"):
                dashboard.display_signal_card(signal)
    else:
        st.info("No recent signals available.")

    st.markdown("---")

    # --- Real Wallet Performance ---
    st.subheader("📊 Real Wallet Overview")
    if real_trades and hasattr(dashboard, "create_portfolio_performance_chart"):
        fig = dashboard.create_portfolio_performance_chart(real_trades, real_total)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No real trade history available.")

    st.markdown("---")

    # --- Trades Grid Tabs ---
    st.subheader("🔍 Trade Summary")
    tab_real, tab_virtual = st.tabs(["📈 Real Trades", "🧪 Virtual Trades"])

    def display_trades_grid(trades):
        if trades:
            cols = st.columns(3)
            for i, trade in enumerate(trades):
                col = cols[i % 3]
                col.markdown(
                    f"""
                    <div style='border-radius:12px;padding:15px;background-color:#e8f4f8;margin-bottom:10px;box-shadow:0 2px 8px rgba(0,0,0,0.1);'>
                        <h4 style='margin:0'>{trade.get("symbol","N/A")}</h4>
                        <p style='margin:5px 0'>Type: {trade.get("side","N/A")}</p>
                        <p style='margin:5px 0'>ROI: {trade.get("roi",0):.2f}%</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if hasattr(dashboard, "display_trade_card"):
                    dashboard.display_trade_card(trade)
        else:
            st.info("No trades available.")

    with tab_real:
        display_trades_grid(real_trades)

    with tab_virtual:
        display_trades_grid(virtual_trades)
