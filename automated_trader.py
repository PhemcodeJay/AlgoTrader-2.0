import json
import time
import threading
import logging
from datetime import datetime, timedelta, timezone

try:
    import bybit_client
    from engine import TradingEngine
    from utils import calculate_drawdown # type: ignore
except ImportError as e:
    logging.error(f"Import error: {e}")

    # Fallback implementations with correct attributes for type checking
    class DummyTradingEngine:
        def __init__(self):
            self.db = None
            self.client = None

        def run_once(self):
            return []

    TradingEngine = DummyTradingEngine

    def calculate_drawdown(equity_curve):
        # Return two floats to match expected signature
        return 0.0, 0.0


# Logging configuration (placed before other imports to catch early logs)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("automated_trader.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AutomatedTrader:
    def __init__(self):
        self.engine = TradingEngine()
        # Use type-ignore if engine.db or engine.client might be None (fallback)
        self.db = self.engine.db  # type: ignore
        self.client = self.engine.client  # type: ignore
        self.is_running = False
        self.automation_thread = None

        # bybit_client might be missing if import failed; guard it
        self.bybitClient = None
        if 'bybit_client' in globals():
            try:
                self.bybitClient = bybit_client.BybitClient()
            except Exception as e:
                logger.error(f"Failed to initialize BybitClient: {e}")
                self.bybitClient = None

        # Settings with fallback defaults
        self.signal_interval = int(self.db.get_setting("SCAN_INTERVAL") or 3600) if self.db else 3600
        self.max_signals = int(self.db.get_setting("TOP_N_SIGNALS") or 5) if self.db else 5
        self.max_drawdown_limit = float(self.db.get_setting("MAX_DRAWDOWN") or 20) if self.db else 20.0
        self.max_daily_trades = int(self.db.get_setting("MAX_DAILY_TRADES") or 50) if self.db else 50
        self.max_position_pct = float(self.db.get_setting("MAX_POSITION_PCT") or 5) if self.db else 5.0

        self.last_run_time = None

        stats_setting = self.db.get_setting("AUTOMATION_STATS") if self.db else None
        self.stats = json.loads(stats_setting) if stats_setting else {
            "signals_generated": 0,
            "last_update": None,
            "trades_executed": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_pnl": 0.0,
        }
        self.logger = logger

    def get_today_trades(self):
        if not self.db:
            return []
        all_trades = self.db.get_trades(limit=500)
        today_str = datetime.now().strftime("%Y-%m-%d")
        return [t for t in all_trades if hasattr(t, "timestamp") and t.timestamp.strftime("%Y-%m-%d") == today_str]

    def check_risk_limits(self):
        if not self.db:
            return True

        trades = self.db.get_trades(limit=1000)

        try:
            with open("capital.json", "r") as f:
                capital_data = json.load(f)
                capital = capital_data.get("virtual", {}).get("available", 100)

        except Exception as e:
            self.logger.error(f"Failed to read capital.json: {e}")
            capital = 100

        equity_curve = [float(capital)]
        sorted_trades = sorted(trades, key=lambda t: getattr(t, "timestamp", datetime.min))

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
        trades = self.get_today_trades()

        for trade in trades:
            if getattr(trade, "_logged", False):
                continue

            pnl = getattr(trade, "pnl", 0.0)
            if pnl is None:
                pnl = 0.0
            try:
                pnl_float = float(pnl)
            except (TypeError, ValueError):
                pnl_float = 0.0

            status = getattr(trade, "status", "unknown")
            symbol = getattr(trade, "symbol", "UNKNOWN")

            self.logger.info(f"Trade Result: {symbol} - {status} - PnL: ${pnl_float:.2f}")
            setattr(trade, "_logged", True)

            # Uncomment below if you want more detailed logging (currently unreachable due to continue above)
            # side = getattr(trade, "side", "N/A")
            # entry = getattr(trade, "entry_price", None)
            # exit_price = getattr(trade, "exit_price", None)
            #
            # if None in (entry, exit_price, pnl):
            #     self.logger.warning(f"[SKIP] Incomplete trade data for {symbol}: Entry={entry}, Exit={exit_price}, PnL={pnl}")
            #     continue
            #
            # self.stats["trades_executed"] += 1
            # self.stats["total_pnl"] += pnl_float
            #
            # if pnl_float > 0:
            #     self.stats["successful_trades"] += 1
            #     outcome = "✅ PROFIT"
            # else:
            #     self.stats["failed_trades"] += 1
            #     outcome = "❌ LOSS"
            #
            # self.logger.info(
            #     f"[TRADE] {symbol} {side} | Entry: {entry:.4f} | Exit: {exit_price:.4f} | PnL: {pnl_float:.2f} | {outcome}"
            # )

    def get_available_capital(self) -> float:
        try:
            if self.bybitClient and hasattr(self.bybitClient, 'use_real') and self.bybitClient.use_real:
                try:
                    balance_info = self.bybitClient.get_wallet_balance()
                    return float(balance_info.get("available_balance", 0.0))
                except Exception as e:
                    self.logger.error(f"Failed to get real balance: {e}")
                    return 0.0
            else:
                try:
                    with open("capital.json", "r") as f:
                        data = json.load(f)
                        return float(data.get("virtual", {}).get("capital", 100.0))
                except FileNotFoundError:
                    default_capital = {
                        "virtual": {"capital": 100.0, "start_balance": 100.0},
                        "real": {"capital": 0.0, "start_balance": 0.0}
                    }
                    with open("capital.json", "w") as f:
                        json.dump(default_capital, f, indent=4)
                    return 100.0
                except Exception as e:
                    self.logger.error(f"Failed to load virtual capital: {e}")
                    return 100.0
        except Exception as e:
            self.logger.error(f"Failed to load capital: {e}")
            return 0.0

    def automation_cycle(self):
        start_time = datetime.now()

        while self.is_running:
            try:
                now = datetime.now()

                # Stop automation after 1 hour
                if (now - start_time).total_seconds() >= 3600:
                    self.logger.info("🕒 Automation session completed: 1 hour elapsed.")
                    break

                # Time to run new signal scan
                if not self.last_run_time or (now - self.last_run_time).total_seconds() >= self.signal_interval:
                    self.logger.info("⚙️ Starting automation cycle...")

                    if not self.check_risk_limits():
                        self.logger.info("⛔ Risk limits triggered. Sleeping for 1 hour with countdown.")
                        for remaining in range(60, 0, -1):
                            if not self.is_running:
                                self.logger.info("🛑 Automation stopped manually during risk cooldown.")
                                return
                            self.logger.info(f"⏳ Sleeping... {remaining} minute(s) remaining.")
                            time.sleep(60)
                        continue

                    raw_signals = []
                    if self.engine and hasattr(self.engine, "run_once"):
                        raw_signals = self.engine.run_once() or []

                    valid_symbols = set()
                    if self.client and hasattr(self.client, "get_symbols"):
                        try:
                            valid_symbols = {s["symbol"] for s in self.client.get_symbols()}
                        except Exception as e:
                            self.logger.error(f"Failed to fetch valid symbols: {e}")

                    top_signals = []
                    capital = self.get_available_capital()

                    for signal in raw_signals:
                        symbol = signal.get("Symbol")
                        margin_required = signal.get("margin_usdt")

                        # Skip invalid signals with proper logging
                        if not symbol:
                            self.logger.warning("⚠️ Skipping signal with missing symbol.")
                            continue
                        if margin_required is None:
                            self.logger.warning(f"⚠️ Skipping {symbol}: margin_required is None.")
                            continue
                        if symbol not in valid_symbols:
                            self.logger.warning(f"⚠️ Skipping {symbol}: symbol not available or no OHLCV data.")
                            continue
                        if not isinstance(capital, (int, float)):
                            self.logger.warning(f"⚠️ Skipping {symbol}: Capital is not numeric. Value: {capital}")
                            continue
                        if capital < margin_required:
                            self.logger.warning(
                                f"⚠️ Skipping {symbol}: Not enough capital. Needed: {margin_required}, Available: {capital}"
                            )
                            continue

                        top_signals.append(signal)
                        capital -= margin_required  # reserve capital

                        if len(top_signals) >= self.max_signals:
                            break

                    # Insert trades into DB
                    for signal in top_signals:
                        try:
                            order_id = f"virtual_{int(time.time() * 1000)}"
                            trade_data = {
                                "symbol": signal.get("Symbol"),
                                "side": signal.get("side", "Buy"),
                                "qty": signal.get("qty", 0.01),
                                "entry_price": signal.get("entry_price", 0.0),
                                "exit_price": None,
                                "stop_loss": signal.get("sl"),
                                "take_profit": signal.get("tp"),
                                "leverage": signal.get("leverage", 20),
                                "margin_usdt": signal.get("margin_usdt"),
                                "pnl": None,
                                "timestamp": datetime.now(timezone.utc),
                                "status": "open",
                                "order_id": order_id,
                                "virtual": not (self.bybitClient.use_real if self.bybitClient else False),
                            }

                            if self.db:
                                self.db.add_trade(trade_data)
                            self.logger.info(f"✅ Trade inserted: {trade_data['symbol']} | Order ID: {order_id}")

                        except Exception as e:
                            self.logger.error(f"❌ Failed to insert trade for {signal.get('Symbol')}: {e}", exc_info=True)

                    # Update stats
                    self.stats["signals_generated"] += len(top_signals)
                    self.stats["last_update"] = now.isoformat()

                    self.log_trade_results()
                    if self.db:
                        self.db.update_automation_stats(self.stats)

                    self.last_run_time = now
                    self.logger.info(f"✅ Cycle complete. {len(top_signals)} trades processed. Next run in {self.signal_interval} seconds.")

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
        if self.db:
            for key, value in new_settings.items():
                self.db.set_setting(key, value)

            self.signal_interval = int(self.db.get_setting("SCAN_INTERVAL") or 3600)
            self.max_signals = int(self.db.get_setting("TOP_N_SIGNALS") or 5)
            self.max_drawdown_limit = float(self.db.get_setting("MAX_DRAWDOWN") or 20)
            self.max_daily_trades = int(self.db.get_setting("MAX_DAILY_TRADES") or 50)
            self.max_position_pct = float(self.db.get_setting("MAX_POSITION_PCT") or 5)


# Singleton instance
automated_trader = AutomatedTrader()
