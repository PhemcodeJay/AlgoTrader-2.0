import streamlit as st
import os
from db import db_manager

def render(trading_engine, dashboard):
    st.image("logo.png", width=80)
    st.title("⚙️ Trading & System Settings")

    tab1, tab2 = st.tabs(["📈 Trading Settings", "🛠️ System Settings"])

    # === TAB 1: TRADING SETTINGS ===
    with tab1:
        st.subheader("🛡️ Risk Management")

        settings = trading_engine.default_settings
        max_loss = settings.get("MAX_LOSS_PCT", -15.0)
        tp_pct = settings.get("TP_PERCENT", 0.30)
        sl_pct = settings.get("SL_PERCENT", 0.15)
        leverage = settings.get("LEVERAGE", 20)
        risk_per_trade = settings.get("RISK_PER_TRADE", 0.01)

        col1, col2 = st.columns(2)
        with col1:
            new_max_loss = st.slider("Max Daily Loss %", -50.0, 0.0, max_loss, 0.1)
            new_tp = st.slider("Take Profit %", 0.1, 50.0, tp_pct * 100, 0.1) / 100
            new_sl = st.slider("Stop Loss %", 0.05, 20.0, sl_pct * 100, 0.05) / 100
        with col2:
            new_lev = st.slider("Leverage", 1, 50, leverage)
            new_risk = st.slider("Risk per Trade %", 0.5, 5.0, risk_per_trade * 100, 0.1) / 100

        st.subheader("📊 Trading Configuration")
        col1, col2 = st.columns(2)
        with col1:
            scan_interval = st.slider("Signal Scan Interval (minutes)", 5, 120, 15)
            max_signals = st.slider("Max Signals per Scan", 1, 20, 5)
        with col2:
            max_drawdown = st.slider("Max Drawdown (%)", 5.0, 50.0, 15.0, step=1.0)
            tp_percent = st.slider("Take Profit (%)", 1.0, 50.0, 15.0, step=0.5)
            sl_percent = st.slider("Stop Loss (%)", 1.0, 20.0, 8.0, step=0.5)

        st.subheader("💰 Trading Mode")
        real_mode = dashboard.render_real_mode_toggle()
        if real_mode:
            st.warning("⚠️ Real trading mode is enabled. Trades will use actual funds!")
        else:
            st.info("🧪 Virtual trading mode is active. All trades are simulated.")

        if st.button("💾 Save Trading Settings"):
            try:
                updates = {
                    "MAX_LOSS_PCT": str(new_max_loss),
                    "TP_PERCENT": str(new_tp),
                    "SL_PERCENT": str(new_sl),
                    "LEVERAGE": str(new_lev),
                    "RISK_PER_TRADE": str(new_risk),
                    "SCAN_INTERVAL": scan_interval * 60,
                    "TOP_N_SIGNALS": max_signals,
                    "MAX_DRAWDOWN": max_drawdown,
                    "TP_PERCENT_GENERAL": tp_percent / 100,
                    "SL_PERCENT_GENERAL": sl_percent / 100,
                }
                for key, value in updates.items():
                    db_manager.set_setting(key, str(value))
                st.success("✅ Trading settings saved successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error saving settings: {e}")

    # === TAB 2: SYSTEM SETTINGS ===
    with tab2:
        st.subheader("🔑 API Configuration")
        bybit_testnet = st.checkbox("Use Bybit Testnet", value=True)

        col1, col2 = st.columns(2)
        with col1:
            api_key = st.text_input("Bybit API Key", type="password")
        with col2:
            api_secret = st.text_input("Bybit API Secret", type="password")

        if st.button("💾 Save API Settings"):
            if api_key and api_secret:
                st.success("✅ API credentials saved (demo)")
            else:
                st.warning("⚠️ Please enter both API key and secret")

        st.markdown("---")
        st.subheader("🔗 Notification Integration")

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Discord Notifications**")
            discord_url = st.text_input(
                "Discord Webhook URL",
                value=os.getenv("DISCORD_WEBHOOK_URL", ""),
                type="password"
            )
            if st.button("Test Discord") and discord_url:
                try:
                    st.success("✅ Discord connection test (demo)")
                except Exception as e:
                    st.error(f"❌ Discord error: {e}")

        with col2:
            st.write("**Telegram Notifications**")
            telegram_enabled = st.checkbox(
                "Enable Telegram",
                value=os.getenv("TELEGRAM_ENABLED", "False") == "True"
            )
            if telegram_enabled:
                telegram_token = st.text_input(
                    "Telegram Bot Token",
                    value=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                    type="password"
                )
                telegram_chat_id = st.text_input(
                    "Telegram Chat ID",
                    value=os.getenv("TELEGRAM_CHAT_ID", "")
                )
                if st.button("Test Telegram"):
                    try:
                        st.success("✅ Telegram connection test (demo)")
                    except Exception as e:
                        st.error(f"❌ Telegram error: {e}")

        st.markdown("---")
        st.subheader("📋 System Information")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Database Status**")
            db_health = db_manager.get_db_health()
            if db_health.get("status") == "ok":
                st.success("✅ Database connected")
            else:
                st.error(f"❌ Database error: {db_health.get('error', 'Unknown')}")

        with col2:
            st.write("**Record Counts**")
            try:
                signals_count = db_manager.get_signals_count()
                trades_count = db_manager.get_trades_count()
                st.info(f"Signals: {signals_count}")
                st.info(f"Trades: {trades_count}")
            except Exception as e:
                st.error(f"Error getting counts: {e}")

        st.markdown("---")
        st.subheader("⚠️ Reset Options")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reset to Default Settings"):
                try:
                    db_manager.reset_all_settings_to_defaults()
                    st.success("✅ Settings reset to defaults")
                except Exception as e:
                    st.error(f"❌ Error resetting settings: {e}")
        with col2:
            if st.button("🗑️ Clear All Data"):
                st.warning("⚠️ This action cannot be undone!")
                if st.button("Confirm Clear All Data"):
                    try:
                        st.success("✅ All data cleared (demo)")
                    except Exception as e:
                        st.error(f"❌ Error clearing data: {e}")

        st.markdown("---")
        st.subheader("ℹ️ File / System Metrics")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Signals folder", len(os.listdir("signals")) if os.path.exists("signals") else 0)
        with col2:
            st.metric("Trades folder", len(os.listdir("trades")) if os.path.exists("trades") else 0)
        with col3:
            exists = os.path.exists("capital.json")
            st.metric("Capital File", "✅ Exists" if exists else "❌ Missing")
