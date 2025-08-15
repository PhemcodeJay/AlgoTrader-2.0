import streamlit as st
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import db_manager, Signal


def render(trading_engine, dashboard, db_manager):
    st.title("📊 AI Trading Signals")

    # Scan Options
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol_limit = st.number_input("Symbols to Analyze", min_value=10, max_value=100, value=30)
    with col2:
        confidence_threshold = st.slider("Min Confidence %", 50, 95, 75)
    with col3:
        if st.button("🔍 Scan New Signals"):
            with st.spinner("Analyzing markets..."):
                new_signals = trading_engine.run_once()
                st.success(f"Generated {len(new_signals)} signals")
                st.rerun()

    # Load signals from DB
    with db_manager.get_session() as session:
        signal_objs = session.query(Signal) \
                             .order_by(Signal.created_at.desc()) \
                             .limit(100).all()

    signal_dicts = [s.to_dict() if hasattr(s, 'to_dict') else {
        "symbol": s.symbol,
        "side": s.side,
        "score": s.score,
        "strategy": s.strategy,
        "entry": s.entry,
        "tp": s.tp,
        "sl": s.sl,
        "interval": s.interval,
        "created_at": s.created_at.strftime('%Y-%m-%d %H:%M:%S'),
    } for s in signal_objs]

    if not signal_dicts:
        st.info("No signals available. Scan to generate signals.")
        return

    st.subheader("🧠 Recent AI Signals")
    st.dataframe(signal_dicts)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        strategy_filter = st.multiselect(
            "Filter by Strategy",
            options=sorted({s["strategy"] for s in signal_dicts}),
            default=sorted({s["strategy"] for s in signal_dicts})
        )
    with col2:
        side_filter = st.multiselect("Filter by Side", ["LONG", "SHORT"], default=["LONG", "SHORT"])
    with col3:
        min_score = st.slider("Minimum Score", 70, 100, 80)

    filtered_signals = [
        s for s in signal_dicts
        if s["strategy"] in strategy_filter
        and s["side"] in side_filter
        and s["score"] >= min_score
    ]

    st.subheader(f"📡 {len(filtered_signals)} Active Signals")

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
