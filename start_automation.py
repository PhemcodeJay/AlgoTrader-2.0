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
    print("\n🛑 Stopping automation...")
    automated_trader.stop()
    print("✅ Automation stopped successfully")
    sys.exit(0)


def main():
    print("🚀 AlgoTrader Automated Trading")
    print("=" * 40)
    print("This script runs the automated trading system alongside your dashboard.")
    print("The automation will:")
    print("  • Generate trading signals every 5 minutes")
    print("  • Execute trades automatically (if enabled)")
    print("  • Apply risk management rules")
    print("  • Log all activities")
    print("\nPress Ctrl+C to stop automation")
    print("=" * 40)

    signal.signal(signal.SIGINT, signal_handler)

    if automated_trader.start():
        print("✅ Automation started successfully!")
        print("📊 Monitor progress in the dashboard: http://localhost:5001")
        print("🤖 Navigate to 'Automation' tab for controls and statistics")
        print("\nAutomation is running in the background...")

        try:
            while True:
                time.sleep(60)
                status = automated_trader.get_status()
                print(f"📈 Status: {status['stats']['signals_generated']} signals generated")
        except KeyboardInterrupt:
            pass
    else:
        print("❌ Failed to start automation")
        print("Check the logs for more details")


if __name__ == "__main__":
    main()
