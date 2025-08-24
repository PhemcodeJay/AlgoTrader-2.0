# dashboard_components.py (fixed version)
# Fixes: Completed truncated sections.
# Fixed display_signals_table to use pd.DataFrame safely.
# Fixed create_portfolio_performance_chart and create_detailed_performance_chart to handle data.
# Added safe_float.
# Fixed render_ticker to handle empty.

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone
from utils import format_currency, get_trend_color, calculate_indicators
from db import db_manager
from typing import cast, List, Dict, Any

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class DashboardComponents:
    def __init__(self, engine):
        self.engine = engine
        self._trade_cache = {}

    def render(self, *args, **kwargs):

        st.title("AlgoTrader Dashboard")

        # 1. Real Mode Toggle
        real_mode = self.render_real_mode_toggle()

        # 2. Display Ticker at top if available
        ticker_data = []
        if hasattr(self.engine, "get_ticker_data"):
            ticker_data = self.engine.get_ticker_data()
        self.render_ticker(ticker_data, position='top')

        # 3. Show Signals Section
        signals = []
        if hasattr(self.engine, "get_signals"):
            signals = self.engine.get_signals()

        st.header("Trading Signals")
        if signals:
            for signal in signals:
                self.display_signal_card(signal)
            self.display_signals_table(signals)
        else:
            self.display_empty_state("No trading signals available.")

        # 4. Trade Filters in sidebar & fetch filtered trades
        trade_status, trade_mode = self.display_trade_filters()
        trades = self.get_filtered_trades(trade_status, trade_mode)

        # 5. Display Trades Section
        st.header("Trades")
        if trades:
            self.display_trades_table(trades)

            # 6. Show trade statistics if available
            stats = {}
            if hasattr(self.engine, "get_trade_statistics"):
                stats = self.engine.get_trade_statistics()
            if stats:
                self.display_trade_statistics(stats)

            # 7. Portfolio performance chart
            fig_perf = self.create_portfolio_performance_chart(trades)
            st.plotly_chart(fig_perf, use_container_width=True)

            # 8. Detailed performance chart
            fig_detail = self.create_detailed_performance_chart(trades)
            st.plotly_chart(fig_detail, use_container_width=True)

        else:
            self.display_empty_state("No trades found for the selected filters.")

    def render_real_mode_toggle(self):
        current_mode = os.getenv("USE_REAL_TRADING", "false").lower() == "true"
        real_mode = st.checkbox("✅ Enable Real Bybit Trading", value=current_mode)

        # Only update if value changed
        if real_mode != current_mode:
            os.environ["USE_REAL_TRADING"] = str(real_mode).lower()
            db_manager.update_setting("real_trading", str(real_mode).lower())
            st.warning("Mode change requires app restart for full effect.")

        return real_mode

    def display_signal_card(self, signal):
        col1, col2 = st.columns([2, 1])

        def safe_float(value, default=0.0):
            try:
                return round(float(value or default), 4)
            except (TypeError, ValueError):
                return default

        entry = safe_float(signal.get('entry_price') or signal.get('entry'))
        tp = safe_float(signal.get('tp_price') or signal.get('tp'))
        sl = safe_float(signal.get('sl_price') or signal.get('sl'))
        leverage = signal.get('leverage', 20)
        margin_usdt = signal.get('margin_usdt')
        confidence = safe_float(signal.get('score', 0), 0)
        strategy = signal.get('strategy') or "N/A"
        symbol = signal.get('symbol', 'N/A')
        side = signal.get('side', 'N/A')

        try:
            margin_display = f"${float(margin_usdt):.2f}"
        except (TypeError, ValueError):
            margin_display = "N/A"

        with col1:
            st.markdown(f"**{symbol}** - {side}")
            st.markdown(f"Strategy: {strategy}")
            st.markdown(f"Entry: ${entry:.2f} | TP: ${tp:.2f} | SL: ${sl:.2f}")
            st.markdown(f"Leverage: {leverage}x | Margin: {margin_display}")

        with col2:
            confidence_color = (
                "green" if confidence >= 75 else
                "orange" if confidence >= 60 else
                "red"
            )
            st.markdown(f"""
                <div style='background-color: {confidence_color}; color: white; padding: 6px; 
                border-radius: 6px; text-align: center; font-weight: bold'>
                {confidence}% Confidence</div>
            """, unsafe_allow_html=True)

    def display_signals_table(self, signals):
        def safe_get(signal, key, default=0.0):
            val = signal.get(key)
            if val is None:
                val = signal.get(key.replace('_price', ''), default)
            return val or default

        df_data = []
        for s in signals:
            df_data.append({
                'Symbol': s.get('symbol', 'N/A'),
                'Side': s.get('side', 'N/A'),
                'Strategy': s.get('strategy', 'N/A'),
                'Entry': safe_get(s, 'entry_price'),
                'TP': safe_get(s, 'tp_price'),
                'SL': safe_get(s, 'sl_price'),
                'Score': safe_get(s, 'score'),
                'Leverage': s.get('leverage', 20),
                'Margin': safe_get(s, 'margin_usdt')
            })
        df = pd.DataFrame(df_data)
        st.table(df)

    def display_empty_state(self, message):
        st.info(message)

    def display_trade_filters(self):
        with st.sidebar:
            trade_status = st.selectbox("Trade Status", ["All", "Open", "Closed"])
            trade_mode = st.selectbox("Trade Mode", ["All", "Virtual", "Real"])
        return trade_status, trade_mode

    def get_filtered_trades(self, status, mode):
        virtual = None if mode == "All" else (mode == "Virtual")
        trades = self.engine.get_open_trades(virtual=virtual) if status == "Open" else self.engine.get_closed_trades(virtual=virtual) if status == "Closed" else self.engine.get_trades(virtual=virtual)
        return trades

    def display_trades_table(self, trades):
        formatted = format_trades(trades)
        df = pd.DataFrame(formatted)
        st.table(df)

    def display_trade_statistics(self, stats):
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Trades", stats["total_trades"])
        col2.metric("Win Rate", f"{stats['win_rate']}%")
        col3.metric("Total PnL", format_currency(stats["total_pnl"]))

    def create_portfolio_performance_chart(self, trades):
        df = pd.DataFrame([{"time": t["timestamp"], "pnl": t["pnl"]} for t in trades])
        df = df.sort_values("time")
        df["cum_pnl"] = df["pnl"].cumsum()
        fig = go.Figure(go.Scatter(x=df["time"], y=df["cum_pnl"], mode="lines"))
        fig.update_layout(title="Portfolio Performance", template="plotly_dark")
        return fig

    def create_detailed_performance_chart(self, trades):
        fig = make_subplots(rows=1, cols=1)
        for t in trades:
            fig.add_trace(go.Bar(x=[t["timestamp"]], y=[t["pnl"]], name=t["symbol"]))
        fig.update_layout(title="Trade PnL", template="plotly_dark")
        return fig

    def render_ticker(self, ticker_data, position='top'):
        if not ticker_data:
            return

        def format_volume(val):
            if val >= 1_000_000_000:
                return f"${val / 1_000_000_000:.1f}B"
            elif val >= 1_000_000:
                return f"${val / 1_000_000:.1f}M"
            elif val >= 1_000:
                return f"${val / 1_000:.1f}K"
            else:
                return f"${val:.2f}"

        cleaned = []
        for item in ticker_data:
            try:
                symbol = item.get('symbol', 'N/A')
                price = float(item.get('lastPrice') or 0)
                change = float(item.get('price24hPcnt') or 0) * 100
                volume = float(item.get("turnover24h") or item.get("volume24h") or 0)
                cleaned.append({'symbol': symbol, 'price': price, 'change': change, 'volume': volume})
            except (ValueError, TypeError):
                continue

        top_20 = sorted(cleaned, key=lambda x: x['volume'], reverse=True)[:20]
        # Force BTC, ETH, BNB to appear first in order
        priority = ['BTC', 'ETH', 'BNB', 'SOL', 'DOGE']
        top_20 = sorted(top_20, key=lambda x: (x['symbol'] not in priority, priority.index(x['symbol']) if x['symbol'] in priority else 99))
        ticker_html = " | ".join([
            f"<b>{x['symbol']}</b>: ${x['price']:.6f} "
            f"(<span style='color:{'#00cc66' if x['change'] > 0 else '#ff4d4d'}'>{x['change']:.2f}%</span>) "
            f"Vol: {format_volume(x['volume'])}"
            for x in top_20
        ])

        if ticker_html:
            st.markdown(f"""
                <div style='position: fixed; {position}: 0; left: 0; width: 100%; background-color: #111; 
                color: white; padding: 10px; font-family: monospace; font-size: 16px; 
                white-space: nowrap; overflow: hidden; z-index: 9999;' >
                    <marquee>{ticker_html}</marquee>
                </div>
            """, unsafe_allow_html=True)