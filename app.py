import streamlit as st
from PIL import Image
from utils import get_status_color, format_currency, format_percentage, get_ticker_snapshot
from engine import engine
from dashboard_components import DashboardComponents
from automated_trader import automated_trader
from db import db_manager
from streamlit_autorefresh import st_autorefresh

# Page config
st.set_page_config(
    page_title="AlgoTrader",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.set_option("client.showErrorDetails", True)

# Sidebar logo and title
logo = Image.open("logo.png")
st.sidebar.image(logo, width=40)
st.sidebar.title("🚀 AlgoTrader")
st.sidebar.markdown("---")

# Auto refresh checkbox
auto_refresh_enabled = st.sidebar.checkbox("Auto Refresh (15 min)", value=True)
if auto_refresh_enabled:
    st_autorefresh(interval=900_000, limit=None, key="auto_refresh_15min")

@st.cache_resource
def init_components():
    return engine, DashboardComponents(engine)

trading_engine, dashboard = init_components()

# Try load ticker data for dashboard ticker bar
try:
    ticker_data = get_ticker_snapshot()
    dashboard.render_ticker(ticker_data, position="top")
except Exception as e:
    st.warning(f"⚠️ Could not load market ticker: {e}")

# Sidebar navigation menu
page = st.sidebar.selectbox(
    "Navigate",
    [
        "🏠 Dashboard",
        "📊 Signals",
        "💼 Portfolio",
        "📈 Charts",
        "🤖 Automation",
        "🗄️ Database",
        "⚙️ Settings"
    ]
)

# Manual refresh button
if st.sidebar.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()

# Sidebar wallet & status info
try:
    balance_dict = trading_engine.load_capital() or {}
    daily_pnl_pct = trading_engine.get_daily_pnl()

    balance_value = float(balance_dict.get("capital", 100.0))
    daily_pnl_value = daily_pnl_pct if isinstance(daily_pnl_pct, (int, float)) else 0.0

    status = (
        "success" if daily_pnl_value > 0
        else "failed" if daily_pnl_value < 0
        else "pending"
    )
    status_color = get_status_color(status)

    st.sidebar.metric(
        "💰 Wallet Balance",
        f"{format_currency(balance_value)}",
        f"{format_percentage(daily_pnl_value)} today"
    )

    max_loss_pct = trading_engine.default_settings.get("MAX_LOSS_PCT", -15.0)
    trading_status = "🟢 Active" if daily_pnl_value > max_loss_pct else "🔴 Paused"
    st.sidebar.markdown(
        f"**Status:** <span style='color: {status_color}'>{trading_status}</span>",
        unsafe_allow_html=True
    )

    automation_status = automated_trader.get_status()
    automation_color = "#00d4aa" if automation_status.get("running", False) else "#ff4444"
    st.sidebar.markdown(
        f"**Auto Mode:** <span style='color: {automation_color}'>{'🤖 Running' if automation_status.get('running', False) else '⏸️ Stopped'}</span>",
        unsafe_allow_html=True
    )

    db_health = db_manager.get_db_health()
    db_color = "#00d4aa" if db_health.get("status") == "ok" else "#ff4444"
    db_status = "🟢 Ok" if db_health.get("status") == "ok" else f"🔴 Error: {db_health.get('error', '')}"

    st.sidebar.markdown(
        f"**Database:** <span style='color: {db_color}'>{db_status}</span>",
        unsafe_allow_html=True
    )

except Exception as e:
    st.sidebar.error(f"❌ Sidebar Metrics Error: {e}")

# --- Page Routing ---

if page == "🏠 Dashboard":
    import views.dashboard as view
    view.render(trading_engine, dashboard, db_manager)

elif page == "📊 Signals":
    import views.signals as view
    view.render(trading_engine, dashboard)

elif page == "💼 Portfolio":
    import views.portfolio as view
    view.render(trading_engine, dashboard)

elif page == "📈 Charts":
    import views.charts as view
    view.render(trading_engine, dashboard)

elif page == "🤖 Automation":
    import views.automation as view
    view.render(trading_engine, dashboard, automated_trader)

elif page == "🗄️ Database":
    st.title("🗄️ Database Overview")

    db_health = db_manager.get_db_health()
    st.write(f"Database Health: {db_health.get('status')}")
    if db_health.get("status") != "ok":
        st.error(f"Database Error: {db_health.get('error', 'Unknown error')}")

    signals_count = db_manager.get_signals_count()
    trades_count = db_manager.get_trades_count()
    portfolio_count = db_manager.get_portfolio_count()

    st.write(f"Signals count: {signals_count}")
    st.write(f"Trades count: {trades_count}")
    st.write(f"Portfolio count: {portfolio_count}")

elif page == "⚙️ Settings":
    import views.settings as view
    view.render(trading_engine, dashboard)
