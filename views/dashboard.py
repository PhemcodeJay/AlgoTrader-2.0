import streamlit as st
from datetime import datetime, timezone
from db import Signal
from utils import format_currency

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
        with self.db_manager.get_session() as session:
            signal_objs = session.query(Signal).order_by(Signal.created_at.desc()).limit(5).all()
            recent_signals = [s.to_dict() for s in signal_objs]

        # === Create main tabs ===
        tab_overview, tab_signals, tab_wallet, tab_trades = st.tabs([
            "📈 Overview",
            "📡 Latest Signals",
            "💰 Wallet Chart",
            "🔍 Trade Summary"
        ])

        # --- Overview tab ---
        with tab_overview:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("💰 Real Wallet", format_currency(real_available), f"Total: {format_currency(real_total)}")
            col2.metric("🧪 Virtual Wallet", format_currency(virtual_available), f"Total: {format_currency(virtual_total)}")
            col3.metric("📡 Active Signals", len(recent_signals), "Recent")
            col4.metric("📅 Real Trades Today", len([
                t for t in real_trades if str(t.get("timestamp", "")).startswith(today_str)
            ]))

        # --- Signals tab ---
        with tab_signals:
            if recent_signals:
                for i, signal in enumerate(recent_signals):
                    symbol = signal.get("symbol", "N/A")
                    signal_type = signal.get("signal_type", "N/A")
                    score = round(float(signal.get("score") or 0.0), 1)
                    with st.expander(f"{symbol} - {signal_type} ({score}%)", expanded=(i == 0)):
                        self.display_signal_card(signal)
            else:
                st.info("No recent signals available.")

        # --- Wallet Chart tab ---
        with tab_wallet:
            if real_trades:
                fig = self.create_portfolio_performance_chart(real_trades, real_total)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No real trade history available.")

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

    # === Helper methods ===
    def display_signal_card(self, signal):
        st.write(signal)  # Placeholder - your styling here

    def create_portfolio_performance_chart(self, trades, total_capital):
        st.write("Portfolio chart placeholder")  # Replace with plotly logic
        return None

    def display_trades_table(self, trades):
        st.dataframe(trades)
