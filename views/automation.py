import os
import streamlit as st
import time
from datetime import datetime
from utils import format_currency


def render(trading_engine, dashboard, automated_trader):
    st.title("🤖 AlgoTrader Automation")

    # Theme toggle
    st.sidebar.markdown("## ⚙️ Display Options")
    theme = st.sidebar.radio("Select Theme", ["Light", "Dark"], index=0)
    if theme == "Dark":
        st.markdown("""
            <style>
                html, body, [class*="css"] {
                    background-color: #0e1117 !important;
                    color: white !important;
                }
                .stButton>button {
                    background-color: #262730;
                    color: white;
                }
            </style>
        """, unsafe_allow_html=True)

    # Get automation status and stats
    status = automated_trader.get_status() or {}
    stats = status.get("stats", {})
    settings = status.get("settings", {})

    # Extract stats safely
    signals_generated = stats.get("signals_generated", 0)
    trades_executed = stats.get("trades_executed", 0)
    successful_trades = stats.get("successful_trades", 0)
    total_pnl = stats.get("total_pnl", 0.0)

    # Metrics overview
    col1, col2, col3 = st.columns(3)
    col1.metric("Automation Status", "🟢 Active" if status.get("running") else "🔴 Off")
    col2.metric("Signals Generated", signals_generated)
    col3.metric("Trades Executed", trades_executed)

    # Control buttons
    col1, col2, col3 = st.columns(3)
    with col1:
        if not status.get("running"):
            if st.button("▶️ Start Auto Mode"):
                if automated_trader.start():
                    st.success("Automation started")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to start")
        else:
            if st.button("⏹️ Stop Automation"):
                if automated_trader.stop():
                    st.success("Automation stopped")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Stop failed")

    with col2:
        if st.button("🔄 Generate Signals"):
            with st.spinner("Generating…"):
                signals = trading_engine.run_once()
                st.success(f"Generated {len(signals)} signals")

    with col3:
        if st.button("📊 View Logs"):
            log_file = "automated_trader.log"
            if os.path.exists(log_file):
                logs = open(log_file, encoding="utf-8").read().splitlines()[-20:]
                st.text_area("Recent Logs", "\n".join(logs), height=200)
            else:
                st.info("No log file found")

    # --- Settings Section ---
    st.markdown("---")
    st.subheader("⚙️ Automation Settings")
    col1, col2 = st.columns(2)
    with col1:
        signal_interval = st.slider(
            "Signal Interval (min)", 5, 60,
            int(settings.get("interval", 900)) // 60
        )
        max_signals = st.slider(
            "Max Signals/cycle", 1, 10,
            int(settings.get("max_signals", 5))
        )
    with col2:
        max_daily = st.slider(
            "Max Daily Trades", 1, 150,
            int(settings.get("max_daily_trades", 30))
        )
        max_pos = st.slider(
            "Max Position Size %", 0.5, 20.0,
            float(settings.get("max_position_pct", 5.0)),
            step=0.5
        )
        max_dd = st.slider(
            "Max Drawdown %", 0.0, 100.0,
            float(settings.get("max_drawdown", 10.0)),
            step=0.1
        )

    if st.button("💾 Save Automation Settings"):
        new = {
            "SCAN_INTERVAL": signal_interval * 60,
            "TOP_N_SIGNALS": max_signals,
            "MAX_DAILY_TRADES": max_daily,
            "MAX_POSITION_PCT": max_pos,
            "MAX_DRAWDOWN": max_dd
        }
        automated_trader.update_settings(new)
        st.success("Settings saved")
        time.sleep(1)
        st.rerun()

    # --- Performance Section ---
    st.subheader("📈 Automation Performance")
    col1, col2, col3, col4 = st.columns(4)
    success_rate = (successful_trades / trades_executed * 100) if trades_executed > 0 else 0.0
    col1.metric("Total Signals", signals_generated)
    col2.metric("Total Trades", trades_executed)
    col3.metric("Success Rate", f"{success_rate:.1f}%")
    col4.metric("Total P&L", format_currency(total_pnl))

    # --- Timing Info ---
    if status.get("running"):
        st.subheader("⏰ Timing Information")
        last_str = status.get("last_run")
        next_str = status.get("next_run")

        try:
            if last_str:
                last = datetime.fromisoformat(last_str)
                st.info(f"Last Signal Generation: {last:%Y-%m-%d %H:%M:%S}")
            if next_str:
                nxt = datetime.fromisoformat(next_str)
                st.info(f"Next Signal Generation: {nxt:%Y-%m-%d %H:%M:%S}")
        except Exception as e:
            st.warning(f"Could not parse timing info: {e}")
