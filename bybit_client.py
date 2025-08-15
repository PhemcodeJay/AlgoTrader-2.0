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
        self.virtual: bool = not self.use_real and not self.use_testnet

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
                self.virtual_wallet = json.load(f)
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
    def load_capital(self):
        try:
            with open("capital.json", "r") as f:
                return json.load(f)
        except Exception as e:
            logging.exception("Failed to load capital.json")
            return {
                "real": {"capital": 0.0, "available": 0.0, "used": 0.0, "currency": "USDT"},
                "virtual": {"capital": 100.0, "available": 100.0, "used": 0.0, "currency": "USDT"}
            }

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], timedelta, CaseInsensitiveDict]:
        if self.client is None:
            logger.error("[BybitClient] ❌ Client not initialized.")
            return {}, timedelta(), CaseInsensitiveDict()

        try:
            allowed_methods = {
            "get_orders": getattr(self.client, "get_orders", None),
            "get_open_orders": getattr(self.client, "get_open_orders", None),
            "get_positions": getattr(self.client, "get_positions", None),
            "get_wallet_balance": getattr(self.client, "get_wallet_balance", None),
            "place_order": getattr(self.client, "place_order", None),  # 🔥 Add this
            "amend_active_order": getattr(self.client, "amend_active_order", None),  # 🔥 And this
            "get_ticker": getattr(self.client, "get_ticker", None),
            "get_instruments_info": getattr(self.client, "get_instruments_info", None)
        }

            method_func = allowed_methods.get(method)

            if not callable(method_func):
                logger.error(f"[BybitClient] ❌ Method '{method}' not found or not callable on client.")
                return {}, timedelta(), CaseInsensitiveDict()

            start_time = datetime.now()
            raw_result = method_func(**(params or {}))
            elapsed = datetime.now() - start_time

            if not isinstance(raw_result, dict):
                logger.warning(f"[BybitClient] ⚠️ Invalid response format: {raw_result}")
                return {}, elapsed, CaseInsensitiveDict()

            if raw_result.get("retCode") != 0:
                logger.warning(
                    f"[BybitClient] ⚠️ API Error: {raw_result.get('retMsg')} "
                    f"(ErrCode: {raw_result.get('retCode')})"
                )
                return {}, elapsed, CaseInsensitiveDict()

            result = raw_result.get("result") or {}
            return result, elapsed, CaseInsensitiveDict(raw_result.get("retExtInfo", {}))

        except Exception as e:
            logger.exception(f"[BybitClient] ❌ Exception during '{method}' call: {e}")
            return {}, timedelta(), CaseInsensitiveDict()

    def get_kline(self, symbol: str, interval: str, limit: int = 200) -> Dict[str, Any]:
        response = self._send_request("kline", {"symbol": symbol, "interval": interval, "limit": limit})
        return extract_response(response)

    def get_chart_data(self, symbol: str, interval: str = "1", limit: int = 100) -> List[Dict[str, Any]]:
        raw = self.get_kline(symbol, interval, limit)
        if not raw.get("result", {}).get("list"):
            return []
        return [
            {
                "timestamp": datetime.fromtimestamp(int(item[0]) / 1000),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5])
            } for item in raw["result"]["list"]
        ]

    def wallet_balance(self, coin: str = "USDT") -> dict:
        def safe_float(val):
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        if self.use_real:
            # === Real trading: Call Bybit Unified Trading Wallet API ===
            response, _, _ = self._send_request("get_wallet_balance", {
                "accountType": "UNIFIED",
                "coin": coin
            })

            if not response:
                logger.warning("[BybitClient] ⚠️ No wallet balance response received.")
                return {"capital": 0.0, "currency": coin}

            balance_list = response.get("list", [])
            for wallet_entry in balance_list:
                if wallet_entry.get("coin") == coin:
                    available = safe_float(wallet_entry.get("availableBalance"))
                    equity = safe_float(wallet_entry.get("totalEquity", available))
                    used = max(equity - available, 0.0)

                    # --- Update capital.json ---
                    try:
                        with open("capital.json", "r") as f:
                            capital_data = json.load(f)
                    except FileNotFoundError:
                        capital_data = {
                            "real": {"capital": 0.0, "available": 0.0, "used": 0.0, "start_balance": 0.0, "currency": coin},
                            "virtual": {"capital": 100.0, "available": 100.0, "used": 0.0, "start_balance": 100.0, "currency": coin}
                        }

                    start_balance = capital_data.get("real", {}).get("start_balance", 0.0)
                    if start_balance == 0.0:
                        start_balance = equity

                    capital_data["real"] = {
                        "capital": equity,
                        "available": available,
                        "used": used,
                        "start_balance": start_balance,
                        "currency": coin
                    }

                    with open("capital.json", "w") as f:
                        json.dump(capital_data, f, indent=4)

                    return {"capital": available, "currency": coin}

            logger.warning(f"[BybitClient] ⚠️ Coin '{coin}' not found in wallet balance.")
            return {"capital": 0.0, "currency": coin}

        else:
            # === Virtual mode: Load from capital.json ===
            try:
                with open("capital.json", "r") as f:
                    capital_data = json.load(f)

                virtual = capital_data.get("virtual", {})
                available = safe_float(virtual.get("available"))
                currency = virtual.get("currency", coin)

                return {
                    "capital": available,
                    "currency": currency
                }

            except Exception as e:
                logger.exception("[BybitClient] ❌ Failed to load virtual capital.")
                return {"capital": 0.0, "currency": coin}


    def get_wallet_balance(self) -> dict:
        if self.use_real:
            # === Real trading: Call Bybit Unified Trading Wallet API ===
            coin = "USDT"
            response, _, _ = self._send_request("get_wallet_balance", {
                "accountType": "UNIFIED",
                "coin": coin
            })

            if not response:
                logger.warning("[BybitClient] ⚠️ No wallet balance response received.")
                return {"available": 0.0, "used": 0.0, "equity": 0.0, "currency": coin}

            balance_list = response.get("list", [])
            for wallet_entry in balance_list:
                if wallet_entry.get("coin") == coin:
                    available = safe_float(wallet_entry.get("availableBalance"))
                    equity = safe_float(wallet_entry.get("totalEquity", available))
                    used = max(equity - available, 0.0)

                    # --- Update capital.json ---
                    try:
                        with open("capital.json", "r") as f:
                            capital_data = json.load(f)
                    except FileNotFoundError:
                        capital_data = {
                            "real": {"capital": 0.0, "available": 0.0, "used": 0.0, "start_balance": 0.0, "currency": coin},
                            "virtual": {"capital": 100.0, "available": 100.0, "used": 0.0, "start_balance": 100.0, "currency": coin}
                        }

                    start_balance = capital_data.get("real", {}).get("start_balance", 0.0)
                    if start_balance == 0.0:
                        start_balance = equity

                    capital_data["real"] = {
                        "capital": equity,
                        "available": available,
                        "used": used,
                        "start_balance": start_balance,
                        "currency": coin
                    }

                    with open("capital.json", "w") as f:
                        json.dump(capital_data, f, indent=4)

                    return {"available": available, "used": used, "equity": equity, "currency": coin}

            logger.warning(f"[BybitClient] ⚠️ Coin '{coin}' not found in wallet balance.")
            return {"available": 0.0, "used": 0.0, "equity": 0.0, "currency": coin}

        else:
            # Virtual mode: return from capital.json
            try:
                with open("capital.json", "r") as f:
                    capital_data = json.load(f)
                virtual = capital_data.get("virtual", {})
                available = float(virtual.get("available", 0.0))
                used = float(virtual.get("used", 0.0))
                equity = available + used
                currency = virtual.get("currency", "USDT")

                return {
                    "available": available,
                    "used": used,
                    "equity": equity,
                    "currency": currency
                }
            except Exception as e:
                logger.exception("[BybitClient] ❌ Failed to load virtual capital.")
                return {
                    "available": 0.0,
                    "used": 0.0,
                    "equity": 0.0,
                    "currency": "USDT"
                }


    def calculate_margin(self, qty: float, price: float, leverage: float) -> float:
        return round((qty * price) / leverage, 2)
    
    def _save_virtual_wallet(self):
        try:
            with open("capital.json", "w", encoding="utf-8") as f:
                json.dump(self.virtual_wallet, f, indent=4)
            logger.info("[BybitClient] 💾 Virtual wallet saved to capital.json")
        except Exception as e:
            logger.exception("[BybitClient] ❌ Failed to save virtual wallet: %s", e)



    def get_qty_step(self, symbol: str) -> float:
        if not self.client:
            return 1.0

        try:
            result = self.client.get_instruments_info(category="linear", symbol=symbol)
            if isinstance(result, tuple):
                result = result[0]  # Get just the response dict

            instruments = result.get("result", {}).get("list", [])
            if instruments:
                qty_step = instruments[0].get("lotSizeFilter", {}).get("qtyStep")
                return float(qty_step)
        except Exception as e:
            logger.error(f"Failed to fetch qtyStep for {symbol}: {e}")
        return 1.0

    def save_virtual_wallet(self):
        """Save the current virtual wallet state to capital.json."""
        with open("capital.json", "w") as f:
            json.dump(self.virtual_wallet, f, indent=4)

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: Optional[float] = None,
        time_in_force: Optional[str] = "GoodTillCancel",
        reduce_only: bool = False,
        close_on_trigger: bool = False,
        order_link_id: Optional[str] = None
    ) -> Dict[str, Any]:

        # ============================
        # ✅ REAL TRADING LOGIC
        # ============================
        if self.use_real and self.client:
            if order_link_id:
                try:
                    open_orders = self._send_request("get_open_orders", {"symbol": symbol})
                    open_orders_data = extract_response(open_orders)
                    matched_order = next(
                        (o for o in open_orders_data.get("list", [])
                        if o.get("order_link_id") == order_link_id),
                        None
                    )
                    if matched_order:
                        amend_params: Dict[str, Any] = {
                            "symbol": symbol,
                            "order_link_id": order_link_id,
                            "qty": qty
                        }
                        if price is not None:
                            amend_params["price"] = price
                        response = self._send_request("amend_active_order", amend_params)
                        return extract_response(response)
                except Exception as e:
                    logger.warning(f"[Real] ⚠️ Failed to amend order with link_id={order_link_id}: {e}")

            qty_step = self.get_qty_step(symbol)
            qty = round(float(qty) / qty_step) * qty_step
            precision = str(qty_step)[::-1].find('.')
            formatted_qty = f"{qty:.{precision}f}"

            params: Dict[str, Any] = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,          # camelCase
                "qty": formatted_qty,
                "timeInForce": time_in_force,     # camelCase
                "reduceOnly": reduce_only,        # camelCase
                "closeOnTrigger": close_on_trigger  # camelCase
            }

            if price is not None:
                params["price"] = str(price)  # ensure string per API spec

            if order_link_id:
                params["orderLinkId"] = order_link_id

            response = self._send_request("place_order", params)

            try:
                data = extract_response(response)
            except Exception as e:
                logger.error(f"[Real] ❌ Failed to extract response: {e}")
                return {
                    "success": False,
                    "message": "Invalid response format",
                    "error": str(e),
                    "response": response
                }

            result = data.get("result", data)
            order_id = result.get("orderId") or result.get("order_id")
            if not order_id:
                logger.warning(f"[Real] ⚠️ No order_id returned: {response}")
                return {
                    "success": False,
                    "message": "No order ID returned",
                    "response": response
                }

            try:
                time.sleep(0.5)
                status_resp = self._send_request("get_orders", {"category": "linear", "orderId": order_id})
                status_data, _, _ = status_resp
                orders_list = status_data.get("list", [])
                if not orders_list:
                    logger.warning("[Real] ❌ No orders found in order status response.")
                    return {
                        "success": False,
                        "message": "No orders returned",
                        "order_id": order_id,
                        "response": status_data
                    }

                order_info = orders_list[0]
                order_status = order_info.get("orderStatus", "UNKNOWN")

                if order_status in ["Filled", "PartiallyFilled", "New"]:
                    logger.info("[Real] ✅ Order confirmed. Placing TP/SL limit orders...")

                    try:
                        raw_price = result.get("price")
                        entry_price: float = float(raw_price) if raw_price is not None else float(price) if price is not None else 0.0

                        # Only place TP/SL if at least partially filled
                        if order_status in ["PartiallyFilled", "Filled"]:
                            self.place_tp_sl_limit_orders(
                                symbol=symbol,
                                side=side,
                                entry_price=entry_price,
                                qty=qty,
                                order_link_id=order_link_id,
                                order_id=order_id
                            )

                    except Exception as e:
                        logger.error(f"[TP/SL] ❌ Failed to place TP/SL: {e}")

                    return {
                        "success": True,
                        "message": "Order placed successfully",
                        "order_id": order_id,
                        "status": order_status,
                        "response": result
                    }

                else:
                    logger.warning(f"[Real] ❌ Order not active: {order_info}")
                    return {
                        "success": False,
                        "message": f"Order status is '{order_status}'",
                        "order_id": order_id,
                        "response": order_info
                    }

            except Exception as e:
                logger.error(f"[Real] 🚨 Failed to validate order status: {e}")
                return {
                    "success": False,
                    "message": "Exception while checking order status",
                    "error": str(e),
                    "response": response
                }

        # ============================
        # ✅ VIRTUAL TRADING LOGIC
        # ============================
        price_used = price or 1.0
        leverage = 20
        margin = self.calculate_margin(qty, price_used, leverage)

        wallet = self.capital.get("virtual", {
            "capital": 100.0,
            "available": 100.0,
            "used": 0.0,
            "start_balance": 100.0,
            "currency": "USDT"
        })
        available_capital = wallet.get("available", 0.0)

        # 📌 MODIFY EXISTING ORDER
        existing_order = next(
            (o for o in self._virtual_orders if o["symbol"] == symbol and o["side"] == side and o["status"] == "open"),
            None
        )

        if existing_order:
            old_margin = existing_order["margin"]
            margin_diff = margin - old_margin

            if margin_diff > available_capital:
                logger.warning(f"[Virtual] ❌ Not enough capital to modify order. Needed: {margin_diff}, Available: {available_capital}")
                return {"error": "Insufficient virtual capital for modification"}

            wallet["available"] -= margin_diff
            wallet["used"] += margin_diff
            self.capital["virtual"] = wallet
            self.save_capital()

            existing_order.update({
                "qty": qty,
                "price": price_used,
                "margin": margin,
                "update_time": datetime.utcnow()
            })

            for pos in self._virtual_positions:
                if pos["order_id"] == existing_order["order_id"]:
                    pos.update({
                        "qty": qty,
                        "price": price_used,
                        "margin": margin,
                        "update_time": datetime.utcnow()
                    })
                    break

            return {
                "success": True,
                "message": "Virtual order modified successfully",
                "order_id": existing_order["order_id"],
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price_used,
                "create_time": existing_order["create_time"]
            }

        # 📌 PLACE NEW ORDER
        if margin > available_capital:
            logger.warning(f"[Virtual] ❌ Not enough capital. Needed: {margin}, Available: {available_capital}")
            return {"error": "Insufficient virtual capital"}

        closed_pos = self.close_virtual_position(symbol)
        pnl = closed_pos.get("realized_pnl", 0) if closed_pos else 0

        wallet["available"] = wallet.get("available", 0) - margin + pnl
        wallet["used"] += margin
        self.capital["virtual"] = wallet
        self.save_capital()

        order_id = f"virtual_{int(time.time() * 1000)}"
        create_time = datetime.utcnow()

        self._virtual_orders.append({
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "qty": qty,
            "price": price_used,
            "status": "open",
            "margin": margin,
            "leverage": leverage,
            "create_time": create_time
        })

        self._virtual_positions.append({
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price_used,
            "margin": margin,
            "status": "open",
            "create_time": create_time,
            "order_id": order_id
        })

        self.place_tp_sl_limit_orders(
            symbol=symbol,
            side=side,
            entry_price=price_used,
            qty=qty,
            order_id=order_id
        )
        logger.info(f"[Virtual] ✅ TP/SL placed for {symbol}")

        trade_data = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": price_used,
            "leverage": leverage,
            "margin_usdt": margin,
            "order_id": order_id,
            "status": "open",
            "timestamp": create_time,
            "virtual": True
        }
        db_manager.add_trade(trade_data)

        return {
            "message": "Virtual order placed",
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price_used,
            "create_time": create_time
        }


    def place_tp_sl_limit_orders(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        order_link_id: Optional[str] = None,
        order_id: Optional[str] = None
    ):
        tp_multiplier = 1.30  # +30% TP
        sl_multiplier = 0.90  # -10% SL (previously 0.85, now corrected)

        tp_price = round(entry_price * tp_multiplier, 4)
        sl_price = round(entry_price * sl_multiplier, 4)
        opposite_side = "Sell" if side == "Buy" else "Buy"

        qty_step = self.get_qty_step(symbol)
        precision = str(qty_step)[::-1].find('.')
        formatted_qty = f"{round(qty, precision):.{precision}f}"

        if self.use_real:
            tp_order = {
                "category": "linear",
                "symbol": symbol,
                "side": opposite_side,
                "order_type": "Limit",
                "qty": formatted_qty,
                "price": tp_price,
                "time_in_force": "GoodTillCancel",
                "reduce_only": True,
                "close_on_trigger": False
            }

            sl_order = {
                "category": "linear",
                "symbol": symbol,
                "side": opposite_side,
                "order_type": "Limit",
                "qty": formatted_qty,
                "price": sl_price,
                "time_in_force": "GoodTillCancel",
                "reduce_only": True,
                "close_on_trigger": True
            }

            if order_link_id:
                tp_order["order_link_id"] = f"{order_link_id}_TP"
                sl_order["order_link_id"] = f"{order_link_id}_SL"

            try:
                self._send_request("place_order", tp_order)
                logger.info(f"[Real] ✅ TP order placed at {tp_price} for {symbol}")
            except Exception as e:
                logger.error(f"[Real] ❌ Failed to place TP order: {e}")

            try:
                self._send_request("place_order", sl_order)
                logger.info(f"[Real] ✅ SL order placed at {sl_price} for {symbol}")
            except Exception as e:
                logger.error(f"[Real] ❌ Failed to place SL order: {e}")

        else:
            # ✅ VIRTUAL MODE
            if not order_id:
                order_id = f"virtual_{int(time.time() * 1000)}"

            tp_order = {
                "order_id": f"{order_id}_VTP",
                "symbol": symbol,
                "side": opposite_side,
                "order_type": "Limit",
                "qty": qty,
                "price": tp_price,
                "status": "open",
                "reduce_only": True,
                "close_on_trigger": False,
                "create_time": datetime.utcnow().isoformat()
            }

            sl_order = {
                "order_id": f"{order_id}_VSL",
                "symbol": symbol,
                "side": opposite_side,
                "order_type": "Limit",
                "qty": qty,
                "price": sl_price,
                "status": "open",
                "reduce_only": True,
                "close_on_trigger": True,
                "create_time": datetime.utcnow().isoformat()
            }

            self._virtual_orders.extend([tp_order, sl_order])
            logger.info(f"[Virtual] ✅ TP @ {tp_price}, SL @ {sl_price} added for {symbol}")
    
    def save_capital(self):
        """Save the capital dictionary to capital.json file."""
        try:
            with open("capital.json", "w") as f:
                json.dump(self.capital, f, indent=4)
            logging.info("[BybitClient] Capital saved successfully.")
        except Exception as e:
            logging.error(f"[BybitClient] Failed to save capital: {e}")
                
    def get_open_positions(self) -> List[Dict[str, Any]]:
        if self.use_real and self.client:
            # Get real positions from Bybit
            try:
                positions, _, _ = self._send_request("get_positions", {"category": "linear"})
                real_positions = []
                
                for pos in positions.get("list", []):
                    size = float(pos.get("size", 0))
                    if size != 0:  # Only open positions
                        real_positions.append({
                            "symbol": pos.get("symbol"),
                            "side": pos.get("side"),
                            "qty": abs(size),
                            "size": size,
                            "entry_price": float(pos.get("avgPrice", 0)),
                            "mark_price": float(pos.get("markPrice", 0)),
                            "unrealized_pnl": float(pos.get("unrealisedPnl", 0)),
                            "leverage": float(pos.get("leverage", 1)),
                            "margin": float(pos.get("positionIM", 0)),
                            "status": "open",
                            "order_id": pos.get("positionIdx", f"real_{pos.get('symbol')}")
                        })
                
                return real_positions
                
            except Exception as e:
                logger.error(f"[Real] Failed to fetch positions: {e}")
                return []
        else:
            # Return virtual positions
            return [pos for pos in self._virtual_positions if pos["status"] == "open"]
    
    def get_open_orders(
        self,
        symbol: str,
        category: str = "linear"
    ) -> Tuple[Dict[str, Any], timedelta, CaseInsensitiveDict]:
        return self._send_request(
            "get_open_orders",  # ✅ Correct pybit Unified Trading method name
            {
                "symbol": symbol,
                "category": category
            }
        )

    def get_closed_positions(self) -> List[Dict[str, Any]]:
        return [pos for pos in self._virtual_positions if pos["status"] == "closed"]

    def close_virtual_position(self, symbol: str):
        for pos in self._virtual_positions:
            if pos["symbol"] == symbol and pos["status"] == "open":
                pos["status"] = "closed"
                pos["close_time"] = datetime.utcnow()

                # ✅ Calculate PnL
                pnl = self.calculate_virtual_pnl(pos)
                pos["unrealized_pnl"] = pnl
                pos["realized_pnl"] = pnl  # Virtual PnL treated as realized
                margin = pos.get("margin", 0)

                # ✅ Update wallet
                wallet = self.virtual_wallet.get("virtual", {})
                wallet["used"] = max(wallet.get("used", 0) - margin, 0)
                wallet["available"] = wallet.get("available", 0) + margin + pnl
                self.virtual_wallet["virtual"] = wallet
                self._save_virtual_wallet()

                # ✅ Log to DB
                candles = self.get_chart_data(symbol=symbol, interval="1", limit=1)
                if candles:
                    exit_price = candles[-1]["close"]
                    db_manager.close_trade(
                        order_id=pos["order_id"],
                        exit_price=exit_price,
                        pnl=pnl
                    )
                else:
                    logger.warning(f"[Virtual] ⚠️ Could not fetch exit price for {symbol}, trade not logged.")

                logger.info(f"[Virtual] Closed {symbol}: Margin refunded: {margin}, PnL: {pnl:.2f}, New balance: {wallet['available']:.2f}")
                return pos

        logger.warning(f"[Virtual] No open position found for {symbol} to close.")
        return None

    def close_virtual_trade(self, trade_id: str) -> bool:
        """Close a virtual trade by trade ID"""
        try:
            # Find trade in database
            trade = self.db.get_trade_by_id(trade_id)
            if not trade or trade.status != "open":
                logger.warning(f"[Virtual] Trade {trade_id} not found or already closed")
                return False

            # Get current price for PnL calculation
            candles = self.get_chart_data(symbol=trade.symbol, interval="1", limit=1)
            if not candles:
                logger.error(f"[Virtual] Could not fetch current price for {trade.symbol}")
                return False

            exit_price = candles[-1]["close"]
            entry_price = float(trade.entry_price)
            qty = float(trade.qty)
            side = trade.side.lower()

            # Calculate PnL
            if side == "buy":
                pnl = (exit_price - entry_price) * qty
            else:
                pnl = (entry_price - exit_price) * qty

            # Update wallet
            try:
                with open("capital.json", "r") as f:
                    capital_data = json.load(f)
                
                virtual = capital_data.get("virtual", {})
                margin = float(trade.margin_usdt or 0)
                
                virtual["used"] = max(virtual.get("used", 0) - margin, 0)
                virtual["available"] = virtual.get("available", 0) + margin + pnl
                
                capital_data["virtual"] = virtual
                
                with open("capital.json", "w") as f:
                    json.dump(capital_data, f, indent=4)

            except Exception as e:
                logger.error(f"[Virtual] Failed to update capital.json: {e}")

            # Close trade in database
            self.db.close_trade(trade.order_id, exit_price, pnl)

            # Close virtual position if it exists
            for pos in self._virtual_positions:
                if pos.get("order_id") == trade.order_id and pos["status"] == "open":
                    pos["status"] = "closed"
                    pos["close_time"] = datetime.utcnow()
                    pos["realized_pnl"] = pnl
                    break

            logger.info(f"[Virtual] Trade {trade_id} closed: PnL {pnl:.2f}")
            return True

        except Exception as e:
            logger.error(f"[Virtual] Failed to close trade {trade_id}: {e}")
            return False

    def close_real_position(self, symbol: str) -> bool:
        """Close a real position by placing a market order"""
        if not self.client:
            logger.error("[Real] Client not initialized")
            return False

        try:
            # Get current positions
            positions, _, _ = self._send_request("get_positions", {
                "category": "linear", 
                "symbol": symbol
            })

            open_positions = [p for p in positions.get("list", []) if float(p.get("size", 0)) != 0]
            
            if not open_positions:
                logger.warning(f"[Real] No open position found for {symbol}")
                return False

            position = open_positions[0]
            size = abs(float(position["size"]))
            side = position["side"]
            
            # Determine closing side (opposite of position side)
            close_side = "Sell" if side == "Buy" else "Buy"

            # Place market order to close position
            close_params = {
                "category": "linear",
                "symbol": symbol,
                "side": close_side,
                "order_type": "Market",
                "qty": str(size),
                "reduce_only": True,
                "time_in_force": "ImmediateOrCancel"
            }

            result, _, _ = self._send_request("place_order", close_params)
            
            if result.get("orderId"):
                logger.info(f"[Real] Position close order placed for {symbol}: {result['orderId']}")
                
                # Wait a moment and check if position is closed
                time.sleep(1)
                updated_positions, _, _ = self._send_request("get_positions", {
                    "category": "linear", 
                    "symbol": symbol
                })
                
                remaining_size = 0
                if updated_positions.get("list"):
                    remaining_size = abs(float(updated_positions["list"][0].get("size", 0)))
                
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
        entry_price = float(position.get("price", 0))
        qty = float(position.get("qty", 0))
        side = position["side"].lower()

        candles = self.get_chart_data(symbol=symbol, interval="1", limit=1)
        if not candles:
            logger.warning(f"Price not available for {symbol}")
            return 0.0

        last_price = candles[-1]["close"]
        if side == "buy":
            return (last_price - entry_price) * qty
        else:
            return (entry_price - last_price) * qty

    def get_virtual_unrealized_pnls(self) -> List[Dict[str, Any]]:
        return [
            {**pos, "unrealized_pnl": self.calculate_virtual_pnl(pos)}
            for pos in self.get_open_positions()
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
        result, _, _ = self._send_request("get_ticker", {"symbol": symbol, "category": "linear"})
        return result

    def update_unrealized_pnl(self):
        if self.virtual:
            # === Virtual Trades ===
            open_trades = self.db.get_open_virtual_trades()
            for trade in open_trades:
                symbol = trade["symbol"]
                entry_price = float(trade["entry_price"])
                qty = float(trade["qty"])
                side = trade["side"].lower()

                ticker = self.get_ticker(symbol)
                if not ticker:
                    continue

                last_price = float(ticker["lastPrice"])
                pnl = (last_price - entry_price) * qty if side == "buy" else (entry_price - last_price) * qty

                # Update trade and portfolio
                self.db.update_trade_unrealized_pnl(order_id=trade["order_id"], unrealized_pnl=pnl)
                self.db.update_portfolio_unrealized_pnl(symbol, pnl, is_virtual=True)

        else:
            # === Real Positions ===
            positions = self.get_open_positions()
            for pos in positions:
                symbol = pos["symbol"]
                qty = float(pos["size"])
                entry_price = float(pos["entry_price"])
                mark_price = float(pos["mark_price"])
                side = pos["side"].lower()

                pnl = (mark_price - entry_price) * qty if side == "buy" else (entry_price - mark_price) * qty

                # Update portfolio (optional: match order_id to trade)
                self.db.update_portfolio_unrealized_pnl(symbol, pnl, is_virtual=False)

                # Optional: if you store real trades by order_id
                self.db.update_trade_unrealized_pnl(order_id=pos["order_id"], unrealized_pnl=pnl)


# Export instance
bybit_client = BybitClient()
