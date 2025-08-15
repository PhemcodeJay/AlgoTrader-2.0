import streamlit as st
import pandas as pd

def render(trading_engine, dashboard):
    st.set_page_config(page_title="Market Dashboard", layout="wide")
    st.image("logo.png", width=80)
    st.title("📊 Market Overview")

    # === Fetch symbols ===
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
        if hasattr(trading_engine, 'get_usdt_symbols'):
            symbols = trading_engine.get_usdt_symbols()
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
        limit = st.slider("Candles", min_value=50, max_value=200, value=50)
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
                # --- Load OHLC data ---
                data = trading_engine.get_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
                df = pd.DataFrame(data) if not isinstance(data, pd.DataFrame) else data
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

                # --- Calculate ROI / PnL (example, last candle change) ---
                last_close = df['close'].iloc[-1]
                first_close = df['close'].iloc[0]
                roi = ((last_close - first_close) / first_close) * 100

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
                    data=df.to_dict("records"),
                    symbol=symbol,
                    indicators=["MA 50", "MA 200"],
                    theme="dark",
                    layout="compact"
                )
                col.plotly_chart(fig, use_container_width=True)

                # --- Display latest signals ---
                if hasattr(trading_engine, 'get_recent_signals'):
                    signals = [s for s in trading_engine.get_recent_signals() if s.get("symbol") == symbol]
                    for signal in signals:
                        dashboard.display_signal_card(signal)

            except Exception as e:
                col.error(f"Failed to load {symbol}: {e}")
