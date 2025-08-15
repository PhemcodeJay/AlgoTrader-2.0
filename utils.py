from datetime import datetime
import json
import os
import pandas as pd
import numpy as np
import requests
from typing import List, Tuple, Union, Dict, Any, Optional


def calculate_indicators(data: List[Dict[str, Any]]) -> pd.DataFrame:
    if not data or len(data) < 30:
        return pd.DataFrame(data)

    df = pd.DataFrame(data)
    if df.empty or 'close' not in df.columns:
        return df

    df = df.sort_values("timestamp").reset_index(drop=True)
    df['close'] = df['close'].astype(float)

    delta = df['close'].diff().astype(float)
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'].fillna(0, inplace=True)

    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()

    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    sma = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(window=20).std()
    df['BB_upper'] = sma + (2 * std)
    df['BB_lower'] = sma - (2 * std)

    return df


def score_signal(df: pd.DataFrame) -> float:
    required_cols = ['EMA_21', 'EMA_50', 'EMA_200', 'MACD_hist', 'RSI', 'close']
    if any(col not in df.columns or df[col].empty for col in required_cols):
        return 0.0

    try:
        ema_21 = float(df['EMA_21'].iloc[-1])
        ema_50 = float(df['EMA_50'].iloc[-1])
        ema_200 = float(df['EMA_200'].iloc[-1])
        macd_hist = float(df['MACD_hist'].iloc[-1])
        rsi = float(df['RSI'].iloc[-1])
        close = float(df['close'].iloc[-1])
    except Exception:
        return 0.0

    score = 0
    if ema_21 > ema_50:
        score += 1
    if ema_50 > ema_200:
        score += 1
    if macd_hist > 0:
        score += 1
    if 30 < rsi < 70:
        score += 1
    if close > ema_21:
        score += 1

    return round(score / 5 * 100, 2)


def format_currency(value: Optional[float]) -> str:
    if value is None:
        value = 0.0
    return f"${value:,.2f}"


def format_percentage(value: Optional[float]) -> str:
    if value is None:
        value = 0.0
    return f"{value:.2f}%"


def get_trend_color(trend: str) -> str:
    trend = trend.lower()
    if trend in ("up", "bullish"):
        return "green"
    elif trend in ("down", "bearish"):
        return "red"
    return "gray"


def get_status_color(status: str) -> str:
    status = status.lower()
    if status in ("success", "complete", "active", "ok"):
        return "green"
    elif status in ("failed", "error", "inactive"):
        return "red"
    elif status in ("pending", "waiting", "in_progress"):
        return "orange"
    return "gray"


def calculate_drawdown(equity_curve: Union[List[float], pd.Series]) -> Tuple[float, pd.Series]:
    if equity_curve is None or len(equity_curve) < 2:
        return 0.0, pd.Series(dtype=float)

    series = pd.Series(equity_curve, dtype=float)
    peak = series.cummax()
    drawdown = (series - peak) / peak * 100
    max_drawdown = drawdown.min()

    return round(float(max_drawdown), 2), drawdown


def get_ticker_snapshot() -> List[Dict[str, Any]]:
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {}).get("list", [])[:50]
    except Exception as e:
        print(f"Error fetching ticker snapshot: {e}")
        return []


def get_current_price(symbol: str) -> float:
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data.get("result", {}).get("list", [{}])[0].get("lastPrice")
        return float(price) if price else 0.0
    except Exception as e:
        print(f"Error fetching current price for {symbol}: {e}")
        return 0.0


def save_signal_json(signal: Dict[str, Any], symbol: str, folder: str = "reports/signals") -> None:
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder}/{symbol}_{timestamp}.json"
    try:
        with open(filename, "w") as f:
            json.dump(signal, f, indent=2)
    except Exception as e:
        print(f"[save_signal_json] Error saving signal: {e}")


def save_trade_json(trade: Dict[str, Any], folder: str = "reports/trades") -> None:
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, "trades.json")
    existing_trades: List[Dict[str, Any]] = []

    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                existing_trades = json.load(f)
        except Exception:
            pass

    existing_trades.append(trade)
    try:
        with open(file_path, "w") as f:
            json.dump(existing_trades, f, indent=2)
    except Exception as e:
        print(f"[save_trade_json] Error saving trade: {e}")


def send_discord_message(message: str) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("⚠️ DISCORD_WEBHOOK_URL is not set.")
        return

    payload = {"content": message}
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Discord message sent.")
    except Exception as e:
        print(f"❌ Failed to send Discord message: {e}")


def send_telegram_message(message: str, parse_mode: str = "HTML") -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode
    }

    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print("✅ Telegram message sent.")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def serialize_datetimes(obj):
    """
    Recursively converts all datetime objects in a dictionary or list
    into ISO 8601 string format (UTC-safe).
    """
    if isinstance(obj, dict):
        return {k: serialize_datetimes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetimes(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def validate_trading_parameters(tp_pct, sl_pct, leverage):
    """Validate trading parameters"""
    errors = []
    
    if tp_pct <= 0:
        errors.append("Take profit percentage must be positive")
    
    if sl_pct <= 0:
        errors.append("Stop loss percentage must be positive")
    
    if leverage < 1 or leverage > 50:
        errors.append("Leverage must be between 1 and 50")
    
    if tp_pct <= sl_pct:
        errors.append("Take profit should be greater than stop loss")
    
    return errors

def calculate_position_size(capital, risk_pct, entry_price, sl_price):
    """Calculate position size based on risk management"""
    try:
        risk_amount = capital * (risk_pct / 100)
        risk_per_unit = abs(entry_price - sl_price)
        
        if risk_per_unit <= 0:
            return 0
        
        position_size = risk_amount / risk_per_unit
        return round(position_size, 6)
    
    except (TypeError, ZeroDivisionError):
        return 0

def get_signal_strength_text(confidence):
    """Get signal strength description"""
    if confidence >= 90:
        return "🔥 Very Strong"
    elif confidence >= 85:
        return "💪 Strong"
    elif confidence >= 75:
        return "👍 Good"
    elif confidence >= 65:
        return "⚠️ Weak"
    else:
        return "❌ Very Weak"
