import streamlit as st
from datetime import datetime, timezone
from db import Signal

class DashboardComponents:
    def __init__(self, trading_engine, db_manager):
        self.trading_engine = trading_engine
        self.db_manager = db_manager

    def render(self):
        st.image("logo.png", width=80)
        st.title("🚀 AlgoTrader Dashboard")

        # === Load wallet data ===
        capital_data = self.trading_engine.load_capital("all") or {}
        real = capital_data.get("real", {})
        virtual = capital_data.get("virtual", {})

        real_total = float(real.get("capital", 0.0))
        real_available = float(real.get("available", 0.0))
        virtual_total = float(virtual.get("capital", 0.0))
        virtual_available = float(virtual.get("available", 0.0))

        # === Load recent trades ===
        all_trades = self.trading_engine.get_recent_trades(limit=100) or []
        real_trades = [t for t in all_trades if not t.get("virtual")]
        virtual_trades = [t for t in all_trades if t.get("virtual")]

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # === Load recent signals ===
        try:
            with self.db_manager.get_session() as session:
                signal_objs = session.query(Signal).order_by(Signal.created_at.desc()).limit(100).all()
                signal_dicts = [s.to_dict() for s in signal_objs]
        except Exception as e:
            st.error(f"Error loading signals: {e}")
            signal_dicts = []

        # === Create main tabs ===
        tab_overview, tab_signals, tab_wallet, tab_trades = st.tabs([
            "📈 Overview",
            "📡 Latest Signals",
            "💰 Wallet",
            "🔍 Trade Summary"
        ])

        # --- Overview tab ---
        with tab_overview:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("💰 Real Wallet", f"${real_available:,.2f}", f"Total: ${real_total:,.2f}")
            col2.metric("🧪 Virtual Wallet", f"${virtual_available:,.2f}", f"Total: ${virtual_total:,.2f}")
            col3.metric("📡 Active Signals", len(signal_dicts))
            col4.metric("📅 Real Trades Today", len([t for t in real_trades if str(t.get("timestamp", "")).startswith(today_str)]))

        # --- Signals tab ---
        with tab_signals:
            self.render_signals_tab(signal_dicts)

        # --- Wallet tab (simplified) ---
        with tab_wallet:
            st.write("Wallet details and balances here...")

        # --- Trades tab ---
        with tab_trades:
            trades_tab1, trades_tab2 = st.tabs(["📈 Real Trades", "🧪 Virtual Trades"])
            with trades_tab1:
                if real_trades:
                    self.display_trades_table(real_trades)
                else:
                    st.info("No real trades available.")

            with trades_tab2:
                if virtual_trades:
                    self.display_trades_table(virtual_trades)
                else:
                    st.info("No virtual trades available.")

    def render_signals_tab(self, signal_dicts):
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
                        new_signals = self.trading_engine.run_once()
                        st.success(f"Generated {len(new_signals)} signals")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error generating signals: {e}")

        # Filter signals by confidence
        filtered_signals = [s for s in signal_dicts if s.get('score', 0) >= confidence_threshold]

        st.subheader("🧠 Recent AI Signals")

        # Display signals in tabs
        tab1, tab2 = st.tabs(["📋 Signal Cards", "📊 Signal Table"])

        with tab1:
            if filtered_signals:
                for i, signal in enumerate(filtered_signals[:10]):  # Show top 10
                    with st.expander(
                        f"{signal.get('symbol', 'N/A')} - {signal.get('signal_type', 'N/A')} ({signal.get('score', 0):.1f}%)",
                        expanded=(i == 0)
                    ):
                        self.display_signal_card(signal)
            else:
                st.info("No signals to display.")

        with tab2:
            if filtered_signals:
                self.display_signals_table(filtered_signals)
            else:
                st.info("No signals to display in table.")

        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            strategies = sorted({s.get("strategy", "") for s in filtered_signals if "strategy" in s})
            strategy_filter = st.multiselect("Filter by Strategy", options=strategies, default=strategies)

        with col2:
            side_filter = st.multiselect("Filter by Side", ["LONG", "SHORT"], default=["LONG", "SHORT"])

        with col3:
            min_score = st.slider("Minimum Score", 40, 100, 50)

        # Apply filters
        filtered_signals_final = [
            s for s in filtered_signals
            if s.get("strategy", "") in strategy_filter
            and s.get("side", "") in side_filter
            and s.get("score", 0) >= min_score
        ]

        st.subheader(f"📡 {len(filtered_signals_final)} Filtered Signals")

        if filtered_signals_final:
            self.display_signals_table(filtered_signals_final)

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("📤 Export to Discord"):
                    for s in filtered_signals_final[:5]:
                        self.trading_engine.post_signal_to_discord(s)
                    st.success("Posted top 5 to Discord!")

            with col2:
                if st.button("📤 Export to Telegram"):
                    for s in filtered_signals_final[:5]:
                        self.trading_engine.post_signal_to_telegram(s)
                    st.success("Posted top 5 to Telegram!")

            with col3:
                if st.button("📄 Export PDF"):
                    self.trading_engine.save_signal_pdf(filtered_signals_final)
                    st.success("PDF exported!")
        else:
            st.info("No signals match the current filters.")

    def display_signal_card(self, signal):
        st.json(signal)  # or customize display here

    def display_signals_table(self, signals):
        import pandas as pd
        df = pd.DataFrame(signals)
        st.dataframe(df)

    def display_trades_table(self, trades):
        import pandas as pd
        df = pd.DataFrame(trades)
        st.dataframe(df)
