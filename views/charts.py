import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone

# Map Streamlit timeframe to Binance interval
TIMEFRAME_MAP = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d"
}

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 200):
    """Fetch OHLCV data from Binance public API"""
    try:
        interval = TIMEFRAME_MAP.get(timeframe, "1h")
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        print(f"Error fetching OHLCV for {symbol}: {e}")
        return pd.DataFrame()

def render(trading_engine, dashboard):
    st.set_page_config(page_title="Market Dashboard", layout="wide")
    st.image("logo.png", width=80)
    st.title("📊 Market Overview")

    # === Fetch symbols dynamically from engine ===
    try:
        if hasattr(trading_engine, 'get_usdt_symbols'):
            symbols = trading_engine.get_usdt_symbols()
        else:
            symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"]
    except Exception as e:
        st.error(f"Error fetching symbols: {e}")
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT"]

    if not symbols:
        st.info("No symbols available.")
        return

    # === Chart parameters ===
    col1, col2 = st.columns([1, 3])
    with col1:
        timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
        limit = st.slider("Candles", min_value=200, max_value=500, value=200)
    with col2:
        st.markdown("### Mini Charts Overview")
        st.markdown("Quick glance of market movement, ROI, and signals per symbol.")

    # === Mini charts grid ===
    st.markdown("---")
    cols_per_row = 3
    rows = (len(symbols) + cols_per_row - 1) // cols_per_row

    for r in range(rows):
        cols = st.columns(cols_per_row)
        for i in range(cols_per_row):
            idx = r * cols_per_row + i
            if idx >= len(symbols):
                break
            symbol = symbols[idx]
            col = cols[i]

            try:
                # --- Fetch OHLCV from API ---
                df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
                if df.empty:
                    col.info(f"No OHLC data for {symbol}")
                    continue

                # --- Calculate ROI ---
                first_close = df['close'].iloc[0] if not df['close'].empty else 0.0
                last_close = df['close'].iloc[-1] if not df['close'].empty else 0.0
                roi = ((last_close - first_close) / first_close * 100) if first_close else 0.0

                # --- Card styling ---
                col.markdown(
                    f"""
                    <div style='
                        border-radius: 12px;
                        padding: 10px;
                        background-color: #1e1e2f;
                        margin-bottom: 15px;
                        box-shadow: 0 3px 12px rgba(0,0,0,0.3);
                        color: white;
                        text-align:center;
                    '>
                        <h4 style='margin: 0'>{symbol}</h4>
                        <span style='font-size:14px;color:{"#00FF00" if roi>=0 else "#FF4C4C"}'>
                            ROI: {roi:.2f}%
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # --- Mini chart ---
                fig = dashboard.create_technical_chart(
                    chart_data=df.to_dict("records"),
                    symbol=symbol,
                    indicators=["MA 20", "MA 200"]
                )
                col.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                col.error(f"Failed to load {symbol}: {e}")
