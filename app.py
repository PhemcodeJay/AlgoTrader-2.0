import streamlit as st
import sys
import os
import logging
from datetime import datetime
from PIL import Image
from utils import get_ticker_snapshot
from engine import engine
from dashboard_components import DashboardComponents
from automated_trader import automated_trader
from db import db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import views
try:
    from views import dashboard, portfolio, signals, automation, settings, charts, database
except ImportError as e:
    logger.error(f"Failed to import views: {e}")
    st.error("Application initialization failed. Please check the logs.")
    st.stop()

# Conditional import for auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False
    logger.warning("streamlit-autorefresh not available, auto-refresh disabled")

# --- Setup Page ---
try:
    st.set_page_config(
        page_title="AlgoTrader",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.set_option("client.showErrorDetails", True)
except Exception as e:
    logger.error(f"Failed to set page config: {e}")
    st.error("Failed to initialize application configuration")

# --- Sidebar Header ---
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, width=100)
    st.sidebar.title("🚀 AlgoTrader")
    st.sidebar.markdown("---")
except Exception as e:
    logger.error(f"Failed to render sidebar header: {e}")
    st.sidebar.error("Failed to load sidebar elements")

# --- Auto Refresh ---
if HAS_AUTOREFRESH:
    auto_refresh_enabled = st.sidebar.checkbox("Auto Refresh (15 min)", value=True)
    if auto_refresh_enabled:
        st_autorefresh(interval=900_000, limit=None, key="auto_refresh_15min")
else:
    st.sidebar.info("Auto-refresh disabled (package not installed)")

# --- Init Components ---
@st.cache_resource
def init_components():
    return engine, DashboardComponents(engine)

try:
    trading_engine, dashboard = init_components()
except Exception as e:
    logger.error(f"Failed to initialize components: {e}")
    st.error("Failed to initialize trading engine and dashboard components.")
    st.stop()

# --- Market Ticker Bar ---
try:
    ticker_data = get_ticker_snapshot()
    ticker_html = dashboard.render_ticker(ticker_data, position="top")
    if ticker_html:
        st.markdown(ticker_html, unsafe_allow_html=True)
except Exception as e:
    logger.warning(f"⚠️ Could not load market ticker: {e}")
    st.warning(f"⚠️ Could not load market ticker: {e}")

# --- Navigation Menu ---
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

# --- Manual Refresh Button ---
if st.sidebar.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()

# --- Sidebar Wallet Display ---
def render_wallet_summary(trading_engine):
    try:
        capital_data = trading_engine.load_capital("all") or {}
        real = capital_data.get("real", {})
        virtual = capital_data.get("virtual", {})

        # --- Virtual Wallet ---
        st.sidebar.subheader("🧪 Virtual Wallet")
        st.sidebar.metric("Available", f"${float(virtual.get('available', 0.0)):,.2f}")
        st.sidebar.metric("Total", f"${float(virtual.get('capital', 0.0)):,.2f}")

        # --- Real Wallet ---
        st.sidebar.subheader("💰 Real Wallet")
        st.sidebar.metric("Available", f"${float(real.get('available', 0.0)):,.2f}")
        st.sidebar.metric("Total", f"${float(real.get('capital', 0.0)):,.2f}")

    except Exception as e:
        logger.error(f"❌ Wallet Load Error: {e}")
        st.sidebar.error(f"❌ Wallet Load Error: {e}")

# Render Sidebar Wallet Info
render_wallet_summary(trading_engine)

# --- Page Routing ---
def route_page(page: str,
               trading_engine,
               dashboard,
               db_manager,
               automated_trader=None):
    if page == "🏠 Dashboard":
        dashboard.render(trading_engine, dashboard, db_manager)
    elif page == "📊 Signals":
        signals.render(trading_engine, dashboard)
    elif page == "💼 Portfolio":
        portfolio.render(trading_engine, dashboard)
    elif page == "📈 Charts":
        charts.render(trading_engine, dashboard)
    elif page == "🤖 Automation":
        automation.render(trading_engine, dashboard, db_manager)
    elif page == "🗄️ Database":
        database.render()
    elif page == "⚙️ Settings":
        settings.render(trading_engine, dashboard)
    else:
        st.warning(f"Unknown page: {page}")

# Execute page routing
try:
    route_page(page, trading_engine, dashboard, db_manager, automated_trader)
except Exception as e:
    logger.error(f"Error rendering page '{page}': {e}")
    st.error(f"Failed to load {page}. Please check logs.")
