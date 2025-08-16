import json
import time
import threading
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from dashboard_components import DashboardComponents

# Optional imports for production
try:
    import bybit_client
    from engine import TradingEngine
    from utils import calculate_drawdown  # type: ignore
except ImportError as e:
    logging.error(f"Import error: {e}")

    # Dummy fallback classes for type-checking
    class DummyTradingEngine:
        def __init__(self, dashboard_components: Optional[DashboardComponents] = None):
            self.db = None
            self.client = None
            self.dashboard = dashboard_components
            self.stats = {
                "signals_generated": 0,
                "trades_executed": 0,
                "successful_trades": 0,
                "total_pnl": 0.0
            }

        def run_once(self):
            return []

    TradingEngine = DummyTradingEngine

    def calculate_drawdown(equity_curve):
        return 0.0, 0.0

# Logging configuration
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
    def __init__(self, dashboard: Optional[DashboardComponents] = None):
        self.engine = TradingEngine()
        self.db = getattr(self.engine, "db", None)
        self.client = getattr(self.engine, "client", None)
        self.dashboard: Optional[DashboardComponents] = dashboard

        self.is_running = False
        self.automation_thread: Optional[threading.Thread] = None
        self.last_run_time: Optional[datetime] = None

        # Bybit client initialization
        self.bybitClient: Optional[Any] = None
        if 'bybit_client' in globals():
            try:
                self.bybitClient = bybit_client.BybitClient()
            except Exception as e:
                logger.error(f"Failed to initialize BybitClient: {e}")

        # Safe DB setting loader
        def get_setting_safe(key, default):
            if self.db and hasattr(self.db, "get_setting"):
                try:
                    value = self.db.get_setting(key)
                    if value is None:
                        return default
                    return type(default)(value)
                except Exception as e:
                    logger.error(f"Failed to load setting {key}: {e}")
            return default

        self.signal_interval = get_setting_safe("SCAN_INTERVAL", 3600)
        self.max_signals = get_setting_safe("TOP_N_SIGNALS", 5)
        self.max_drawdown_limit = get_setting_safe("MAX_DRAWDOWN", 20.0)
        self.max_daily_trades = get_setting_safe("MAX_DAILY_TRADES", 50)
        self.max_position_pct = get_setting_safe("MAX_POSITION_PCT", 5.0)

        # Automation stats
        stats_setting = get_setting_safe("AUTOMATION_STATS", "{}")
        try:
            self.stats: Dict[str, Any] = json.loads(stats_setting)
        except Exception as e:
            logger.error(f"Failed to parse AUTOMATION_STATS: {e}")
            self.stats = {
                "signals_generated": 0,
                "last_update": None,
                "trades_executed": 0,
                "successful_trades": 0,
                "failed_trades": 0,
                "total_pnl": 0.0,
            }

        self.logger = logger

    def get_today_trades(self) -> List[Any]:
        today_trades: List[Any] = []
        today = datetime.now().date()

        db = getattr(self, "db", None)
        get_trades = getattr(db, "get_trades", None)
        if db is not None and callable(get_trades):
            result = get_trades(limit=500)
            all_trades: List[Any] = list(result) if isinstance(result, list) else []
            for t in all_trades:
                ts = getattr(t, "timestamp", None)
                if isinstance(ts, datetime) and ts.date() == today:
                    today_trades.append(t)
        return today_trades

    def check_risk_limits(self) -> bool:
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
            pnl = getattr(trade, "pnl", 0.0) or 0.0
            try:
                pnl_float = float(pnl)
            except (TypeError, ValueError):
                pnl_float = 0.0
            status = getattr(trade, "status", "unknown")
            symbol = getattr(trade, "symbol", "UNKNOWN")
            self.logger.info(f"Trade Result: {symbol} - {status} - PnL: ${pnl_float:.2f}")
            setattr(trade, "_logged", True)

    def get_available_capital(self) -> float:
        try:
            bybit_client_instance: Any = getattr(self, "bybitClient", None)
            if bybit_client_instance and getattr(bybit_client_instance, "use_real", False):
                try:
                    balance_info: Dict[str, Any] = bybit_client_instance.get_wallet_balance() or {}
                    return float(balance_info.get("available_balance", 0.0))
                except Exception as e:
                    self.logger.error(f"Failed to get real balance: {e}")
                    return 0.0

            # Virtual capital
            try:
                with open("capital.json", "r") as f:
                    data = json.load(f)
                    return float(data.get("virtual", {}).get("available", 100.0))
            except FileNotFoundError:
                default_capital = {
                    "real": {"capital": 0.0, "available": 0.0, "used": 0.0, "start_balance": 0.0, "currency": "USDT"},
                    "virtual": {"capital": 100.0, "available": 100.0, "used": 0.0, "start_balance": 100.0, "currency": "USDT"}
                }
                with open("capital.json", "w") as f:
                    json.dump(default_capital, f, indent=4)
                return 100.0
            except Exception as e:
                self.logger.error(f"Failed to load virtual capital: {e}")
                return 100.0
        except Exception as e:
            self.logger.error(f"Failed to get capital: {e}")
            return 0.0

    def calculate_virtual_pnl(self, trade: dict) -> float:
        try:
            entry = float(trade.get("entry_price", 0.0))
            qty = float(trade.get("qty", 0.0))
            side = trade.get("side", "buy").lower()
            last_price = float(trade.get("last_price", entry))
            return (last_price - entry) * qty if side == "buy" else (entry - last_price) * qty
        except Exception:
            return 0.0

    def automation_cycle(self):
        start_time = datetime.now()
        while self.is_running:
            try:
                now = datetime.now()
                if (now - start_time).total_seconds() >= 3600:
                    self.logger.info("🕒 Automation session completed: 1 hour elapsed.")
                    break

                if not self.last_run_time or (now - self.last_run_time).total_seconds() >= self.signal_interval:
                    self.logger.info("⚙️ Starting automation cycle...")

                    if not self.check_risk_limits():
                        self.logger.info("⛔ Risk limits triggered. Sleeping for 1 hour.")
                        for _ in range(60):
                            if not self.is_running:
                                self.logger.info("🛑 Automation stopped manually.")
                                return
                            time.sleep(60)
                        continue

                    raw_signals = self.engine.run_once() if hasattr(self.engine, "run_once") else []
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
                        if not symbol or margin_required is None or symbol not in valid_symbols or not isinstance(capital, (int, float)) or capital < margin_required:
                            self.logger.warning(f"⚠️ Skipping signal {symbol or 'N/A'}")
                            continue
                        top_signals.append(signal)
                        capital -= margin_required
                        if len(top_signals) >= self.max_signals:
                            break

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
                                "virtual": not (getattr(self.bybitClient, "use_real", False)),
                            }

                            if self.db:
                                self.db.add_trade(trade_data)

                            # Live PnL calculation
                            pnl = 0.0
                            if trade_data.get("status", "").lower() == "open":
                                if trade_data.get("virtual"):
                                    pnl = self.calculate_virtual_pnl(trade_data)
                                elif self.dashboard and hasattr(self.dashboard, "render_ticker"):
                                    ticker = self.dashboard.render_ticker(trade_data["symbol"])
                                    last_price = float(ticker.get("lastPrice", trade_data["entry_price"])) if ticker else trade_data["entry_price"]
                                    side = trade_data.get("side", "buy").lower()
                                    qty = float(trade_data.get("qty", 0.0))
                                    pnl = (last_price - trade_data["entry_price"]) * qty if side == "buy" else (trade_data["entry_price"] - last_price) * qty

                            self.logger.info(f"✅ Trade inserted: {trade_data['symbol']} | Order ID: {order_id} | Live PnL: {pnl:+.2f}")
                        except Exception as e:
                            self.logger.error(f"❌ Failed to insert trade for {signal.get('Symbol')}: {e}", exc_info=True)

                    self.stats.setdefault("signals_generated", 0)
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
            "next_run": (self.last_run_time + timedelta(seconds=self.signal_interval)).isoformat() if self.last_run_time else None,
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
dashboard_instance = DashboardComponents(TradingEngine())
automated_trader = AutomatedTrader(dashboard=dashboard_instance)
