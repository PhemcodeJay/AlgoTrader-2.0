# settings.py (fixed version)
# Fixes: Completed truncated notifications section.
# For save API, update db_manager.update_setting for API keys (securely).
# Fixed folder counts: use reports/signals, reports/trades.
# Added clear functions: add to db_manager if not, but assume session.delete.
# Added real/virtual toggle.
# Ensured os.getenv for values.

import streamlit as st
import os
from db import db_manager

def render(trading_engine, dashboard):
    st.image("logo.png", width=80)
    st.title("⚙️ Trading & System Settings")

    # Theme toggle in sidebar
    st.sidebar.markdown("## 🎨 Theme")
    theme = st.sidebar.radio("Select Theme", ["Light", "Dark"], index=0)
    if theme == "Dark":
        st.markdown("""
            <style>
                html, body, [class*="css"] {
                    background-color: #0e1117 !important;
                    color: #f0f0f0 !important;
                }
                .stButton>button { background-color: #262730; color: white; }
                .stSlider>div>div>div>div { color: white !important; }
            </style>
        """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📈 Trading Settings", "🛠️ System Settings"])

    # --- TAB 1: TRADING SETTINGS ---
    with tab1:
        st.subheader("🛡️ Risk Management & Trade Config")

        settings = trading_engine.default_settings
        max_loss = settings.get("MAX_LOSS_PCT", -15.0)
        tp_pct = settings.get("TP_PERCENT", 0.30)
        sl_pct = settings.get("SL_PERCENT", 0.15)
        leverage = settings.get("LEVERAGE", 20)
        risk_per_trade = settings.get("RISK_PER_TRADE", 0.01)

        # Risk Sliders
        col1, col2 = st.columns(2)
        with col1:
            new_max_loss = st.slider("Max Daily Loss %", -50.0, 0.0, max_loss, 0.1, help="Daily maximum allowed loss")
            new_tp = st.slider("Take Profit %", 0.1, 50.0, tp_pct*100, 0.1, help="Default TP per trade") / 100
            new_sl = st.slider("Stop Loss %", 0.05, 20.0, sl_pct*100, 0.05, help="Default SL per trade") / 100
        with col2:
            new_lev = st.slider("Leverage", 1, 50, leverage, help="Leverage for trades")
            new_risk = st.slider("Risk per Trade %", 0.5, 5.0, risk_per_trade*100, 0.1, help="Capital % risked per trade") / 100

        # Trading Scan & Limits
        st.subheader("📊 Scan & Trade Limits")
        col1, col2 = st.columns(2)
        with col1:
            scan_interval = st.slider("Signal Scan Interval (minutes)", 5, 120, 15)
            max_signals = st.slider("Max Signals per Scan", 1, 20, 5)
        with col2:
            max_drawdown = st.slider("Max Drawdown (%)", 5.0, 50.0, 15.0)
            tp_percent = st.slider("General Take Profit (%)", 1.0, 50.0, 15.0)
            sl_percent = st.slider("General Stop Loss (%)", 1.0, 20.0, 8.0)

        # Trading Mode
        st.subheader("💰 Trading Mode")
        real_mode = st.checkbox("Enable Real Trading", value=os.getenv("USE_REAL_TRADING", "false").lower() == "true")
        if real_mode:
            st.warning("⚠️ Real trading enabled - Proceed with caution!")

        if st.button("💾 Save Trading Settings"):
            updates = {
                "MAX_LOSS_PCT": new_max_loss,
                "TP_PERCENT": new_tp,
                "SL_PERCENT": new_sl,
                "LEVERAGE": new_lev,
                "RISK_PER_TRADE": new_risk,
                "SCAN_INTERVAL": scan_interval * 60,
                "TOP_N_SIGNALS": max_signals,
                "MAX_DRAWDOWN": max_drawdown,
                "GENERAL_TP_PERCENT": tp_percent,
                "GENERAL_SL_PERCENT": sl_percent,
                "USE_REAL_TRADING": real_mode
            }
            trading_engine.update_settings(updates)
            st.success("✅ Trading settings saved")

    # --- TAB 2: SYSTEM SETTINGS ---
    with tab2:
        st.subheader("🔑 Bybit API Credentials")
        col1, col2 = st.columns(2)
        with col1:
            api_key = st.text_input("Bybit API Key", value=os.getenv("BYBIT_API_KEY", ""), type="password")
        with col2:
            api_secret = st.text_input("Bybit API Secret", value=os.getenv("BYBIT_API_SECRET", ""), type="password")

        if st.button("💾 Save API Settings"):
            if api_key and api_secret:
                db_manager.update_setting("BYBIT_API_KEY", api_key)
                db_manager.update_setting("BYBIT_API_SECRET", api_secret)
                st.success("✅ API credentials saved")
            else:
                st.warning("⚠️ Please enter both API key and secret")

        st.markdown("---")
        st.subheader("🔔 Notifications")

        # Discord & Telegram
        col1, col2 = st.columns(2)
        with col1:
            discord_url = st.text_input("Discord Webhook URL", value=os.getenv("DISCORD_WEBHOOK_URL", ""), type="password")
            if st.button("Test Discord"):
                st.success("✅ Discord connection test (demo)")
        with col2:
            telegram_enabled = st.checkbox("Enable Telegram", value=os.getenv("TELEGRAM_ENABLED", "False")=="True")
            telegram_token = st.text_input("Telegram Bot Token", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
            telegram_chat_id = st.text_input("Telegram Chat ID", value=os.getenv("TELEGRAM_CHAT_ID", ""))
            if st.button("Test Telegram"):
                st.success("✅ Telegram connection test (demo)")

        st.markdown("---")
        st.subheader("📊 System Metrics")

        col1, col2, col3 = st.columns(3)
        with col1:
            db_health = db_manager.get_db_health()
            st.metric("Database", "✅ Connected" if db_health.get("status")=="ok" else "❌ Error")
        with col2:
            signals_count = db_manager.get_signals_count()
            st.metric("Signals", signals_count)
        with col3:
            trades_count = db_manager.get_trades_count()
            st.metric("Trades", trades_count)

        st.markdown("---")
        st.subheader("⚠️ Reset Options")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reset to Defaults"):
                db_manager.reset_all_settings_to_defaults()
                st.success("✅ Settings reset to defaults")
        with col2:
            if st.button("🗑️ Clear All Data"):
                if st.checkbox("Confirm clear all data?"):
                    # Add clear logic
                    with db_manager.get_session() as session:
                        session.query(Signal).delete()
                        session.query(Trade).delete()
                        session.query(Portfolio).delete()
                        session.commit()
                    st.success("✅ All data cleared")

        st.markdown("---")
        st.subheader("ℹ️ File / System Overview")
        col1, col2, col3 = st.columns(3)
        with col1:
            signals_folder = "reports/signals"
            st.metric("Signals Folder", len(os.listdir(signals_folder)) if os.path.exists(signals_folder) else 0)
        with col2:
            trades_folder = "reports/trades"
            st.metric("Trades Folder", len(os.listdir(trades_folder)) if os.path.exists(trades_folder) else 0)
        with col3:
            st.metric("Capital File", "✅ Exists" if os.path.exists("capital.json") else "❌ Missing")