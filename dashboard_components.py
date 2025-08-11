import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone
from utils import format_currency, get_trend_color, calculate_indicators
from db import db_manager
from typing import cast, List, Dict, Any


class DashboardComponents:
    def __init__(self, engine):
        self.engine = engine

    def render(self):
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
        real_mode = st.checkbox(
            "✅ Enable Real Bybit Trading",
            value=os.getenv("USE_REAL_TRADING", "false").lower() == "true"
        )
        os.environ["USE_REAL_TRADING"] = str(real_mode).lower()
        db_manager.set_setting("real_trading", str(real_mode).lower())
        return real_mode

    def display_signal_card(self, signal):
        col1, col2 = st.columns([2, 1])

        try:
            entry = round(float(signal.get('entry_price') or signal.get('entry') or 0), 4)
        except (TypeError, ValueError):
            entry = 0.0

        try:
            tp = round(float(signal.get('tp_price') or signal.get('tp') or 0), 4)
        except (TypeError, ValueError):
            tp = 0.0

        try:
            sl = round(float(signal.get('sl_price') or signal.get('sl') or 0), 4)
        except (TypeError, ValueError):
            sl = 0.0

        leverage = signal.get('leverage', 20)
        margin_usdt = signal.get('margin_usdt')
        try:
            confidence = round(float(signal.get('score', 0)), 1)
        except (TypeError, ValueError):
            confidence = 0.0
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
            confidence_color = "green" if confidence >= 75 else "orange" if confidence >= 60 else "red"
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

        df = pd.DataFrame([{
            'Symbol': s.get('symbol', 'N/A'),
            'Side': s.get('side', 'N/A'),
            'Strategy': s.get('strategy', 'N/A'),
            'Entry': f"${safe_get(s, 'entry_price'):.2f}",
            'TP': f"${safe_get(s, 'tp_price'):.2f}",
            'SL': f"${safe_get(s, 'sl_price'):.2f}",
            'Confidence': f"{s.get('score', 0)}%",
            'Leverage': f"{s.get('leverage', 20)}x",
            'Qty': f"{s.get('qty', 0):,.2f}",
            'Margin (USDT)': f"${s.get('margin_usdt', 5):.2f}",
            'Trend': s.get('trend', 'N/A'),
            'Timestamp': s.get('timestamp', 'N/A')
        } for s in signals])
        st.dataframe(df, use_container_width=True, height=400)

    def display_trade_filters(self):
        st.sidebar.header("Trade Filters")
        trade_mode = st.sidebar.selectbox("Trade Mode", ["All", "Real", "Virtual"])
        trade_status = st.sidebar.selectbox("Trade Status", ["All", "Open", "Closed"])
        return trade_status, trade_mode

    def get_filtered_trades(self, trade_status, trade_mode):
        if trade_status == "Open" and trade_mode == "Real":
            return self.engine.get_open_real_trades()
        elif trade_status == "Open" and trade_mode == "Virtual":
            return self.engine.get_open_virtual_trades()
        elif trade_status == "Closed" and trade_mode == "Real":
            return self.engine.get_closed_real_trades()
        elif trade_status == "Closed" and trade_mode == "Virtual":
            return self.engine.get_closed_virtual_trades()
        elif trade_status == "Open":
            return self.engine.get_open_real_trades() + self.engine.get_open_virtual_trades()
        elif trade_status == "Closed":
            return self.engine.get_closed_real_trades() + self.engine.get_closed_virtual_trades()
        else:
            return (
                self.engine.get_open_real_trades()
                + self.engine.get_open_virtual_trades()
                + self.engine.get_closed_real_trades()
                + self.engine.get_closed_virtual_trades()
            )

    def display_trades_table(self, trades):
        def format_timestamp(ts):
            if not ts:
                return "N/A"
            try:
                if isinstance(ts, str):
                    return ts
                return ts.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return str(ts)

        df = pd.DataFrame([
            {
                'Symbol': t.get('symbol', 'N/A'),
                'Side': t.get('side', 'N/A'),
                'Entry': f"${t.get('entry_price', 0):.2f}" if t.get('entry_price') is not None else "N/A",
                'Exit': f"${t.get('exit_price', 0):.2f}" if t.get('exit_price') is not None else "N/A",
                'Qty': f"{t.get('qty', 0):,.2f}" if t.get('qty') is not None else "N/A",
                'Leverage': f"{t.get('leverage', 'N/A')}x" if t.get('leverage') is not None else "N/A",
                'Margin (USDT)': f"${t.get('margin_usdt', 0):.2f}" if t.get('margin_usdt') is not None else "N/A",
                'P&L': (
                    f"{'🟢' if t.get('pnl', 0) > 0 else '🔴'} ${t.get('pnl', 0):.2f}"
                    if t.get('pnl') is not None else "N/A"
                ),
                'Status': t.get('status', 'N/A'),
                'Strategy': t.get('strategy', 'N/A'),
                'Virtual': '✅' if t.get('virtual', False) else '❌',
                'Timestamp': format_timestamp(t.get('timestamp'))
            }
            for t in trades
        ])

        st.dataframe(df, use_container_width=True, height=400)

    def calculate_duration(self, trade):
        try:
            if getattr(trade, 'exit_price', None) is not None:
                delta = datetime.now(timezone.utc) - getattr(trade, 'timestamp', datetime.now(timezone.utc))
                return str(delta).split('.')[0]  # 'HH:MM:SS'
        except Exception:
            pass
        return "Active"

    def display_empty_state(self, message: str):
        st.info(message)

    def display_trade_statistics(self, stats):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Trades", stats.get('total_trades', 0))
            st.metric("Total P&L", f"${format_currency(stats.get('total_pnl', 0))}")
        with col2:
            st.metric("Win Rate", f"{stats.get('win_rate', 0)}%")
            st.metric("Profit Factor", stats.get('profit_factor', 0))
        with col3:
            st.metric("Avg Win", f"${format_currency(stats.get('avg_win', 0))}")
            st.metric("Avg Loss", f"${format_currency(stats.get('avg_loss', 0))}")

    def create_portfolio_performance_chart(self, trades, start_balance=10.0):
        if not trades:
            return go.Figure()

        pnl_data, dates = [], []
        cumulative = float(start_balance)

        for t in trades:
            pnl = float(getattr(t, 'pnl', 0) or 0)
            cumulative += pnl
            pnl_data.append(cumulative)

            try:
                timestamp = getattr(t, 'timestamp', None)
                if isinstance(timestamp, str):
                    dt = datetime.fromisoformat(timestamp)
                elif isinstance(timestamp, datetime):
                    dt = timestamp
                else:
                    raise ValueError("Invalid timestamp type")
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)

            dates.append(dt)

        fig = go.Figure(go.Scatter(
            x=dates, y=pnl_data, mode='lines+markers',
            line=dict(color='#00d4aa', width=2)
        ))
        fig.update_layout(
            title="Portfolio Performance",
            height=400,
            xaxis_title="Time",
            yaxis_title="Portfolio ($)",
            template="plotly_dark"
        )
        return fig

    def create_detailed_performance_chart(self, trades, start_balance=10.0):
        if not trades:
            return go.Figure()

        cumulative, daily_pnl, dates = [], [], []
        running_total = start_balance

        for t in trades:
            pnl = float(getattr(t, 'pnl', 0) or 0)
            running_total += pnl
            cumulative.append(running_total)
            daily_pnl.append(pnl)
            try:
                dt = datetime.fromisoformat(t['timestamp'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dates.append(dt)
            except Exception:
                dates.append(datetime.now(timezone.utc))

        fig = make_subplots(
            rows=2, cols=1, row_heights=[0.7, 0.3], vertical_spacing=0.05,
            subplot_titles=['Cumulative P&L', 'Daily P&L']
        )

        fig.add_trace(go.Scatter(x=dates, y=cumulative, mode='lines+markers', name='Equity',
                                 line=dict(color='lime')), row=1, col=1)
        fig.add_trace(go.Bar(x=dates, y=daily_pnl, name='Daily P&L',
                             marker_color=['green' if x > 0 else 'red' for x in daily_pnl]), row=2, col=1)

        fig.update_layout(template='plotly_dark', height=600, showlegend=False)
        return fig

    def create_technical_chart(self, chart_data: List[Dict[str, Any]], symbol: str, indicators: List[str]) -> go.Figure:
        if not chart_data:
            return go.Figure()

        df = pd.DataFrame(chart_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = calculate_indicators(cast(List[Dict[str, Any]], df.to_dict(orient='records')))

        has_rsi = "RSI" in indicators and "RSI" in df.columns
        has_macd = "MACD" in indicators and "MACD_line" in df.columns
        has_stoch = "Stoch RSI" in indicators and "Stoch_K" in df.columns

        rows = 2 + sum([has_rsi, has_macd, has_stoch])
        subplot_titles = [f'{symbol} Price', 'Volume']
        if has_rsi: subplot_titles.append("RSI")
        if has_macd: subplot_titles.append("MACD")
        if has_stoch: subplot_titles.append("Stoch RSI")

        fig = make_subplots(
            rows=rows,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.5] + [0.12] * (rows - 1),
            subplot_titles=subplot_titles
        )

        row_idx = 1

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="Candles",
            increasing_line_color='lime',
            decreasing_line_color='red'
        ), row=row_idx, col=1)

        # Overlay indicators
        if "EMA 9" in indicators and "EMA_9" in df.columns:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['EMA_9'], name="EMA 9", line=dict(color='cyan')), row=row_idx, col=1)
        if "EMA 21" in indicators and "EMA_21" in df.columns:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['EMA_21'], name="EMA 21", line=dict(color='orange')), row=row_idx, col=1)
        if "MA 50" in indicators and "MA_50" in df.columns:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MA_50'], name="MA 50", line=dict(color='blue')), row=row_idx, col=1)
        if "MA 200" in indicators and "MA_200" in df.columns:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MA_200'], name="MA 200", line=dict(color='white')), row=row_idx, col=1)

        if "Bollinger Bands" in indicators and "BB_upper" in df.columns:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['BB_upper'], name="BB Upper", line=dict(color='gray', dash='dot')), row=row_idx, col=1)
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['BB_lower'], name="BB Lower", line=dict(color='gray', dash='dot')), row=row_idx, col=1)

        # Volume
        row_idx += 1
        bar_colors = ['green' if c >= o else 'red' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df['timestamp'], y=df['volume'], name="Volume", marker_color=bar_colors), row=row_idx, col=1)

        # RSI
        if has_rsi:
            row_idx += 1
            fig.add_trace(go.Scatter(
                x=df['timestamp'], y=df['RSI'],
                name="RSI", line=dict(color='purple')
            ), row=row_idx, col=1)

            fig.add_shape(
                type="line",
                x0=df['timestamp'].min(), x1=df['timestamp'].max(),
                y0=70, y1=70,
                line=dict(color="red", dash="dash"),
                xref=f'x{row_idx}' if row_idx > 1 else 'x',
                yref=f'y{row_idx}' if row_idx > 1 else 'y'
            )
            fig.add_shape(
                type="line",
                x0=df['timestamp'].min(), x1=df['timestamp'].max(),
                y0=30, y1=30,
                line=dict(color="green", dash="dash"),
                xref=f'x{row_idx}' if row_idx > 1 else 'x',
                yref=f'y{row_idx}' if row_idx > 1 else 'y'
            )

        # MACD
        if has_macd:
            row_idx += 1
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MACD_line'], name="MACD Line", line=dict(color='cyan')), row=row_idx, col=1)
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MACD_signal'], name="Signal", line=dict(color='orange', dash='dot')), row=row_idx, col=1)
            fig.add_trace(go.Bar(x=df['timestamp'], y=df['MACD_hist'], name="Histogram", marker_color='lightgray'), row=row_idx, col=1)

        # Stoch RSI
        if has_stoch:
            row_idx += 1
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Stoch_K'], name="Stoch %K", line=dict(color='magenta')), row=row_idx, col=1)
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Stoch_D'], name="Stoch %D", line=dict(color='yellow')), row=row_idx, col=1)

        fig.update_layout(
            template='plotly_dark',
            height=300 + rows * 200,
            margin=dict(l=30, r=30, t=50, b=30),
            showlegend=True,
            xaxis_rangeslider_visible=False,
            xaxis=dict(type='date')
        )

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
        ticker_html = " | ".join([
            f"<span style='color:{'green' if item['change'] > 0 else 'red'}; font-weight:bold'>{item['symbol']}: {item['price']:.2f} ({item['change']:+.2f}%)</span>"
            for item in top_20
        ])

        st.markdown(f"""
            <marquee behavior="scroll" direction="left" scrollamount="6" style="color: white; background-color: #111; padding: 5px; border-radius: 8px;">
                {ticker_html}
            </marquee>
        """, unsafe_allow_html=True)

    