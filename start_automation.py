#!/usr/bin/env python3
"""
AlgoTrader Automation Starter Script
Run this script to start automated trading alongside your dashboard
"""

import time
import signal
import sys
import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("automation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DASHBOARD_PORT = os.getenv("DASHBOARD_PORT", "8501")  # Default to Streamlit's port

# Import automated_trader
try:
    from automated_trader import automated_trader
except ImportError as e:
    logger.error("❌ Failed to import automated_trader: %s", e)
    sys.exit(1)


def signal_handler(sig, frame):
    """Gracefully stop automation on Ctrl+C or termination signal."""
    logger.info("🛑 Stopping automation...")
    if automated_trader.stop():
        logger.info("✅ Automation stopped successfully")
    else:
        logger.error("❌ Failed to stop automation")
    sys.exit(0)


def check_environment():
    """Verify required environment variables."""
    required_vars = ["DATABASE_URL"]
    if os.getenv("USE_REAL_TRADING", "").lower() in ("1", "true", "yes"):
        required_vars.extend(["BYBIT_API_KEY", "BYBIT_API_SECRET"])
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error("❌ Missing environment variables: %s", ", ".join(missing))
        sys.exit(1)


def main():
    check_environment()
    logger.info("🚀 AlgoTrader Automated Trading")
    logger.info("=" * 50)
    logger.info("This script runs the automated trading system alongside your dashboard.")
    logger.info("Automation features:")
    logger.info("  • Generate trading signals periodically")
    logger.info("  • Execute trades automatically")
    logger.info("  • Apply risk management rules")
    logger.info("  • Log all activities")
    logger.info("\nPress Ctrl+C to stop automation")
    logger.info("=" * 50)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start automation
    try:
        if automated_trader.start():
            logger.info("✅ Automation started successfully!")
            logger.info("📊 Monitor progress in the dashboard: http://localhost:%s", DASHBOARD_PORT)
            logger.info("🤖 Navigate to the 'Automation' tab for controls and statistics")
            logger.info("\nAutomation is running in the background...")

            while automated_trader.is_running:
                status = automated_trader.get_status()
                stats = status.get("stats", {})
                signals_generated = stats.get("signals_generated", 0)
                trades_executed = stats.get("trades_executed", 0)
                successful_trades = stats.get("successful_trades", 0)
                total_pnl = stats.get("total_pnl", 0.0)
                logger.info(
                    "📈 Status: Signals=%d, Trades=%d, Successful=%d, Total PnL=$%.2f",
                    signals_generated, trades_executed, successful_trades, total_pnl
                )
                time.sleep(60)  # Update status every 60 seconds
        else:
            logger.error("❌ Failed to start automation")
            logger.info("Check the logs for more details")
            sys.exit(1)
    except Exception as e:
        logger.error("❌ Automation failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()