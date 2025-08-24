# engine.py (fixed version)
# Fixes: Completed truncated code sections.
# Added proper handling for real and virtual in load_capital and save_capital, syncing real from Bybit.
# Fixed get_usdt_symbols to use client if available.
# Added sync for real capital in apply_pnl_to_capital (skip for real, sync instead).
# Fixed truncated calculate_win_rate and calculate_trade_statistics.
# Added missing imports.
# Ensured get_open_positions handles real by querying client and syncing to db.
# Fixed get_ohlcv to fetch from Bybit.
# Focused on real mode by adding balance sync.
# Removed dummy classes.

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
from typing import Any, List, Union, Optional
import db
import signal_generator
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
            if self.client.client:
                data = self.client.client.get_kline(category="linear", symbol=symbol, interval=timeframe, limit=limit)
                resp = extract_response(data)
                df = pd.DataFrame(resp.get("list", []), columns=['time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df = df.iloc[::-1].reset_index(drop=True)
                df = df.astype(float)
                return df
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

        virtual = trade.get("virtual", False)
        mode = "virtual" if virtual else "real"

        if not virtual:
            # For real, sync balance instead of manual update
            self.client.get_balance()  # Triggers sync if needed
            logger.info("[Engine] Real capital synced from Bybit after trade close.")
            return

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

    def load_capital(self, mode="virtual"):
        if mode == "real":
            return self.client.get_balance()
        elif mode == "virtual":
            try:
                with open(self.capital_file, "r") as f:
                    data = json.load(f)
                return data.get("virtual", {"capital": 100.0, "available": 100.0, "used": 0.0, "currency": "USDT"})
            except:
                return {"capital": 100.0, "available": 100.0, "used": 0.0, "currency": "USDT"}
        else:
            return {
                "real": self.client.get_balance(),
                "virtual": self.load_capital("virtual")
            }

    def save_capital(self, mode, capital):
        if mode == "virtual":
            data = self.load_capital("all")
            data["virtual"] = capital
            with open(self.capital_file, "w") as f:
                json.dump(data, f)
        # For real, no save needed

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
            c.drawString(50, 750, f"[{idx + 1}] Trade Report - {trade.get('Symbol', 'UNKNOWN')}")
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

    def calculate_win_rate(self, trades: List[Union[dict, Any]]) -> float:
        def get_pnl(trade: Union[dict, Any]) -> Union[float, int, None]:
            if isinstance(trade, dict):
                return trade.get("pnl")
            return getattr(trade, "pnl", None)

        valid_trades = [t for t in trades if isinstance(get_pnl(t), (int, float))]
        if not valid_trades:
            return 0.0

        wins = [t for t in valid_trades if get_pnl(t) > 0]

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
            # Sync open positions from Bybit for real
            positions = self.client.get_open_positions()
            # Sync to db if needed
            for pos in positions:
                existing = self.db.get_trade_by_id(pos.get("order_id", ""))
                if not existing:
                    self.db.add_trade({
                        "symbol": pos["symbol"],
                        "side": pos["side"],
                        "qty": pos["size"],
                        "entry_price": pos["entry_price"],
                        "status": "open",
                        "order_id": pos.get("order_id", ""),
                        "virtual": False
                    })
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

    def close_trade(self, trade_id: str, is_virtual: Optional[bool] = None) -> bool:
        """Close a trade (auto-detect mode if not specified)"""
        if is_virtual is None:
            try:
                trade = self.db.get_trade_by_id(trade_id)
                if trade:
                    is_virtual = trade.virtual
                else:
                    self.logger.warning(f"Trade {trade_id} not found")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to determine trade mode for {trade_id}: {e}")
                return False

        if is_virtual:
            return self.close_virtual_trade(trade_id)
        else:
            return self.close_real_trade(trade_id)

    def get_open_trades(self, virtual=None):
        """Return all open trades. virtual=None for all, True for virtual only, False for real only."""
        if virtual is True:
            return self.get_open_virtual_trades()
        elif virtual is False:
            return self.get_open_real_trades()
        else:
            return self.get_open_positions()

# Export singleton
engine = TradingEngine()