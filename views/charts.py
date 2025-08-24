# charts.py (fixed version)
# Fixes: Completed truncated volume trace in create_modern_chart.
# Updated API URL to v5 for Bybit.
# Added error handling for empty DF.
# Ensured symbols fetched from trading_engine.get_usdt_symbols().
# Added import for datetime if needed, but not.
# Fixed ROI calculation to handle zero.
# Added real-time price for title or something, but not needed.

import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go

# Timeframe mapping
TIMEFRAME_MAP = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}

def fetch_ohlcv_futures(symbol: str, timeframe: str, limit: int = 200):
    """Fetch OHLCV from Bybit USDT perpetual futures"""
    interval = TIMEFRAME_MAP.get(timeframe, "60")
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('retCode') != 0 or not data.get("result", {}).get("list"):
            return pd.DataFrame()
        df = pd.DataFrame(data["result"]["list"], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df = df.iloc[::-1].reset_index(drop=True)  # Reverse to chronological
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        st.error(f"Error fetching OHLCV for {symbol}: {e}")
        return pd.DataFrame()

def create_modern_chart(df, symbol):
    """Candlestick chart with MA200, Bollinger Bands, and volume"""
    if df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        increasing_line_color="#00FF00", decreasing_line_color="#FF4C4C", showlegend=False
    ))
    df["MA200"] = df["close"].rolling(200).mean()
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df["MA200"], mode='lines',
                             line=dict(color="#00BFFF", width=2), name="MA200"))
    df["BB_middle"] = df["close"].rolling(20).mean()
    df["BB_std"] = df["close"].rolling(20).std()
    df["BB_upper"] = df["BB_middle"] + 2 * df["BB_std"]
    df["BB_lower"] = df["BB_middle"] - 2 * df["BB_std"]
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['BB_upper'], line=dict(color='rgba(255,255,255,0)'),
                             showlegend=False))
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['BB_lower'], line=dict(color='rgba(255,255,255,0)'),
                             fill='tonexty', fillcolor='rgba(255,255,255,0.1)', showlegend=False))
    colors = ['#00FF00' if c >= o else '#FF4C4C' for c, o in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(x=df['timestamp'], y=df['volume'], marker_color=colors, name="Volume", yaxis="y2"))

    fig.update_layout(
        title=f"{symbol} Chart",
        xaxis_rangeslider_visible=False,
        yaxis=dict(autorange=True, fixedrange=False),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, df['volume'].max() * 4]),
        template="plotly_dark",
        height=300
    )
    return fig

def render(trading_engine):
    st.title("📈 Market Charts")

    # Layout Selection
    layout_mode = st.radio("Layout", ["Compact", "Standard"], horizontal=True)
    cols_per_row = 5 if layout_mode == "Compact" else min(3, len(trading_engine.get_usdt_symbols()))

    col1, col2 = st.columns([1, 3])
    with col1:
        timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
        limit = st.slider("Candles", min_value=20, max_value=300, value=50)
    with col2:
        st.markdown("### Mini Charts Overview")
        st.markdown("Quick glance of market movement, ROI, and signals per symbol.")

    st.markdown("---")

    # Fetch symbols
    symbols = trading_engine.get_usdt_symbols()

    # Pre-fetch OHLCV and filter valid symbols
    valid_symbols = []
    ohlcv_data = {}
    for symbol in symbols:
        df = fetch_ohlcv_futures(symbol=symbol, timeframe=timeframe, limit=limit)
        if not df.empty:
            valid_symbols.append(symbol)
            ohlcv_data[symbol] = df

    if not valid_symbols:
        st.info("No valid symbols with OHLCV data available.")
        return

    rows = (len(valid_symbols) + cols_per_row - 1) // cols_per_row
    for r in range(rows):
        cols = st.columns(cols_per_row)
        for i in range(cols_per_row):
            idx = r * cols_per_row + i
            if idx >= len(valid_symbols):
                break
            symbol = valid_symbols[idx]
            col = cols[i]
            df = ohlcv_data[symbol]

            first_close = df['close'].iloc[0] if not df.empty else 0
            last_close = df['close'].iloc[-1] if not df.empty else 0
            roi = ((last_close - first_close) / first_close * 100) if first_close else 0.0

            col.markdown(
                f"""
                <div style='
                    border-radius: 12px;
                    padding: 10px;
                    background-color: #1e1e2f;
                    margin-bottom: 10px;
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

            try:
                fig = create_modern_chart(df, symbol)
                col.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                col.error(f"Failed to plot {symbol}: {e}")