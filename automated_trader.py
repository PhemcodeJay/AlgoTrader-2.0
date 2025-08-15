import json
import time
import threading
import logging
from datetime import datetime, timedelta
from engine import TradingEngine
from utils import calculate_drawdown


class AutomatedTrader:
    def __init__(self):
        self.engine = TradingEngine()
        self.db = self.engine.db
        self.client = self.engine.client
        self.is_running = False
        self.automation_thread = None

        self.signal_interval = int(self.db.get_setting("SCAN_INTERVAL") or 3600)
        self.max_signals = int(self.db.get_setting("TOP_N_SIGNALS") or 5)
        self.max_drawdown_limit = float(self.db.get_setting("MAX_DRAWDOWN") or 20)
        self.max_daily_trades = int(self.db.get_setting("MAX_DAILY_TRADES") or 50)
        self.max_position_pct = float(self.db.get_setting("MAX_POSITION_PCT") or 5)

        self.last_run_time = None

        stats_setting = self.db.get_setting("AUTOMATION_STATS")
        self.stats = json.loads(stats_setting) if stats_setting else {
            "signals_generated": 0,
            "last_update": None,
            "trades_executed": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_pnl": 0.0,
        }

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("automated_trader.log", encoding="utf-8"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def get_today_trades(self):
        all_trades = self.db.get_trades(limit=500)
        today_str = datetime.now().strftime("%Y-%m-%d")
        return [t for t in all_trades if t.timestamp.strftime("%Y-%m-%d") == today_str]

    def check_risk_limits(self):
        trades = self.db.get_trades(limit=1000)

        try:
            with open("capital.json", "r") as f:
                capital_data = json.load(f)
                capital = capital_data.get("capital", 100)
        except Exception as e:
            self.logger.error(f"Failed to read capital.json: {e}")
            capital = 100

        equity_curve = [float(capital)]
        sorted_trades = sorted(trades, key=lambda t: t.timestamp)

        for trade in sorted_trades:
            pnl = getattr(trade, "pnl", 0.0)
            try:
                pnl_float = float(pnl)
            except (TypeError, ValueError):
                pnl_float = 0.0
            equity_curve.append(equity_curve[-1] + pnl_float)

        max_drawdown, _ = calculate_drawdown(equity_curve)
        if max_drawdown >= self.max_drawdown_limit:
            self.logger.warning(f"🚫 Max drawdown exceeded: {max_drawdown:.2f}%")
            return False

        if len(self.get_today_trades()) >= self.max_daily_trades:
            self.logger.warning("🚫 Max daily trades exceeded")
            return False

        return True

    def log_trade_results(self):
        today_trades = self.get_today_trades()

        for trade in today_trades:
            if getattr(trade, "_logged", False):
                continue

            symbol = getattr(trade, "symbol", "UNKNOWN")
            side = getattr(trade, "side", "N/A")
            entry = getattr(trade, "entry_price", None)
            exit_price = getattr(trade, "exit_price", None)
            pnl = getattr(trade, "pnl", None)

            if None in (entry, exit_price, pnl):
                self.logger.warning(
                    f"[SKIP] Incomplete trade data for {symbol}: Entry={entry}, Exit={exit_price}, PnL={pnl}"
                )
                continue

            if pnl is None:
                self.logger.warning(f"[SKIP] PnL is None for {symbol}")
                continue

            try:
                pnl_float = float(pnl)
            except (TypeError, ValueError):
                self.logger.warning(f"[SKIP] PnL not float-convertible for {symbol}: {pnl}")
                continue

            self.stats["trades_executed"] += 1
            self.stats["total_pnl"] += pnl_float

            if pnl_float > 0:
                self.stats["successful_trades"] += 1
                outcome = "✅ PROFIT"
            else:
                self.stats["failed_trades"] += 1
                outcome = "❌ LOSS"

            self.logger.info(
                f"[TRADE] {symbol} {side} | Entry: {entry:.4f} | Exit: {exit_price:.4f} | PnL: {pnl_float:.2f} | {outcome}"
            )

            setattr(trade, "_logged", True)


    def automation_cycle(self):
        while self.is_running:
            try:
                now = datetime.now()
                if not self.last_run_time or (now - self.last_run_time).total_seconds() >= self.signal_interval:
                    self.logger.info("⚙️ Starting automation cycle...")

                    if not self.check_risk_limits():
                        self.logger.info("⛔ Risk limits triggered. Sleeping 60s.")
                        time.sleep(60)
                        continue

                    top_signals = self.engine.run_once()[:self.max_signals]
                    self.stats["signals_generated"] += len(top_signals)
                    self.stats["last_update"] = now.isoformat()

                    self.log_trade_results()
                    self.db.update_automation_stats(self.stats)

                    self.last_run_time = now
                    self.logger.info(f"✅ Cycle complete. {len(top_signals)} signals executed. Next run in {self.signal_interval} seconds.")

                time.sleep(30)

            except Exception as e:
                self.logger.error(f"❌ Automation error: {e}", exc_info=True)
                time.sleep(90)

    def start(self):
        if self.is_running:
            self.logger.warning("⚠️ Automation already running.")
            return False
        self.is_running = True
        self.automation_thread = threading.Thread(target=self.automation_cycle, daemon=True)
        self.automation_thread.start()
        self.logger.info("✅ Automation started.")
        return True

    def stop(self):
        if not self.is_running:
            self.logger.warning("⚠️ Automation not running.")
            return False
        self.is_running = False
        if self.automation_thread and self.automation_thread.is_alive():
            self.automation_thread.join(timeout=10)
        self.logger.info("🛑 Automation stopped.")
        return True

    def get_status(self):
        return {
            "running": self.is_running,
            "settings": {
                "interval": self.signal_interval,
                "max_signals": self.max_signals,
                "max_drawdown": self.max_drawdown_limit,
                "max_daily_trades": self.max_daily_trades,
                "max_position_pct": self.max_position_pct,
            },
            "last_run": self.last_run_time.isoformat() if self.last_run_time else None,
            "next_run": (self.last_run_time + timedelta(seconds=self.signal_interval)).isoformat()
            if self.last_run_time else None,
            "stats": self.stats,
        }

    def update_settings(self, new_settings: dict):
        for key, value in new_settings.items():
            self.db.set_setting(key, value)

        self.signal_interval = int(self.db.get_setting("SCAN_INTERVAL") or 3600)
        self.max_signals = int(self.db.get_setting("TOP_N_SIGNALS") or 5)
        self.max_drawdown_limit = float(self.db.get_setting("MAX_DRAWDOWN") or 20)
        self.max_daily_trades = int(self.db.get_setting("MAX_DAILY_TRADES") or 50)
        self.max_position_pct = float(self.db.get_setting("MAX_POSITION_PCT") or 5)


# ✅ Singleton instance
automated_trader = AutomatedTrader()
