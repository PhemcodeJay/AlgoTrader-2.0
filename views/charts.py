import streamlit as st

def render(trading_engine, dashboard):
    st.title("📈 Market Analysis")

    # Fetch symbols safely from trading_engine client
    try:
        symbol_response = trading_engine.client.get_symbols()
        if isinstance(symbol_response, dict) and "result" in symbol_response:
            symbols = [item["name"] for item in symbol_response["result"]]
        elif isinstance(symbol_response, list):
            symbols = [item.get("symbol") or item.get("name") for item in symbol_response]
        else:
            st.warning("Unexpected symbol format from API.")
            symbols = []
    except Exception as e:
        st.error(f"Error fetching symbols: {e}")
        return

    selected_symbol = st.selectbox("Select Symbol", symbols) if symbols else None

    if not selected_symbol:
        st.info("No symbols available to select.")
        return

    # User selects timeframe, candle limit, and indicators
    col1, col2, col3 = st.columns(3)
    with col1:
        timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
    with col2:
        limit = st.slider("Candles", min_value=50, max_value=500, value=100)
    with col3:
        indicators = st.multiselect(
            "Indicators",
            options=["EMA 9", "EMA 21", "MA 50", "MA 200", "Bollinger Bands",
                     "RSI", "MACD", "Stoch RSI", "Volume"],
            default=["Bollinger Bands", "MA 200", "RSI", "Volume"]
        )

    # Fetch and render chart data with spinner UI
    with st.spinner("Loading chart data…"):
        try:
            # Prefer get_chart_data if available, else fallback to get_kline
            if hasattr(trading_engine.client, "get_chart_data"):
                chart_data = trading_engine.client.get_chart_data(selected_symbol, timeframe, limit)
            else:
                chart_data = trading_engine.client.get_kline(selected_symbol, interval=timeframe, limit=limit)
        except Exception as e:
            st.error(f"Error fetching chart data: {e}")
            return

        if not chart_data:
            st.error(f"No chart data returned for {selected_symbol}")
            return

        # Render the technical chart using dashboard helper
        fig = dashboard.create_technical_chart(chart_data, selected_symbol, indicators)
        st.plotly_chart(fig, use_container_width=True)

        # Show current signals for selected symbol
        current_signals = [
            s for s in trading_engine.get_recent_signals()
            if s.get("symbol") == selected_symbol
        ]
        if current_signals:
            st.subheader(f"🎯 Current Signals for {selected_symbol}")
            for signal in current_signals:
                dashboard.display_signal_card(signal)
