import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, Union, List, cast
from requests.structures import CaseInsensitiveDict

logger = logging.getLogger(__name__)

try:
    from pybit import HTTP  # type: ignore
except ImportError:
    HTTP = None  # type: ignore

def extract_response(
    response: Union[Dict[str, Any], Tuple[Any, ...]]
) -> Dict[str, Any]:
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

class BybitClient:
    def __init__(self):
            # Read environment variables
            self.use_real = os.getenv("USE_REAL_TRADING", "").strip().lower() in ("1", "true", "yes")
            self.use_testnet = os.getenv("BYBIT_TESTNET", "").strip().lower() in ("1", "true", "yes")

            # Conflict: both modes enabled
            if self.use_real and self.use_testnet:
                logger.error("❌ Conflict: Both USE_REAL_TRADING and BYBIT_TESTNET are set. Enable only one.")
                self.client = None
                return

            self._virtual_orders: List[Dict[str, Any]] = []

            # Try importing the pybit HTTP client
            try:
                from pybit.unified_trading import HTTP
                self._HTTP = HTTP
            except ImportError as e:
                logger.error("❌ Pybit is not installed or failed to import: %s", e)
                self.client = None
                return

            # Real trading mode (mainnet)
            if self.use_real:
                self.api_key = os.getenv("BYBIT_API_KEY", "")
                self.api_secret = os.getenv("BYBIT_API_SECRET", "")

                if not self.api_key or not self.api_secret:
                    logger.error("❌ BYBIT_API_KEY and/or BYBIT_API_SECRET not set in environment.")
                    self.client = None
                    return

                try:
                    self.client = self._HTTP(
                        api_key=self.api_key,
                        api_secret=self.api_secret,
                        testnet=False
                    )
                    logger.info("[BybitClient] ✅ Live trading enabled (mainnet)")
                except Exception as e:
                    logger.exception("❌ Failed to initialize Bybit live client: %s", e)
                    self.client = None

            # Virtual trading mode using capital.json
            elif self.use_testnet:
                self.api_key = ""
                self.api_secret = ""
                self.client = None  # No real API client
                self._load_virtual_wallet()
                logger.info("[BybitClient] 🧪 Virtual trading mode enabled (capital.json + testnet)")

            # Neither real nor testnet set
            else:
                logger.error("❌ Neither USE_REAL_TRADING nor BYBIT_TESTNET is set.")
                self.client = None


    def _load_virtual_wallet(self):
        try:
            with open("capital.json", "r") as f:
                self.virtual_wallet = json.load(f)
                logger.info("[BybitClient] ✅ Loaded virtual wallet from capital.json")
        except FileNotFoundError:
            logger.error("❌ capital.json not found.")
            self.virtual_wallet = {}
        except json.JSONDecodeError:
            logger.error("❌ capital.json is not valid JSON.")
            self.virtual_wallet = {}

    def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], timedelta, CaseInsensitiveDict]:

        if self.client is None:
            if self.use_testnet:
                logger.info("Virtual mode: request not sent.")
            elif self.use_real:
                logger.warning("Live mode: client not initialized.")
            else:
                logger.error("No trading mode set.")
            return {}, timedelta(), CaseInsensitiveDict()

        params = params or {}
        method_func = getattr(self.client, method, None)

        if not callable(method_func):
            logger.error(f"❌ Method '{method}' not found in Bybit HTTP client.")
            return {}, timedelta(), CaseInsensitiveDict()

        try:
            start_time = datetime.now()
            raw_result = method_func(**params)
            elapsed = datetime.now() - start_time

            if not isinstance(raw_result, dict):
                logger.warning(f"Unexpected response type from '{method}': {type(raw_result)}. Returning empty dict.")
                return {}, elapsed, CaseInsensitiveDict()

            result = cast(Dict[str, Any], raw_result)
            return result, elapsed, CaseInsensitiveDict()

        except Exception as e:
            logger.exception(f"❌ Exception during Bybit API call '{method}': {e}")
            return {}, timedelta(), CaseInsensitiveDict()

    def get_orderbook(self, symbol: str, limit: int = 25) -> Dict[str, Any]:
        params = {"symbol": symbol, "limit": limit}
        response = self._send_request("orderbook", params)
        return extract_response(response)

    def get_symbols(self) -> List[str]:
        response = self._send_request("get_instruments_info", {"category": "linear"})
        data = extract_response(response)
        if not data or "result" not in data or "list" not in data["result"]:
            return []
        return [item["symbol"] for item in data["result"]["list"]]

    def get_chart_data(self, symbol: str, interval: str, limit: int = 200) -> List[Dict[str, Any]]:
        raw = self.get_kline(symbol, interval, limit)
        if not raw or "result" not in raw or "list" not in raw["result"]:
            return []

        candles = []
        for item in raw["result"]["list"]:
            candles.append({
                "timestamp": datetime.fromtimestamp(int(item[0]) / 1000),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5])
            })
        return candles

    def get_kline(self, symbol: str, interval: str, limit: int = 200) -> Dict[str, Any]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = self._send_request("kline", params)
        return extract_response(response)

    def get_balance(self, coin: str = "USD") -> dict:
        # Handle virtual mode
        if self.client is None:
            try:
                with open("capital.json", "r") as f:
                    data = json.load(f)
                    capital = float(data.get("capital", 100.0))
                    currency = data.get("currency", coin)
                    return {"capital": capital, "currency": currency}
            except Exception as e:
                logger.warning(f"[BybitClient] Could not load capital.json: {e}")
                return {"capital": 100.0, "currency": coin}

        # Handle real API
        response = self._send_request("wallet_balance", {"coin": coin})
        data = extract_response(response)

        if not data or coin not in data:
            logger.warning(f"[BybitClient] No wallet data for coin '{coin}'.")
            return {"capital": 100.0, "currency": coin}

        capital = float(data[coin].get("available_balance", 100.0))
        return {"capital": capital, "currency": coin}

    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        response = self._send_request("positions", params)
        return extract_response(response)

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
        order_link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.use_real and self.client:
            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "qty": qty,
                "time_in_force": time_in_force or "GoodTillCancel",
                "reduce_only": reduce_only,
                "close_on_trigger": close_on_trigger,
            }
            if price is not None:
                params["price"] = price
            if order_link_id is not None:
                params["order_link_id"] = order_link_id
            response = self._send_request("place_active_order", params)
            return extract_response(response)
        else:
            order_id = f"virtual_{int(time.time()*1000)}"
            virtual_order = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "qty": qty,
                "price": price,
                "status": "open",
                "create_time": datetime.now(),
            }
            self._virtual_orders.append(virtual_order)
            logger.info(f"Placed virtual order: {virtual_order}")
            return virtual_order
    
    def _update_virtual_wallet(self, delta: float):
        self.virtual_wallet["capital"] -= delta
        with open("capital.json", "w") as f:
            json.dump(self.virtual_wallet, f, indent=2)


    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not order_id and not order_link_id:
            raise ValueError("Must provide either order_id or order_link_id")
        if self.use_real and self.client:
            params: Dict[str, Any] = {"symbol": symbol}
            if order_id is not None:
                params["order_id"] = order_id
            else:
                params["order_link_id"] = order_link_id
            response = self._send_request("cancel_active_order", params)
            return extract_response(response)
        else:
            for order in self._virtual_orders:
                if (order_id and order["order_id"] == order_id) or (order_link_id and order.get("order_link_id") == order_link_id):
                    order["status"] = "cancelled"
                    logger.info(f"Cancelled virtual order: {order}")
                    return {"result": "success", "order_id": order["order_id"]}
            logger.warning("Virtual order to cancel not found")
            return {"result": "error", "message": "Order not found"}

    def get_open_orders(self, symbol: str) -> Dict[str, Any]:
        if self.use_real and self.client:
            params = {"symbol": symbol}
            response = self._send_request("get_active_order", params)
            return extract_response(response)
        else:
            open_orders = [o for o in self._virtual_orders if o["symbol"] == symbol and o["status"] == "open"]
            return {"result": "success", "data": open_orders}

    def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        if self.use_real and self.client:
            params = {"symbol": symbol, "order_id": order_id}
            response = self._send_request("query_active_order", params)
            return extract_response(response)
        else:
            for order in self._virtual_orders:
                if order["order_id"] == order_id and order["symbol"] == symbol:
                    return {"result": "success", "data": order}
            return {"result": "error", "message": "Order not found"}

    def get_trade_history(self, symbol: str, limit: int = 50) -> Dict[str, Any]:
        if self.use_real and self.client:
            params = {"symbol": symbol, "limit": limit}
            response = self._send_request("execution_list", params)
            return extract_response(response)
        else:
            return {"result": "success", "data": []}

    def get_wallet_fund_records(self, coin: str = "USDT", limit: int = 50) -> Dict[str, Any]:
        if self.use_real and self.client:
            params = {"coin": coin, "limit": limit}
            response = self._send_request("wallet_fund_records", params)
            return extract_response(response)
        else:
            return {"result": "success", "data": []}

    def set_leverage(self, symbol: str, leverage: int = 20, leverage_only: bool = False) -> Dict[str, Any]:
        leverage = 20  # Always enforce 20x
        if self.use_real and self.client:
            params = {"symbol": symbol, "buy_leverage": leverage, "sell_leverage": leverage}
            response = self._send_request("set_leverage", params)
            logger.info(f"Set real leverage to 20x for {symbol}")
            return extract_response(response)
        else:
            logger.info(f"Set virtual leverage to 20x for {symbol}")
            return {"result": "success", "symbol": symbol, "leverage": 20}


    def set_position_mode(self, mode: str = "OneWay") -> Dict[str, Any]:
        """
        Sets position mode to 'OneWay' (isolated) for Futures. HedgeMode is not supported in this setup.
        """
        mode = "OneWay"  # Force to isolated one-way mode

        if self.use_real and self.client:
            params = {"mode": mode}
            response = self._send_request("set_position_mode", params)
            logger.info(f"Set real position mode to {mode}")
            return extract_response(response)
        else:
            logger.info(f"Set virtual position mode to {mode}")
            return {"result": "success", "mode": mode}


    def monitor_virtual_orders(self, check_interval: int = 10, max_checks: int = 6):
        logger.info("Starting virtual orders monitoring...")
        checks = 0
        while checks < max_checks and self._virtual_orders:
            for order in self._virtual_orders:
                elapsed = datetime.now() - order["create_time"]
                if order["status"] == "open" and elapsed > timedelta(seconds=30):
                    order["status"] = "filled"
                    order["fill_time"] = datetime.now()
                    logger.info(f"Virtual order filled: {order['order_id']} for {order['symbol']} qty {order['qty']}")
            self._virtual_orders = [o for o in self._virtual_orders if o["status"] != "filled"]
            time.sleep(check_interval)
            checks += 1
        logger.info("Finished monitoring virtual orders.")

# Export alias
bybit_client = BybitClient()