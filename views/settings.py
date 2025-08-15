import streamlit as st
import os

def render(trading_engine, dashboard):
    st.title("⚙️ Trading Settings")
    st.subheader("🛡️ Risk Management")

    # Load current settings safely
    settings = trading_engine.default_settings
    max_loss = settings.get("MAX_LOSS_PCT", -15.0)
    tp_pct = settings.get("TP_PERCENT", 0.30)
    sl_pct = settings.get("SL_PERCENT", 0.15)
    leverage = settings.get("LEVERAGE", 20)
    risk_per_trade = settings.get("RISK_PER_TRADE", 0.01)

    # Display UI controls
    col1, col2 = st.columns(2)
    with col1:
        new_max_loss = st.slider("Max Daily Loss %", -50.0, 0.0, max_loss, 0.1)
        new_tp = st.slider("Take Profit %", 0.1, 50.0, tp_pct * 100, 0.1) / 100
        new_sl = st.slider("Stop Loss %", 0.05, 20.0, sl_pct * 100, 0.05) / 100
    with col2:
        new_lev = st.slider("Leverage", 1, 50, leverage)
        new_risk = st.slider("Risk per Trade %", 0.5, 5.0, risk_per_trade * 100, 0.1) / 100

    st.subheader("🔗 Notification Integration")
    col1, col2 = st.columns(2)
    with col1:
        discord_url = st.text_input("Discord Webhook URL", value=os.getenv("DISCORD_WEBHOOK_URL", ""), type="password")
        if st.button("Test Discord") and discord_url:
            try:
                trading_engine.test_discord_connection(discord_url)
                st.success("✅ Discord connection successful")
            except Exception as e:
                st.error(f"❌ Discord error: {e}")
    with col2:
        telegram_enabled = st.checkbox("Enable Telegram", os.getenv("TELEGRAM_ENABLED", "False") == "True")
        if telegram_enabled:
            telegram_token = st.text_input("Telegram Bot Token", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
            telegram_chat_id = st.text_input("Telegram Chat ID", value=os.getenv("TELEGRAM_CHAT_ID", ""))
            if st.button("Test Telegram"):
                try:
                    trading_engine.test_telegram_connection(telegram_token, telegram_chat_id)
                    st.success("✅ Telegram connection successful")
                except Exception as e:
                    st.error(f"❌ Telegram error: {e}")

    if st.button("💾 Save Settings"):
        trading_engine.db.update_setting("MAX_LOSS_PCT", new_max_loss)
        trading_engine.db.update_setting("TP_PERCENT", new_tp)
        trading_engine.db.update_setting("SL_PERCENT", new_sl)
        trading_engine.db.update_setting("LEVERAGE", new_lev)
        trading_engine.db.update_setting("RISK_PER_TRADE", new_risk)

        if discord_url:
            os.environ["DISCORD_WEBHOOK_URL"] = discord_url
        if telegram_enabled:
            os.environ["TELEGRAM_ENABLED"] = "True"
            os.environ["TELEGRAM_BOT_TOKEN"] = telegram_token
            os.environ["TELEGRAM_CHAT_ID"] = telegram_chat_id
        else:
            os.environ["TELEGRAM_ENABLED"] = "False"

        st.success("✅ Settings saved")
        st.rerun()

    if st.button("🔄 Reset to Defaults"):
        if hasattr(trading_engine, "reset_to_defaults"):
            trading_engine.reset_to_defaults()
            st.success("✅ Defaults restored")
            st.rerun()
        else:
            st.error("reset_to_defaults() not implemented in trading engine.")

    st.subheader("ℹ️ System Info")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Signals folder", len(os.listdir("signals")) if os.path.exists("signals") else 0)
    with col2:
        st.metric("Trades folder", len(os.listdir("trades")) if os.path.exists("trades") else 0)
    with col3:
        exists = os.path.exists("capital.json")
        st.metric("Capital File", "✅ Exists" if exists else "❌ Missing")
