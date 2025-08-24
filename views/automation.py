# automation.py (fixed version)
# Already fixed in previous, but to confirm: added get_available_capital to automated_trader if missing.
# Assume automated_trader has get_available_capital: return engine.load_capital('real' if not virtual else 'virtual')['available']
# Fixed get_today_trades to use db_manager.
# Added from datetime import datetime for timing.

import os
import sys
import streamlit as st
import time
import pandas as pd
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils import format_currency
except ImportError:
    def format_currency(value):
        return f"${value:.2f}"

def format_float(val):
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return val  # keep non-numeric as-is

def render(trading_engine, dashboard, automated_trader):
    st.set_page_config(page_title="AlgoTrader Automation", layout="wide")
    st.image("logo.png", width=80)
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

    tab_dashboard, tab_settings, tab_logs = st.tabs(["📊 Dashboard", "⚙️ Settings", "🖥 Logs & Terminal"])

    # ---------------- TAB 1: DASHBOARD ----------------
    with tab_dashboard:
        status = automated_trader.get_status() or {}
        stats = status.get("stats", {})
        signals_generated = stats.get("signals_generated", 0)
        trades_executed = stats.get("trades_executed", 0)
        successful_trades = stats.get("successful_trades", 0)
        total_pnl = stats.get("total_pnl", 0.0)

        # Automation Status
        st.subheader("⚡ Automation Status")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Status", "🟢 Active" if status.get("running") else "🔴 Off")
        col2.metric("Signals Generated", signals_generated)
        col3.metric("Trades Executed", trades_executed)
        col4.metric("Available Capital", format_currency(automated_trader.get_available_capital()))

        # Control Buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if not status.get("running") and st.button("▶️ Start Auto Mode", key="start_auto"):
                if automated_trader.start():
                    st.success("Automation started")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to start")
            elif status.get("running") and st.button("⏹️ Stop Automation", key="stop_auto"):
                if automated_trader.stop():
                    st.success("Automation stopped")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Stop failed")

        with col2:
            if st.button("🔄 Generate Signals", key="gen_signals"):
                with st.spinner("Generating signals…"):
                    signals = trading_engine.run_once()
                    st.success(f"Generated {len(signals)} signals")

        # Performance Metrics
        st.subheader("📈 Automation Performance")
        col1, col2, col3, col4 = st.columns(4)
        success_rate = (successful_trades / trades_executed * 100) if trades_executed else 0.0
        col1.metric("Total Signals", signals_generated)
        col2.metric("Total Trades", trades_executed)
        col3.metric("Success Rate", f"{success_rate:.1f}%")
        col4.metric("Total P&L", format_currency(total_pnl))

        # Timing Information
        if status.get("running"):
            st.subheader("⏰ Timing Info")
            try:
                last_str = status.get("last_run")
                next_str = status.get("next_run")
                if last_str:
                    last = datetime.fromisoformat(last_str)
                    st.info(f"Last Signal Generation: {last:%Y-%m-%d %H:%M:%S}")
                if next_str:
                    nxt = datetime.fromisoformat(next_str)
                    st.info(f"Next Signal Generation: {nxt:%Y-%m-%d %H:%M:%S}")
            except Exception as e:
                st.warning(f"Timing display error: {e}")

        # Open Trades Table
        st.subheader("📋 Open Trades (Today)")
        today_trades = automated_trader.get_today_trades()
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

            # Format numeric values safely
            for col in ['Entry', 'Exit', 'SL', 'TP']:
                df[col] = pd.to_numeric(df[col], errors='coerce').map(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")

            # Format PnL with color HTML
            def format_pnl(val):
                try:
                    val = float(val)
                    color = "green" if val > 0 else "red" if val < 0 else "black"
                    return f'<span style="color:{color}">${val:,.2f}</span>'
                except:
                    return '$0.00'
            df['PnL'] = df['PnL'].apply(format_pnl)

            st.write(df.to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.info("No trades for today.")

    # ---------------- TAB 2: SETTINGS ----------------
    with tab_settings:
        settings = status.get("settings", {})
        st.subheader("⚙️ Automation Settings")
        col1, col2 = st.columns(2)
        with col1:
            signal_interval = st.slider("Signal Interval (min)", 15, 90, int(settings.get("interval", 900)) // 60)
            max_signals = st.slider("Max Signals/cycle", 1, 10, int(settings.get("max_signals", 5)))
        with col2:
            max_daily = st.slider("Max Daily Trades", 1, 150, int(settings.get("max_daily_trades", 30)))
            max_pos = st.slider("Max Position Size %", 0.5, 20.0, float(settings.get("max_position_pct", 5.0)), step=0.5)
            max_dd = st.slider("Max Drawdown %", 0.0, 100.0, float(settings.get("max_drawdown", 10.0)), step=0.1)

        if st.button("💾 Save Settings"):
            new_settings = {
                "SCAN_INTERVAL": signal_interval * 60,
                "TOP_N_SIGNALS": max_signals,
                "MAX_DAILY_TRADES": max_daily,
                "MAX_POSITION_PCT": max_pos,
                "MAX_DRAWDOWN": max_dd
            }
            automated_trader.update_settings(new_settings)
            st.success("Settings saved")
            time.sleep(1)
            st.rerun()

    # ---------------- TAB 3: LOGS & TERMINAL ----------------
    with tab_logs:
        st.subheader("📜 Recent Logs")
        log_file = "automated_trader.log"
        if os.path.exists(log_file):
            logs = open(log_file, encoding="utf-8").read().splitlines()[-50:]
            st.text_area("Log Output", "\n".join(logs), height=300)
        else:
            st.info("No log file found")