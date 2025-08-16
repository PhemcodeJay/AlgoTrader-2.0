import os
import sys
import streamlit as st
import time
from datetime import datetime
from engine import TradingEngine
from automated_trader import automated_trader  # import the singleton instance

try:
    from utils import format_currency
except ImportError:
    def format_currency(value):
        return f"${value:.2f}"


def render(trading_engine, automated_trader):
    st.image("logo.png", width=80)
    st.title("🤖 AlgoTrader Automation")

    # Theme toggle
    st.sidebar.markdown("## ⚙️ Display Options")
    theme = st.sidebar.radio("Select Theme", ["Light", "Dark"], index=0)
    if theme == "Dark":
        st.markdown(
            """
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
            """,
            unsafe_allow_html=True,
        )

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "⚙️ Settings", "🖥 Logs & Terminal"])

    # ---------------- TAB 1: DASHBOARD ----------------
    with tab1:
        status = automated_trader.get_status() or {}
        stats = status.get("stats", {})
        settings = status.get("settings", {})

        signals_generated = int(stats.get("signals_generated", 0))
        trades_executed = int(stats.get("trades_executed", 0))
        successful_trades = int(stats.get("successful_trades", 0))
        total_pnl = float(stats.get("total_pnl", 0.0))

        col1, col2, col3 = st.columns(3)
        col1.metric("Automation Status", "🟢 Active" if status.get("running") else "🔴 Off")
        col2.metric("Signals Generated", signals_generated)
        col3.metric("Trades Executed", trades_executed)

        col1, col2, col3 = st.columns(3)
        with col1:
            if not status.get("running"):
                if st.button("▶️ Start Auto Mode"):
                    if automated_trader.start():
                        st.success("Automation started")
                        st.rerun()
                    else:
                        st.error("Failed to start")
            else:
                if st.button("⏹️ Stop Automation"):
                    if automated_trader.stop():
                        st.success("Automation stopped")
                        st.rerun()
                    else:
                        st.error("Stop failed")

        with col2:
            if st.button("🔄 Generate Signals"):
                with st.spinner("Generating…"):
                    signals = trading_engine.run_once() or []
                    st.success(f"Generated {len(signals)} signals")

        # Performance
        st.subheader("📈 Automation Performance")
        col1, col2, col3, col4 = st.columns(4)
        success_rate = (successful_trades / trades_executed * 100) if trades_executed > 0 else 0.0
        col1.metric("Total Signals", signals_generated)
        col2.metric("Total Trades", trades_executed)
        col3.metric("Success Rate", f"{success_rate:.1f}%")
        col4.metric("Total P&L", format_currency(total_pnl))

        # Timing Info
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
            except Exception:
                st.warning("Could not parse timing info")

    # ---------------- TAB 2: SETTINGS ----------------
    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            signal_interval = st.slider(
                "Signal Interval (min)", 15, 90,
                int(settings.get("interval", 3600)) // 60
            )
            max_signals = st.slider(
                "Max Signals/cycle", 1, 10,
                int(settings.get("max_signals", 5))
            )
        with col2:
            max_daily = st.slider(
                "Max Daily Trades", 1, 150,
                int(settings.get("max_daily_trades", 50))
            )
            max_pos = st.slider(
                "Max Position Size %", 0.5, 20.0,
                float(settings.get("max_position_pct", 5.0)),
                step=0.5
            )
            max_dd = st.slider(
                "Max Drawdown %", 0.0, 100.0,
                float(settings.get("max_drawdown", 20.0)),
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
            st.rerun()

    # ---------------- TAB 3: LOGS & TERMINAL ----------------
    st.subheader("📜 Recent Logs / Terminal Output")
    log_file = "automated_trader.log"

    if os.path.exists(log_file):
        try:
            with open(log_file, encoding="utf-8") as f:
                logs = f.read().splitlines()[-50:]  # last 50 lines
        except Exception as e:
            logs = [f"Error reading log: {e}"]
        st.text_area("Log Output", "\n".join(logs[::-1]), height=400)  # newest first
    else:
        st.info("No log file found")


if __name__ == "__main__":
    trading_engine = TradingEngine()
    render(trading_engine, automated_trader)  # Pass the actual AutomatedTrader instance
