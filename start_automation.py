#!/usr/bin/env python3
"""
AlgoTrader Automation Starter Script
Run this script to start automated trading alongside your dashboard
"""

import time
import signal
import sys
from automated_trader import automated_trader


def signal_handler(sig, frame):
    """Gracefully stop automation on Ctrl+C or termination signal."""
    print("\n🛑 Stopping automation...")
    automated_trader.stop()
    print("✅ Automation stopped successfully")
    sys.exit(0)


def main():
    print("🚀 AlgoTrader Automated Trading")
    print("=" * 50)
    print("This script runs the automated trading system alongside your dashboard.")
    print("Automation features:")
    print("  • Generate trading signals periodically")
    print("  • Execute trades automatically")
    print("  • Apply risk management rules")
    print("  • Log all activities")
    print("\nPress Ctrl+C to stop automation")
    print("=" * 50)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start automation
    if automated_trader.start():
        print("✅ Automation started successfully!")
        print("📊 Monitor progress in the dashboard: http://localhost:5001")
        print("🤖 Navigate to the 'Automation' tab for controls and statistics")
        print("\nAutomation is running in the background...")

        try:
            while automated_trader.is_running:
                status = automated_trader.get_status()
                signals_generated = status.get("stats", {}).get("signals_generated", 0)
                print(f"📈 Signals Generated: {signals_generated}")
                time.sleep(60)  # update status every 60 seconds
        except KeyboardInterrupt:
            signal_handler(signal.SIGINT, None)
    else:
        print("❌ Failed to start automation")
        print("Check the logs for more details")
        sys.exit(1)


if __name__ == "__main__":
    main()
