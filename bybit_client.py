# bybit_client.py (fixed version)
# Fixes: Completed truncated sections.
# Added get_balance for real mode sync.
# Fixed place_order to handle real and virtual.
# Added extract_response helper.
# Focused on real mode by ensuring client is initialized correctly for real/testnet.
# Added monitor for real positions to update pnl in db.
# Fixed close_real_position to check after close if fully closed.
# Added get_ticker, get_price_step.

import os
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple, Union, List, cast
import requests
from requests.structures import CaseInsensitiveDict
from db import db_manager
from typing import Optional, TYPE_CHECKING
from pybit.unified_trading import HTTP


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

if TYPE_CHECKING:
    from pybit.unified_trading import HTTP

def extract_response(response: Union[Dict[str, Any], Tuple[Any, ...]]) -> Dict[str, Any]:
    if isinstance(response, tuple):
        if len(response) >= 1 and isinstance(response[0], dict):
            return response[0]
        logger.warning("Unexpected tuple response format")
        return {}
    elif isinstance(response, dict):
        return response
    else:
        logger.warning(f"Unexpected response type: {type(response)}")
        return {}

def safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0

class BybitClient:
    def __init__(self):
        # 💡 Trading mode
        self.use_real: bool = os.getenv("USE_REAL_TRADING", "").strip().lower() in ("1", "true", "yes")
        self.use_testnet: bool = os.getenv("BYBIT_TESTNET", "").strip().lower() in ("1", "true", "yes")
        self.virtual = not self.use_real and not self.use_testnet

        # ❌ Prevent dual mode conflict
        if self.use_real and self.use_testnet:
            logger.error("❌ Conflict: Both USE_REAL_TRADING and BYBIT_TESTNET are set. Enable only one.")
            self.client = None
            return

        # ✅ Basic attributes
        self.capital: dict = {}
        self.capital = self.load_capital()
        self.db = db_manager
        self._virtual_orders: List[Dict[str, Any]] = []
        self._virtual_positions: List[Dict[str, Any]] = []
        self.virtual_wallet: Dict[str, Any] = {}
        self.session = requests.Session()
        self.client: Optional[HTTP] = None
        self.base_url = "https://api.bybit.com"

        if HTTP is None:
            logger.error("❌ Cannot initialize Bybit client: HTTP class not available.")
            return

        # 🔑 Real Trading (Mainnet)
        if self.use_real:
            self.api_key = os.getenv("BYBIT_API_KEY", "")
            self.api_secret = os.getenv("BYBIT_API_SECRET", "")
            if not self.api_key or not self.api_secret:
                logger.error("❌ BYBIT_API_KEY and/or BYBIT_API_SECRET not set.")
                return

            try:
                self.client = HTTP(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=False
                )
                logger.info("[BybitClient] ✅ Live trading enabled (mainnet)")
            except Exception as e:
                logger.exception("❌ Failed to initialize Bybit mainnet client: %s", e)
                self.client = None

        # 🧪 Testnet Trading
        elif self.use_testnet:
            self.api_key = os.getenv("BYBIT_TESTNET_API_KEY", "")
            self.api_secret = os.getenv("BYBIT_TESTNET_API_SECRET", "")
            if not self.api_key or not self.api_secret:
                logger.error("❌ BYBIT_TESTNET_API_KEY and/or BYBIT_TESTNET_API_SECRET not set.")
                return

            try:
                self.client = HTTP(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=True
                )
                logger.info("[BybitClient] 🧪 Testnet trading enabled")
            except Exception as e:
                logger.exception("❌ Failed to initialize Bybit testnet client: %s", e)
                self.client = None

        # 💻 Virtual mode
        if self.virtual:
            logger.warning("⚠️ No trading mode specified. Defaulting to virtual mode.")
            self._load_virtual_wallet()

        # 🔄 Connection test
        if self.client:
            try:
                test_result = self.client.get_server_time()
                logger.debug(f"[BybitClient] Server time: {test_result}")
            except Exception as e:
                logger.warning(f"[BybitClient] ⚠️ Test connection failed: {e}")

    def _load_virtual_wallet(self):
        try:
            with open("capital.json", "r") as f:
                data = json.load(f)
                self.virtual_wallet = data.get("virtual", {"USDT": {"equity": 100.0, "available_balance": 100.0}})
            logger.info("[BybitClient] ✅ Loaded virtual wallet from capital.json")

        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("[BybitClient] ⚠️ Could not load capital.json: %s", e)
            # Fallback to default balance
            self.virtual_wallet = {
                "USDT": {
                    "equity": 100.0,
                    "available_balance": 100.0
                }
            }
            self._save_virtual_wallet()
            logger.info("[BybitClient] 💰 Initialized default virtual wallet")

        except Exception as e:
            logger.exception("[BybitClient] ❌ Unexpected error loading virtual wallet")
            self.virtual_wallet = {
                "USDT": {
                    "equity": 0.0,
                    "available_balance": 0.0
                }
            }

    def _save_virtual_wallet(self):
        data = {}
        try:
            with open("capital.json", "r") as f:
                data = json.load(f)
        except:
            pass
        data["virtual"] = self.virtual_wallet
        with open("capital.json", "w") as f:
            json.dump(data, f)

    def get_balance(self):
        if self.client:
            try:
                balance = self.client.get_wallet_balance(accountType="UNIFIED")
                resp = extract_response(balance)
                if resp.get("retCode") == 0:
                    coin_list = resp["result"].get("list", [{}])[0].get("coin", [])
                    usdt = next((c for c in coin_list if c["coin"] == "USDT"), None)
                    if usdt:
                        return {
                            "capital": float(usdt["equity"]),
                            "available": float(usdt["availableToWithdraw"]),
                            "used": float(usdt["equity"]) - float(usdt["availableToWithdraw"]),
                            "currency": "USDT"
                        }
                logger.error("Failed to get balance")
                return {"capital": 0.0, "available": 0.0, "used": 0.0, "currency": "USDT"}
            except Exception as e:
                logger.error(f"Balance error: {e}")
                return {"capital": 0.0, "available": 0.0, "used": 0.0, "currency": "USDT"}
        else:
            return {
                "capital": self.virtual_wallet["USDT"]["equity"],
                "available": self.virtual_wallet["USDT"]["available_balance"],
                "used": self.virtual_wallet["USDT"]["equity"] - self.virtual_wallet["USDT"]["available_balance"],
                "currency": "USDT"
            }

    def place_order(self, symbol: str, side: str, qty: float):
        if not self.virtual:
            try:
                order = self.client.place_order(
                    category="linear",
                    symbol=symbol,
                    side=side.capitalize(),
                    order_type="Market",
                    qty=qty,
                    time_in_force="GTC"
                )
                resp = extract_response(order)
                if resp.get("retCode") == 0:
                    order_id = resp["result"].get("orderId")
                    logger.info(f"[Real] Order placed: {symbol} {side} qty={qty} id={order_id}")
                    return order_id
                else:
                    logger.error(f"[Real] Order failed: {resp.get('retMsg')}")
                    return None
            except Exception as e:
                logger.error(f"[Real] Order error: {e}")
                return None
        else:
            order_id = f"virtual_{int(time.time() * 1000)}"
            current_price = get_current_price(symbol)
            self._virtual_orders.append({
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": current_price,
                "status": "filled",
                "fill_time": datetime.utcnow()
            })
            self._virtual_positions.append({
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry_price": current_price,
                "status": "open"
            })
            self.virtual_wallet["USDT"]["available_balance"] -= (qty * current_price) / LEVERAGE
            logger.info(f"[Virtual] Order placed: {symbol} {side} qty={qty} id={order_id}")
            return order_id

    def close_real_position(self, symbol: str) -> bool:
        try:
            positions = self.client.get_positions(category="linear", symbol=symbol)
            pos_resp = extract_response(positions)
            pos_list = pos_resp.get("list", [])
            if not pos_list:
                logger.warning(f"[Real] No position for {symbol}")
                return True
            pos = pos_list[0]
            side = "Sell" if pos["side"] == "Buy" else "Buy"
            qty = float(pos["size"])
            order = self.client.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                order_type="Market",
                qty=qty,
                reduce_only=True
            )
            resp = extract_response(order)
            if resp.get("retCode") == 0:
                # Check if fully closed
                time.sleep(2)  # Wait for execution
                updated_positions = self.client.get_positions(category="linear", symbol=symbol)
                updated_resp = extract_response(updated_positions)
                remaining_size = float(updated_resp["list"][0].get("size", 0))
                if remaining_size == 0:
                    logger.info(f"[Real] Position successfully closed for {symbol}")
                    return True
                else:
                    logger.warning(f"[Real] Position partially closed for {symbol}, remaining: {remaining_size}")
                    return False
            else:
                logger.error(f"[Real] Failed to place close order for {symbol}")
                return False
        except Exception as e:
            logger.error(f"[Real] Error closing position for {symbol}: {e}")
            return False

    def close_real_trade(self, trade_id: str) -> bool:
        """Close a real trade by trade ID"""
        try:
            trade = self.db.get_trade_by_id(trade_id)
            if not trade or trade.status != "open":
                logger.warning(f"[Real] Trade {trade_id} not found or already closed")
                return False

            return self.close_real_position(trade.symbol)

        except Exception as e:
            logger.error(f"[Real] Failed to close trade {trade_id}: {e}")
            return False


    def calculate_virtual_pnl(self, position: Dict[str, Any]) -> float:
        symbol = position["symbol"]
        entry_price = float(position.get("entry_price", 0))
        qty = float(position.get("qty", 0))
        side = position["side"].lower()

        last_price = get_current_price(symbol)
        if side == "buy":
            return (last_price - entry_price) * qty
        else:
            return (entry_price - last_price) * qty

    def get_virtual_unrealized_pnls(self) -> List[Dict[str, Any]]:
        return [
            {**pos, "unrealized_pnl": self.calculate_virtual_pnl(pos)}
            for pos in self._virtual_positions
        ]
    
    def monitor_virtual_orders(self):
        """Simulate monitoring and filling of virtual orders."""
        for order in self._virtual_orders:
            if order["status"] == "open":
                order["status"] = "filled"
                order["fill_time"] = datetime.utcnow()
                logger.info(f"[Virtual] Order {order['order_id']} filled at {order['price']}")

        for pos in self._virtual_positions:
            if pos["status"] == "open" and "fill_time" not in pos:
                pos["fill_time"] = datetime.utcnow()
                logger.info(f"[Virtual] Position for {pos['symbol']} marked as active.")

    def get_symbols(self):
        try:
            url = self.base_url + "/v5/market/instruments-info"
            params = {"category": "linear"}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("result", {}).get("list", [])
        except Exception as e:
            print(f"[BybitClient] ❌ Failed to fetch symbols: {e}")
            return []
        
    def get_price_step(self, symbol: str) -> float:
        if not self.client:
            return 0.01  # fallback default

        try:
            result = self.client.get_instruments_info(category="linear", symbol=symbol)
            if isinstance(result, tuple):
                result = result[0]  # Extract the dict if it's a tuple

            instruments = result.get("result", {}).get("list", [])
            if instruments:
                tick_size = instruments[0].get("priceFilter", {}).get("tickSize")
                return float(tick_size)
        except Exception as e:
            logger.error(f"Failed to fetch price step for {symbol}: {e}")
        return 0.01  # fallback default

    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("result", {}).get("list", [{}])[0]
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None

    def update_unrealized_pnl(self):
        if self.virtual:
            # === Virtual Trades ===
            open_trades = self.db.get_open_virtual_trades()
            for trade in open_trades:
                symbol = trade.symbol
                entry_price = float(trade.entry_price)
                qty = float(trade.qty)
                side = trade.side.lower()

                ticker = self.get_ticker(symbol)
                if not ticker:
                    continue

                last_price = float(ticker["lastPrice"])
                pnl = (last_price - entry_price) * qty if side == "buy" else (entry_price - last_price) * qty

                # Update trade and portfolio
                self.db.update_trade_unrealized_pnl(order_id=trade.order_id, unrealized_pnl=pnl)
                self.db.update_portfolio_unrealized_pnl(symbol, pnl, is_virtual=True)

        else:
            # === Real Positions ===
            positions = self.get_open_positions()
            for pos in positions:
                symbol = pos["symbol"]
                qty = float(pos["size"])
                entry_price = float(pos["avgPrice"])
                mark_price = float(pos["markPrice"])
                side = pos["side"].lower()

                pnl = (mark_price - entry_price) * qty if side == "buy" else (entry_price - mark_price) * qty

                # Update portfolio (optional: match order_id to trade)
                self.db.update_portfolio_unrealized_pnl(symbol, pnl, is_virtual=False)

                # Optional: if you store real trades by order_id
                self.db.update_trade_unrealized_pnl(order_id=pos.get("orderId", ""), unrealized_pnl=pnl)

    def get_open_positions(self):
        if self.virtual:
            return self._virtual_positions
        else:
            try:
                positions = self.client.get_positions(category="linear")
                resp = extract_response(positions)
                return resp.get("list", [])
            except Exception as e:
                logger.error(f"[Real] Positions error: {e}")
                return []


# Export instance
bybit_client = BybitClient()