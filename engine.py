from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os
import time
import json
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

import db
import signal_generator
from signal_generator import get_usdt_symbols, analyze 
from bybit_client import BybitClient
from ml import MLFilter
from utils import send_discord_message, send_telegram_message, serialize_datetimes

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
        symbols = get_usdt_symbols()

        for symbol in symbols:
            raw = analyze(symbol)
            if raw:
                enhanced = self.ml.enhance_signal(raw)
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
                    "strategy": enhanced.get("strategy", "Default"),
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

        if not signals:
            print("[Engine] ⚠️ No tradable signals found.")
            return []

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
                print(f"[Engine] ❌ Order failed: {e}")
                continue

            # ✅ FIXED: Fully structured trade_data
            trade_data = {
                "symbol": order["symbol"],
                "side": order["side"],
                "qty": order["qty"],
                "entry_price": order["price"],
                "stop_loss": signal.get("SL"),
                "take_profit": signal.get("TP"),
                "leverage": signal.get("leverage"),
                "margin_usdt": signal.get("margin_usdt"),
                "status": "open",
                "order_id": order["order_id"],
                "timestamp": order.get("create_time", datetime.now(timezone.utc)),
                "virtual": not is_real,
                "exit_price": None,
                "pnl": None,
            }

            self.db.add_trade(trade_data)
            self.post_trade_to_discord(trade_data)
            self.post_trade_to_telegram(trade_data)
            trades.append(trade_data)

        self.save_signal_pdf(signals)
        self.save_trade_pdf(trades)

        if not getattr(self.client, "use_real", False) and hasattr(self.client, "monitor_virtual_orders"):
            self.client.monitor_virtual_orders()

        return top_signals

    def run_loop(self):
        print("[Engine] ♻️ Starting scan loop...")
        while True:
            try:
                self.run_once()
            except Exception as e:
                print(f"[Engine] ❌ Error: {e}")
            scan_interval, _ = self.get_settings()
            print(f"[Engine] ⏱️ Sleeping {scan_interval} seconds...\n")
            time.sleep(scan_interval)

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

    def load_capital(self) -> dict:
        if self.client and hasattr(self.client, "get_balance"):
            try:
                return self.client.get_balance()
            except Exception as e:
                logger.warning(f"[Engine] ⚠️ get_balance failed: {e}")
        try:
            with open("capital.json", "r") as f:
                data = json.load(f)
                return {
                    "capital": float(data.get("capital", 100.0)),
                    "currency": data.get("currency", "USD"),
                }
        except Exception as e:
            logger.warning(f"[Engine] ⚠️ capital.json missing: {e}")
            return {"capital": 100.0, "currency": "USD"}

    def get_daily_pnl(self):
        if hasattr(self.db, "get_daily_pnl_pct"):
            return self.db.get_daily_pnl_pct()
        return None

    def calculate_win_rate(self, trades):
        if not trades:
            return 0.0

        valid_trades = [t for t in trades if isinstance(t.get('pnl'), (int, float))]
        if not valid_trades:
            return 0.0

        wins = sum(1 for t in valid_trades if t['pnl'] > 0)
        return round((wins / len(valid_trades)) * 100, 2)

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
            pnl = t.get("pnl")
            duration = t.get("duration_minutes", 0)

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


# Export singleton
engine = TradingEngine()