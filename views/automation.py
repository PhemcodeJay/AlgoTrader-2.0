import os
import sys
import streamlit as st
import time
from datetime import datetime
import pandas as pd

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils import format_currency
except ImportError:
    def format_currency(value):
        try:
            return f"${float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)

def format_float(val):
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return val

def render(trading_engine, dashboard, automated_trader):
    st.set_page_config(page_title="AlgoTrader Automation", layout="wide")
    st.image("logo.png", width=80)
    st.title("🤖 AlgoTrader Automation")

    # ---------------- Theme ----------------
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

    tab_dashboard, tab_settings, tab_logs = st.tabs(["📊 Dashboard", "⚙️ Settings", "🖥 Logs & Terminal"])

    # ---------------- DASHBOARD ----------------
    with tab_dashboard:
        status = automated_trader.get_status() or {}
        stats = status.get("stats", {})

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Status", "🟢 Active" if status.get("running") else "🔴 Off")
        col2.metric("Signals Generated", stats.get("signals_generated", 0))
        col3.metric("Trades Executed", stats.get("trades_executed", 0))

        try:
            capital = automated_trader.get_available_capital()
        except Exception as e:
            st.error(f"Failed to get capital: {e}")
            capital = 0.0
        col4.metric("Available Capital", format_currency(capital))

        # Control buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if not status.get("running") and st.button("▶️ Start Auto Mode"):
                if automated_trader.start():
                    st.success("Automation started")
                    time.sleep(1)
                    st.rerun()
            elif status.get("running") and st.button("⏹️ Stop Automation"):
                if automated_trader.stop():
                    st.success("Automation stopped")
                    time.sleep(1)
                    st.rerun()

        with col2:
            if st.button("🔄 Generate Signals"):
                with st.spinner("Generating signals…"):
                    signals = trading_engine.run_once() or []
                    st.success(f"Generated {len(signals)} signals")

        # Performance metrics
        st.subheader("📈 Automation Performance")
        trades_executed = stats.get("trades_executed", 0)
        successful_trades = stats.get("successful_trades", 0)
        total_pnl = stats.get("total_pnl", 0.0)
        success_rate = (successful_trades / trades_executed * 100) if trades_executed else 0.0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Signals", stats.get("signals_generated", 0))
        col2.metric("Total Trades", trades_executed)
        col3.metric("Success Rate", f"{success_rate:.1f}%")
        col4.metric("Total P&L", format_currency(total_pnl))

        # Timing info
        if status.get("running"):
            st.subheader("⏰ Timing Info")
            last_run = status.get("last_run")
            next_run = status.get("next_run")
            if last_run:
                last = datetime.fromisoformat(last_run)
                st.info(f"Last Signal Generation: {last:%Y-%m-%d %H:%M:%S}")
            if next_run:
                nxt = datetime.fromisoformat(next_run)
                st.info(f"Next Signal Generation: {nxt:%Y-%m-%d %H:%M:%S}")

        # Open trades table
        st.subheader("📋 Open Trades (Today)")
        today_trades = automated_trader.get_today_trades() or []
        if today_trades:
            trade_data = []
            for t in today_trades:
                trade_data.append({
                    "Symbol": getattr(t, "symbol", "N/A"),
                    "Side": getattr(t, "side", "N/A"),
                    "Qty": getattr(t, "qty", 0),
                    "Entry": getattr(t, "entry_price", 0),
                    "Exit": getattr(t, "exit_price", "-"),
                    "SL": getattr(t, "stop_loss", "-"),
                    "TP": getattr(t, "take_profit", "-"),
                    "PnL": getattr(t, "pnl", 0.0),
                    "Status": getattr(t, "status", "N/A"),
                })

            df = pd.DataFrame(trade_data)
            # Numeric formatting
            for col in ["Entry", "Exit", "SL", "TP"]:
                df[col] = pd.to_numeric(df[col], errors='coerce').map(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
            # PnL coloring
            def format_pnl(val):
                if isinstance(val, (int, float)):
                    color = "green" if val > 0 else "red" if val < 0 else "black"
                    return f'<span style="color:{color}">${val:,.2f}</span>'
                return val
            df["PnL"] = df["PnL"].apply(format_pnl)
            st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.info("No trades for today.")

    # ---------------- SETTINGS ----------------
    with tab_settings:
        st.subheader("⚙️ Automation Settings")
        settings = status.get("settings", {})

        col1, col2 = st.columns(2)
        with col1:
            signal_interval = st.slider("Signal Interval (min)", 15, 90, int(settings.get("interval", 900)) // 60)
            max_signals = st.slider("Max Signals/cycle", 1, 10, int(settings.get("max_signals", 5)))
        with col2:
            max_daily = st.slider("Max Daily Trades", 1, 150, int(settings.get("max_daily_trades", 50)))
            max_pos = st.slider("Max Position Size %", 0.5, 20.0, float(settings.get("max_position_pct", 5.0)), step=0.5)
            max_dd = st.slider("Max Drawdown %", 0.0, 100.0, float(settings.get("max_drawdown", 20.0)), step=0.1)

        if st.button("💾 Save Settings"):
            new_settings = {
                "SCAN_INTERVAL": signal_interval * 60,
                "TOP_N_SIGNALS": max_signals,
                "MAX_DAILY_TRADES": max_daily,
                "MAX_POSITION_PCT": max_pos,
                "MAX_DRAWDOWN": max_dd,
            }
            automated_trader.update_settings(new_settings)
            st.success("Settings saved")
            time.sleep(1)
            st.rerun()

    # ---------------- LOGS ----------------
    with tab_logs:
        st.subheader("📜 Recent Logs")
        log_file = "automated_trader.log"
        if os.path.exists(log_file):
            with open(log_file, encoding="utf-8") as f:
                logs = f.read().splitlines()[-50:]
            st.text_area("Log Output", "\n".join(logs), height=300)
        else:
            st.info("No log file found")
