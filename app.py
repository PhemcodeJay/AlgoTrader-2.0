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

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

# --- Init Components (cached) ---
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
    dashboard.render_ticker(ticker_data, position="top")
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

# ✅ Render Sidebar Wallet Info
render_wallet_summary(trading_engine)

# --- Page Routing ---
if page == "🏠 Dashboard":
    try:
        dashboard.render()  # ✅ just call with self
    except Exception as e:
        logger.error(f"Error rendering Dashboard: {e}")
        st.error("Failed to load Dashboard. Please check logs.")

elif page == "📊 Signals":
    try:
        signals.render(trading_engine, dashboard)
    except Exception as e:
        logger.error(f"Error rendering Signals: {e}")
        st.error("Failed to load Signals. Please check logs.")

elif page == "💼 Portfolio":
    try:
        portfolio.render(trading_engine, dashboard)
    except Exception as e:
        logger.error(f"Error rendering Portfolio: {e}")
        st.error("Failed to load Portfolio. Please check logs.")

elif page == "📈 Charts":
    try:
        charts.render(trading_engine, dashboard)
    except Exception as e:
        logger.error(f"Error rendering Charts: {e}")
        st.error("Failed to load Charts. Please check logs.")

elif page == "🤖 Automation":
    try:
        automation.render(trading_engine, dashboard, automated_trader)
    except Exception as e:
        logger.error(f"Error rendering Automation: {e}")
        st.error("Failed to load Automation. Please check logs.")

elif page == "🗄️ Database":
    try:
        database.render()
    except Exception as e:
        logger.error(f"Error rendering Database: {e}")
        st.error("Failed to load Database. Please check logs.")

elif page == "⚙️ Settings":
    try:
        settings.render(trading_engine, dashboard)
    except Exception as e:
        logger.error(f"Error rendering Settings: {e}")
        st.error("Failed to load Settings. Please check logs.")