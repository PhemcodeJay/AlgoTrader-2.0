from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os
import sys
import pandas as pd
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from typing import Any, List, Union
import db
import signal_generator
from signal_generator import get_usdt_symbols, analyze
from bybit_client import BybitClient
from ml import MLFilter
from utils import send_discord_message, send_telegram_message, serialize_datetimes
from sqlalchemy import (
    create_engine, String, Integer, Float, DateTime, Boolean, JSON, text, update
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, Session, Mapped, mapped_column
)


# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", 3600))  # 60 minutes
DEFAULT_TOP_N_SIGNALS = int(os.getenv("TOP_N_SIGNALS", 5))


class TradingEngine:
    def __init__(self):
        print("[Engine] 🚀 Initializing TradingEngine...")
        self.client = BybitClient()
        self.db = db.db
        self.ml = MLFilter()
        self.signal_generator = signal_generator
        self.capital_file = "capital.json"
        self.logger = logger # Added for consistency in error logging

    def get_settings(self):
        scan_interval = self.db.get_setting("SCAN_INTERVAL")
        top_n_signals = self.db.get_setting("TOP_N_SIGNALS")
        scan_interval = int(scan_interval) if scan_interval else DEFAULT_SCAN_INTERVAL
        top_n_signals = int(top_n_signals) if top_n_signals else DEFAULT_TOP_N_SIGNALS
        return scan_interval, top_n_signals

    def update_settings(self, updates: dict):
        for key, value in updates.items():
            self.db.update_setting(key, value)

    def reset_to_defaults(self):
        self.db.reset_all_settings_to_defaults()

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int):
        """Get OHLCV data for charting"""
        try:
            # This should fetch from your data provider
            # For now, return None to indicate no data available
            return None
        except Exception as e:
            self.logger.error(f"Error getting OHLCV for {symbol}: {e}")
            return None

    def get_usdt_symbols(self):
        """Get list of USDT trading pairs"""
        try:
            symbols = self.client.get_symbols()
            usdt_symbols = [s["symbol"] for s in symbols if s["symbol"].endswith("USDT")]
            return usdt_symbols[:50]  # Return top 50 symbols
        except Exception as e:
            self.logger.error(f"Error getting USDT symbols: {e}")
            return ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"]


    def apply_pnl_to_capital(self, trade: dict):
        """
        Apply the PnL of a closed trade to the appropriate capital (real or virtual).
        """
        if not trade:
            logger.warning("[Engine] apply_pnl_to_capital: Empty trade data.")
            return

        pnl = trade.get("pnl")
        if pnl is None:
            logger.warning("[Engine] apply_pnl_to_capital: Trade has no PnL.")
            return

        mode = "virtual" if trade.get("virtual", False) else "real"

        try:
            capital = self.load_capital(mode)
            capital_before = capital.get("capital", 0.0)
            capital["capital"] = capital_before + float(pnl)
            self.save_capital(mode, capital)

            logger.info(
                f"[Engine] 💰 Updated {mode.upper()} capital: "
                f"{capital_before:.2f} → {capital['capital']:.2f} "
                f"(PnL: {pnl:.2f})"
            )
        except Exception as e:
            logger.error(f"[Engine] Failed to update capital for {mode.upper()}: {e}")


    def save_signal_pdf(self, signals: list[dict]):
        if not signals:
            print("[Engine] ⚠️ No signals to save.")
            return

        filename = f"reports/signals/ALL_SIGNALS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        c = canvas.Canvas(filename, pagesize=letter)

        for idx, signal in enumerate(signals):
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, 750, f"[{idx + 1}] Signal Report - {signal.get('Symbol', 'UNKNOWN')}")
            c.setFont("Helvetica", 10)
            y = 730
            for key, val in signal.items():
                c.drawString(50, y, f"{key}: {val}")
                y -= 15
                if y < 50:
                    c.showPage()
                    y = 750
            c.showPage()

        c.save()
        print(f"[Engine] ✅ Saved all signals in one PDF: {filename}")

    def save_trade_pdf(self, trades: list[dict]):
        if not trades:
            print("[Engine] ⚠️ No trades to save.")
            return

        filename = f"reports/trades/ALL_TRADES_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        c = canvas.Canvas(filename, pagesize=letter)

        for idx, trade in enumerate(trades):
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, 750, f"[{idx + 1}] Trade Report - {trade.get('symbol', 'UNKNOWN')}")
            c.setFont("Helvetica", 10)
            y = 730
            for key, val in trade.items():
                c.drawString(50, y, f"{key}: {val}")
                y -= 15
                if y < 50:
                    c.showPage()
                    y = 750
            c.showPage()

        c.save()
        print(f"[Engine] ✅ Saved all trades in one PDF: {filename}")

    def post_signal_to_discord(self, signal: dict):
        msg = (
            f"📡 **AI Signal**: `{signal.get('Symbol', 'N/A')}`\n"
            f"Side: `{signal.get('Side', 'N/A')}`\n"
            f"Entry: `{signal.get('Entry', 'N/A')}` | TP: `{signal.get('TP', 'N/A')}` | SL: `{signal.get('SL', 'N/A')}`\n"
            f"Score: `{signal.get('score', 0)}%` | Strategy: `{signal.get('strategy', '-')}`\n"
            f"Market: `{signal.get('market', 'bybit')}` | Margin: `{signal.get('margin_usdt', '-')}`"
        )
        send_discord_message(msg)

    def post_signal_to_telegram(self, signal: dict):
        msg = (
            f"📡 <b>AI Signal</b>: <code>{signal.get('Symbol', 'N/A')}</code>\n"
            f"Side: <code>{signal.get('Side', 'N/A')}</code>\n"
            f"Entry: <code>{signal.get('Entry', 'N/A')}</code> | TP: <code>{signal.get('TP', 'N/A')}</code> | SL: <code>{signal.get('SL', 'N/A')}</code>\n"
            f"Score: <code>{signal.get('score', 0)}%</code> | Strategy: <code>{signal.get('strategy', '-')}</code>\n"
            f"Market: <code>{signal.get('market', 'bybit')}</code> | Margin: <code>{signal.get('margin_usdt', '-')}</code>"
        )
        send_telegram_message(msg, parse_mode="HTML")

    def post_trade_to_discord(self, trade: dict):
        msg = (
            f"💼 **Trade Executed**: `{trade.get('symbol', 'N/A')}`\n"
            f"Side: `{trade.get('side', 'N/A')}` | Entry: `{trade.get('entry_price', 'N/A')}`\n"
            f"Qty: `{trade.get('qty', 0)}` | Order ID: `{trade.get('order_id', '-')}`\n"
            f"Mode: `{'REAL' if not trade.get('virtual') else 'VIRTUAL'}`"
        )
        send_discord_message(msg)

    def post_trade_to_telegram(self, trade: dict):
        msg = (
            f"💼 <b>Trade Executed</b>: <code>{trade.get('symbol', 'N/A')}</code>\n"
            f"Side: <code>{trade.get('side', 'N/A')}</code> | Entry: <code>{trade.get('entry_price', 'N/A')}</code>\n"
            f"Qty: <code>{trade.get('qty', 0)}</code> | Order ID: <code>{trade.get('order_id', '-')}</code>\n"
            f"Mode: <code>{'REAL' if not trade.get('virtual') else 'VIRTUAL'}</code>"
        )
        send_telegram_message(msg, parse_mode="HTML")

    def run_once(self):
        print("[Engine] 🔍 Scanning market...\n")
        scan_interval, top_n_signals = self.get_settings()
        signals = []
        trades = []
        symbols = self.get_usdt_symbols() # Changed to use the new method

        for symbol in symbols:
            enhanced = None
            raw = None

            # Step 1: Analyze signal
            try:
                raw = analyze(symbol)
            except Exception as e:
                print(f"[Engine] ❌ Failed to analyze {symbol}: {e}")
                continue

            if not raw:
                continue  # Skip empty signal

            # Step 2: Enhance signal
            try:
                enhanced = self.ml.enhance_signal(raw)

                enhanced["leverage"] = enhanced.get("leverage", 20)
                enhanced["margin_usdt"] = enhanced.get("margin_usdt") or 5.0

                print(
                    f"✅ ML Signal: {enhanced.get('Symbol')} "
                    f"({enhanced.get('Side')} @ {enhanced.get('Entry')}) → "
                    f"Score: {enhanced.get('score')}%"
                )

                indicators_clean = serialize_datetimes(enhanced)

                self.db.add_signal({
                    "symbol": enhanced.get("Symbol", ""),
                    "interval": enhanced.get("Interval", "1h"),
                    "signal_type": enhanced.get("Side", ""),
                    "score": enhanced.get("score", 0.0),
                    "indicators": indicators_clean,
                    "strategy": enhanced.get("strategy", "Auto"),
                    "side": enhanced.get("Side", "LONG"),
                    "sl": enhanced.get("SL"),
                    "tp": enhanced.get("TP"),
                    "entry": enhanced.get("Entry"),
                    "leverage": enhanced.get("leverage"),
                    "margin_usdt": enhanced.get("margin_usdt"),
                    "market": enhanced.get("market", "bybit"),
                    "created_at": datetime.now(timezone.utc),
                })

                self.post_signal_to_discord(enhanced)
                self.post_signal_to_telegram(enhanced)
                signals.append(enhanced)

                time.sleep(0.2)

            except Exception as e:
                print(f"[Engine] ❌ Error enhancing signal for {symbol}: {e}")
                continue

        # Step 3: Handle no signal case
        if not signals:
            print("[Engine] ⚠️ No tradable signals found.")
            return []

        # Step 4: Execute top trades
        signals.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_signals = signals[:top_n_signals]

        for signal in top_signals:
            print(f"[Engine] 🧠 Executing trade for {signal.get('Symbol')} (Score: {signal.get('score')}%)")
            is_real = getattr(self.client, "use_real", False)

            try:
                order = self.client.place_order(
                    symbol=signal.get("Symbol"),
                    side=signal.get("Side"),
                    order_type=signal.get("OrderType", "Market"),
                    qty=signal.get("Qty", 0),
                    price=signal.get("Entry", 0.0),
                    time_in_force=signal.get("TIF", "GoodTillCancel"),
                )
            except Exception as e:
                print(f"[Engine] ❌ Order failed for {signal.get('Symbol')}: {e}")
                continue

            if not order or "symbol" not in order:
                print(f"[Engine] ⚠️ Skipping failed order for {signal.get('Symbol')}: {order}")
                continue

            # Validate required fields
            required_order_fields = ["symbol", "side", "qty", "price", "order_id"]
            required_signal_fields = ["SL", "TP", "leverage", "margin_usdt"]
            missing_fields = [
                key for key in required_order_fields if not order.get(key)
            ] + [
                key for key in required_signal_fields if not signal.get(key)
            ]

            if missing_fields:
                print(f"[Engine] ⚠️ Missing required fields: {missing_fields}")
                continue

            # Build trade record
            trade_data = {
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": order["qty"],
                "entry_price": order["price"],
                "stop_loss": signal["SL"],
                "take_profit": signal["TP"],
                "leverage": signal["leverage"],
                "margin_usdt": signal["margin_usdt"],
                "status": "open",
                "order_id": order["order_id"],
                "timestamp": order.get("create_time") or datetime.now(timezone.utc),
                "virtual": not is_real,
                "exit_price": None,
                "pnl": None,
            }

            self.db.add_trade(trade_data)
            self.post_trade_to_discord(trade_data)
            self.post_trade_to_telegram(trade_data)
            trades.append(trade_data)

        # Step 5: Save to PDF
        self.save_signal_pdf(signals)
        self.save_trade_pdf(trades)

        # Step 6: Virtual mode monitor
        if not getattr(self.client, "use_real", False) and hasattr(self.client, "monitor_virtual_orders"):
            self.client.monitor_virtual_orders()  # type: ignore

        return top_signals


    def run_loop(self):
        print("[Engine] ♻️ Starting scan loop...")

        scan_interval = 3600  # 1 hour in seconds

        while True:
            try:
                print("\n[Engine] 🚀 Running scan...")
                self.run_once()
            except Exception as e:
                print(f"[Engine] ❌ Error during scan: {e}")

            print(f"[Engine] ⏱️ Countdown to next scan ({scan_interval // 60} minutes):")

            for remaining in range(scan_interval, 0, -1):
                # Convert seconds to hh:mm:ss format
                time_str = str(timedelta(seconds=remaining))
                sys.stdout.write(f"\r[Engine] ⏳ Time remaining: {time_str} ")
                sys.stdout.flush()
                time.sleep(1)

            print("\n[Engine] 🔁 Restarting scan...")


    def get_recent_trades(self, limit=10):
        try:
            trades = self.db.get_recent_trades(limit=limit)
            return [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "qty": t.qty,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "status": t.status,
                    "order_id": t.order_id,
                    "timestamp": t.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    "virtual": t.virtual
                }
                for t in trades
            ]
        except Exception as e:
            print(f"[Engine] ⚠️ get_recent_trades failed: {e}")
            return []

    def get_trades_by_status_and_mode(self, status="open", virtual=None):
        try:
            trades = self.db.get_trades_by_status(status)
            if virtual is not None:
                trades = [t for t in trades if t.virtual == virtual]
            return [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "qty": t.qty,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "status": t.status,
                    "order_id": t.order_id,
                    "timestamp": t.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    "virtual": t.virtual
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"[Engine] Failed to fetch trades: {e}")
            return []

    def load_capital(self, mode: str = "virtual") -> dict:
        """Load capital from JSON file."""
        if not os.path.exists(self.capital_file):
            # Initialize if missing
            initial_data = {
                "real": {
                    "capital": 0.0,
                    "start_balance": 0.0,
                    "currency": "USD"
                },
                "virtual": {
                    "capital": 100.0,
                    "start_balance": 100.0,
                    "currency": "USD"
                }
            }
            self._save_all_capital(initial_data)

        with open(self.capital_file, "r") as f:
            all_capital = json.load(f)

        if mode.lower() == "all":
            return all_capital
        return all_capital.get(mode.lower(), {})

    def save_capital(self, mode: str, data: dict):
        """Update capital JSON file for a specific mode."""
        mode = mode.lower()
        if mode not in ["real", "virtual"]:
            raise ValueError("Mode must be 'real' or 'virtual'.")

        # Load existing
        all_capital = {}
        if os.path.exists(self.capital_file):
            with open(self.capital_file, "r") as f:
                all_capital = json.load(f)

        # Update mode section
        all_capital[mode] = {
            "capital": data.get("capital", 0.0),
            "start_balance": data.get("start_balance", 0.0),
            "currency": data.get("currency", "USD")
        }

        # Save back
        self._save_all_capital(all_capital)

    def _save_all_capital(self, data: dict):
        """Write entire capital.json"""
        with open(self.capital_file, "w") as f:
            json.dump(data, f, indent=4)


    def get_daily_pnl(self, mode="real") -> float:
        trades = []
        if mode == "real":
            trades = self.get_closed_real_trades()
        elif mode == "virtual":
            trades = self.get_closed_virtual_trades()
        else:
            trades = self.get_closed_real_trades() + self.get_closed_virtual_trades()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def get_attr(t, attr, default=None):
            if isinstance(t, dict):
                return t.get(attr, default)
            return getattr(t, attr, default)

        daily_pnl = sum(
            float(get_attr(t, "pnl", 0.0) or 0.0)
            for t in trades
            if isinstance(get_attr(t, "timestamp"), str) and get_attr(t, "timestamp", "").startswith(today)
        )

        return daily_pnl


    def calculate_win_rate(self, trades: List[Union[dict, Any]]) -> float:
        def get_pnl(trade: Union[dict, Any]) -> Union[float, int, None]:
            if isinstance(trade, dict):
                return trade.get("pnl")
            return getattr(trade, "pnl", None)

        valid_trades = [t for t in trades if isinstance(get_pnl(t), (int, float))]
        if not valid_trades:
            return 0.0

        wins = []
        for t in valid_trades:
            pnl = get_pnl(t)
            if isinstance(pnl, (int, float)) and pnl > 0:
                wins.append(t)

        return round(len(wins) / len(valid_trades) * 100, 2)


    def calculate_trade_statistics(self, trades):
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "average_pnl": 0.0,
                "total_pnl": 0.0,
                "average_duration_minutes": 0.0
            }

        total_pnl = 0.0
        total_duration = 0.0
        wins = 0
        losses = 0

        for t in trades:
            pnl = getattr(t, 'pnl', None)
            duration = getattr(t, 'duration_minutes', 0)


            if isinstance(pnl, (int, float)):
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

            if isinstance(duration, (int, float)):
                total_duration += duration

        total_trades = len(trades)
        avg_pnl = total_pnl / total_trades if total_trades else 0.0
        avg_duration = total_duration / total_trades if total_trades else 0.0
        win_rate = (wins / total_trades) * 100 if total_trades else 0.0

        return {
            "total_trades": total_trades,
            "winning_trades": wins,
            "losing_trades": losses,
            "win_rate": round(win_rate, 2),
            "average_pnl": round(avg_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "average_duration_minutes": round(avg_duration, 2)
        }

    @property
    def default_settings(self):
        return {
            "SCAN_INTERVAL": int(self.db.get_setting("SCAN_INTERVAL") or DEFAULT_SCAN_INTERVAL),
            "TOP_N_SIGNALS": int(self.db.get_setting("TOP_N_SIGNALS") or DEFAULT_TOP_N_SIGNALS),
            "MAX_LOSS_PCT": float(self.db.get_setting("MAX_LOSS_PCT") or -5.0),
        }

    def get_symbols(self):
        return self.client.get_symbols()

    def get_open_virtual_trades(self):
        try:
            return self.db.get_open_virtual_trades() or []
        except Exception as e:
            self.logger.error(f"Error getting open virtual trades: {e}")
            return []

    def get_open_real_trades(self):
        try:
            return self.db.get_open_real_trades() or []
        except Exception as e:
            self.logger.error(f"Error getting open real trades: {e}")
            return []

    def get_closed_virtual_trades(self):
        try:
            return self.db.get_closed_virtual_trades() or []
        except Exception as e:
            self.logger.error(f"Error getting closed virtual trades: {e}")
            return []

    def get_closed_real_trades(self):
        try:
            return self.db.get_closed_real_trades() or []
        except Exception as e:
            self.logger.error(f"Error getting closed real trades: {e}")
            return []


    def get_open_positions(self, mode="all"):
        if mode == "real":
            return self.get_open_real_trades()
        elif mode == "virtual":
            return self.get_open_virtual_trades()
        else:
            return self.get_open_real_trades() + self.get_open_virtual_trades()

    def close_virtual_trade(self, trade_id: str) -> bool:
        """Close a virtual trade"""
        return self.client.close_virtual_trade(trade_id)

    def close_real_trade(self, trade_id: str) -> bool:
        """Close a real trade"""
        return self.client.close_real_trade(trade_id)

    def close_trade(self, trade_id: str, is_virtual: bool = None) -> bool:
        """Close a trade (auto-detect mode if not specified)"""
        if is_virtual is None:
            # Try to get trade from DB to determine mode
            try:
                trade = self.db.get_trade_by_id(trade_id)
                if trade:
                    is_virtual = trade.virtual
                else:
                    logger.warning(f"Trade {trade_id} not found")
                    return False
            except Exception as e:
                logger.error(f"Failed to determine trade mode for {trade_id}: {e}")
                return False

        if is_virtual:
            return self.close_virtual_trade(trade_id)
        else:
            return self.close_real_trade(trade_id)


# Export singleton
engine = TradingEngine()