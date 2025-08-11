import streamlit as st
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from db import db  # using the global `db` instance
    from db import Signal
except ImportError as e:
    st.error(f"Database import error: {e}")
    db = None

from db import db_manager  # Removed duplicate st import

def render(trading_engine, dashboard):
    st.image("logo.png", width=80)
    st.title("📊 AI Trading Signals")

    # Scan Options
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol_limit = st.number_input("Symbols to Analyze", min_value=10, max_value=100, value=50)
    with col2:
        confidence_threshold = st.slider("Min Confidence %", 40, 90, 60)
    with col3:
        if st.button("🔍 Scan New Signals"):
            with st.spinner("Analyzing markets..."):
                try:
                    new_signals = trading_engine.run_once()
                    st.success(f"Generated {len(new_signals)} signals")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error generating signals: {e}")

    # Load signals from DB using db_manager
    try:
        signal_objs = db_manager.get_signals(limit=100)

        # Convert to dicts and filter
        signal_dicts = []
        for s in signal_objs:
            try:
                signal_dict = s.to_dict()
                if signal_dict.get('score', 0) >= confidence_threshold:
                    signal_dicts.append(signal_dict)
            except Exception as e:
                st.warning(f"Error converting signal to dict: {e}")
                continue

        if not signal_dicts:
            st.info("No signals found matching your criteria.")
            return

    except Exception as e:
        st.error(f"Error loading signals: {e}")
        return

    st.subheader("🧠 Recent AI Signals")

    # Display signals in tabs
    tab1, tab2 = st.tabs(["📋 Signal Cards", "📊 Signal Table"])

    with tab1:
        if signal_dicts:
            for i, signal in enumerate(signal_dicts[:10]):  # Show top 10
                with st.expander(
                    f"{signal.get('symbol', 'N/A')} - {signal.get('signal_type', 'N/A')} ({signal.get('score', 0):.1f}%)", 
                    expanded=(i == 0)
                ):
                    dashboard.display_signal_card(signal)
        else:
            st.info("No signals to display.")

    with tab2:
        if signal_dicts:
            dashboard.display_signals_table(signal_dicts)
        else:
            st.info("No signals to display in table.")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        strategies = sorted({s["strategy"] for s in signal_dicts})
        strategy_filter = st.multiselect("Filter by Strategy", options=strategies, default=strategies)

    with col2:
        side_filter = st.multiselect("Filter by Side", ["LONG", "SHORT"], default=["LONG", "SHORT"])

    with col3:
        min_score = st.slider("Minimum Score", 40, 100, 50)

    # Apply filters
    filtered_signals = [
        s for s in signal_dicts
        if s["strategy"] in strategy_filter
        and s["side"] in side_filter
        and s["score"] >= min_score
    ]

    st.subheader(f"📡 {len(filtered_signals)} Filtered Signals")

    if filtered_signals:
        dashboard.display_signals_table(filtered_signals)

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📤 Export to Discord"):
                for s in filtered_signals[:5]:
                    trading_engine.post_signal_to_discord(s)
                st.success("Posted top 5 to Discord!")

        with col2:
            if st.button("📤 Export to Telegram"):
                for s in filtered_signals[:5]:
                    trading_engine.post_signal_to_telegram(s)
                st.success("Posted top 5 to Telegram!")

        with col3:
            if st.button("📄 Export PDF"):
                trading_engine.save_signal_pdf(filtered_signals)
                st.success("PDF exported!")
    else:
        st.info("No signals match the current filters.")
