import streamlit as st
import pandas as pd

def render(trading_engine, dashboard):
    st.image("logo.png", width=80)
    st.title("📈 Market Analysis")

    # === Load available symbols ===
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
        if hasattr(trading_engine, 'get_usdt_symbols'):
            symbols = trading_engine.get_usdt_symbols()
    except Exception as e:
        st.error(f"Error fetching symbols: {e}")
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT"]

    selected_symbol = st.selectbox("Select Symbol", symbols) if symbols else None
    if not selected_symbol:
        st.info("No symbols available.")
        return

    # === Chart parameters ===
    col1, col2, col3 = st.columns(3)
    with col1:
        timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
    with col2:
        limit = st.slider("Candles", min_value=50, max_value=500, value=100)
    with col3:
        indicators = st.multiselect(
            "Indicators",
            options=["EMA 9", "EMA 21", "MA 50", "MA 200", "Bollinger Bands", "RSI", "MACD", "Stoch RSI", "Volume"],
            default=["MA 200", "Bollinger Bands", "RSI", "Volume"]
        )

    # === Load historical candle data ===
    try:
        with st.spinner("Loading chart data…"):
            chart_data = None
            if hasattr(trading_engine, 'get_ohlcv'):
                chart_data = trading_engine.get_ohlcv(symbol=selected_symbol, timeframe=timeframe, limit=limit)

            if chart_data is None or (hasattr(chart_data, 'empty') and chart_data.empty):
                st.warning("No historical data found for this symbol/timeframe.")
                return

            # Convert to DataFrame if not already
            if not isinstance(chart_data, pd.DataFrame):
                df = pd.DataFrame(chart_data)
            else:
                df = chart_data

            # Ensure timestamps are proper datetime
            if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df.dropna(subset=['timestamp', 'open', 'high', 'low', 'close'], inplace=True)

    except Exception as e:
        st.error(f"Failed to load historical data: {e}")
        return

    # === Render chart ===
    try:
        fig = dashboard.create_technical_chart(
            data=df.to_dict("records"),
            symbol=selected_symbol,
            indicators=indicators,
            theme="dark",
            layout="tight"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error rendering chart: {e}")
        st.write(df.head())
        return

    # === Show recent signals ===
    try:
        current_signals = [
            s for s in trading_engine.get_recent_signals()
            if s.get("symbol") == selected_symbol
        ]
        if current_signals:
            st.subheader(f"🎯 Current Signals for {selected_symbol}")
            for signal in current_signals:
                dashboard.display_signal_card(signal)
    except Exception as e:
        st.warning(f"Failed to load signals: {e}")
