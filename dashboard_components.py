import os
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
        current_mode = os.getenv("USE_REAL_TRADING", "false").lower() == "true"
        real_mode = st.checkbox("✅ Enable Real Bybit Trading", value=current_mode)

        # Only update if value changed
        if real_mode != current_mode:
            os.environ["USE_REAL_TRADING"] = str(real_mode).lower()
            db_manager.set_setting("real_trading", str(real_mode).lower())

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
            'Entry': safe_get(s, 'entry_price'),
            'TP': safe_get(s, 'tp_price'),
            'SL': safe_get(s, 'sl_price'),
            'Confidence (%)': s.get('score', 0),
            'Leverage': s.get('leverage', 20),
            'Qty': s.get('qty', 0),
            'Margin (USDT)': s.get('margin_usdt', 5),
            'Trend': s.get('trend', 'N/A'),
            'Timestamp': s.get('timestamp', 'N/A')
        } for s in signals])

        st.dataframe(
            df.style.format({
                'Entry': "${:.2f}",
                'TP': "${:.2f}",
                'SL': "${:.2f}",
                'Confidence (%)': "{:.1f}%",
                'Qty': "{:,.2f}",
                'Margin (USDT)': "${:.2f}"
            }),
            use_container_width=True,
            height=400
        )

    def display_trade_filters(self):
        st.sidebar.header("Trade Filters")
        trade_mode = st.sidebar.selectbox("Trade Mode", ["All", "Real", "Virtual"])
        trade_status = st.sidebar.selectbox("Trade Status", ["All", "Open", "Closed"])
        return trade_status, trade_mode

    def _fetch_trades(self, key, fetch_func):
        if key not in self._trade_cache:
            self._trade_cache[key] = fetch_func()
        return self._trade_cache[key]

    def get_filtered_trades(self, trade_status, trade_mode):
        # Cache results to avoid repeated DB/API calls
        open_real = self._fetch_trades("open_real", self.engine.get_open_real_trades)
        open_virtual = self._fetch_trades("open_virtual", self.engine.get_open_virtual_trades)
        closed_real = self._fetch_trades("closed_real", self.engine.get_closed_real_trades)
        closed_virtual = self._fetch_trades("closed_virtual", self.engine.get_closed_virtual_trades)

        if trade_status == "Open" and trade_mode == "Real":
            return open_real
        elif trade_status == "Open" and trade_mode == "Virtual":
            return open_virtual
        elif trade_status == "Closed" and trade_mode == "Real":
            return closed_real
        elif trade_status == "Closed" and trade_mode == "Virtual":
            return closed_virtual
        elif trade_status == "Open":
            return open_real + open_virtual
        elif trade_status == "Closed":
            return closed_real + closed_virtual
        else:
            return open_real + open_virtual + closed_real + closed_virtual

    def display_trades_table(self, trades):
        def format_timestamp(ts):
            if not ts:
                return "N/A"
            if isinstance(ts, datetime):
                return ts.strftime('%Y-%m-%d %H:%M:%S')
            return str(ts)

        df = pd.DataFrame([
            {
                'Symbol': getattr(t, 'symbol', 'N/A'),
                'Side': getattr(t, 'side', 'N/A'),
                'Entry': getattr(t, 'entry_price', None),
                'Exit': getattr(t, 'exit_price', None),
                'Qty': getattr(t, 'qty', None),
                'Leverage': getattr(t, 'leverage', None),
                'Margin (USDT)': getattr(t, 'margin_usdt', None),
                'P&L': getattr(t, 'pnl', None),
                'Status': getattr(t, 'status', 'N/A'),
                'Strategy': getattr(t, 'strategy', 'N/A'),
                'Virtual': getattr(t, 'virtual', False),
                'Timestamp': format_timestamp(getattr(t, 'timestamp', None)),
                'Duration': self.calculate_duration(t)
            }
            for t in trades
        ])

        st.dataframe(
            df.style.format({
                'Entry': "${:.2f}",
                'Exit': "${:.2f}",
                'Qty': "{:,.2f}",
                'Margin (USDT)': "${:.2f}",
                'P&L': "${:.2f}"
            }),
            use_container_width=True,
            height=400
        )
        
    def calculate_trade_age(self, trade):
        """Return trade age as string or 'N/A'."""
        try:
            timestamp = trade.get('timestamp', None)

            if not timestamp:
                return "N/A"

            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    return "N/A"

            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                return "N/A"

            delta = datetime.now(timezone.utc) - timestamp
            return str(delta).split('.')[0]
        except Exception:
            return "N/A"

    def display_trade_card(self, trade):
        """Render a single trade as a card with ROI and P&L info."""
        roi = trade.get('roi', 0)
        pnl = trade.get('pnl', 0)
        border_color = "#00C853" if roi >= 0 else "#D50000"

        st.markdown(
            f"""
            <div style="
                border: 2px solid {border_color};
                border-radius: 10px;
                padding: 10px;
                margin-bottom: 10px;
                background-color: #1E1E1E;
            ">
                <h4 style="margin:0; color:white;">{trade.get('symbol', 'N/A')}</h4>
                <p style="margin:0; color:gray;">Side: {trade.get('side', 'N/A')}</p>
                <p style="margin:0; color:gray;">Entry: {trade.get('entry_price', 'N/A')}</p>
                <p style="margin:0; color:gray;">Age: {self.calculate_trade_age(trade)}</p>
                <span style="
                    display:inline-block;
                    padding:4px 8px;
                    background-color:{border_color};
                    color:white;
                    border-radius:5px;
                    font-size:0.85em;
                    margin-right:5px;
                ">{roi:.2f}% ROI</span>
                <span style="
                    display:inline-block;
                    padding:4px 8px;
                    background-color:{border_color};
                    color:white;
                    border-radius:5px;
                    font-size:0.85em;
                ">PNL: {pnl:.2f}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    def calculate_duration(self, trade):
        try:
            timestamp = getattr(trade, 'timestamp', None)

            # Handle None timestamp
            if not timestamp:
                return "N/A"

            # If timestamp is string, parse it
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    return "N/A"

            # Ensure tz-aware datetime
            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                return "N/A"

            # Calculate duration
            delta = datetime.now(timezone.utc) - timestamp
            return str(delta).split('.')[0]

        except Exception:
            return "N/A"


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

            timestamp = getattr(t, 'timestamp', None)
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp)
            elif isinstance(timestamp, datetime):
                dt = timestamp
            else:
                dt = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

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

            timestamp = getattr(t, 'timestamp', None)
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp)
            elif isinstance(timestamp, datetime):
                dt = timestamp
            else:
                dt = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            dates.append(dt)

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
        if 'timestamp' not in df:
            return go.Figure()

        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df.dropna(subset=['timestamp'], inplace=True)
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
            open=df.get('open', []),
            high=df.get('high', []),
            low=df.get('low', []),
            close=df.get('close', []),
            name="Candles",
            increasing_line_color='lime',
            decreasing_line_color='red'
        ), row=row_idx, col=1)

        # EMA / MA
        for name, colname, color in [
            ("EMA 9", "EMA_9", "cyan"),
            ("EMA 21", "EMA_21", "orange"),
            ("MA 50", "MA_50", "blue"),
            ("MA 200", "MA_200", "white")
        ]:
            if name in indicators and colname in df.columns:
                fig.add_trace(go.Scatter(x=df['timestamp'], y=df[colname], name=name, line=dict(color=color)), row=row_idx, col=1)

        # Bollinger Bands
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
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['RSI'], name="RSI", line=dict(color='purple')), row=row_idx, col=1)

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

    def render_ticker(self, ticker_data, position: str = 'top') -> str:
        if not ticker_data:
            return ""

        def format_volume(val: float) -> str:
            if val >= 1_000_000_000:
                return f"${val / 1_000_000_000:.1f}B"
            elif val >= 1_000_000:
                return f"${val / 1_000_000:.1f}M"
            elif val >= 1_000:
                return f"${val / 1_000:.1f}K"
            return f"${val:.8f}" if val < 1 else f"${val:.2f}"

        # Ensure ticker_data is a list
        tickers = ticker_data if isinstance(ticker_data, list) else [ticker_data]

        ticker_html = ""
        for t in tickers:
            if not isinstance(t, dict):
                continue

            # Safely get price and change as floats
            try:
                price = float(t.get('price', 0))
                change = float(t.get('change', 0))
            except (TypeError, ValueError):
                continue  # skip tickers with invalid data

            # Skip zero-price tickers
            if price == 0:
                continue

            symbol = t.get('symbol', '')
            ticker_html += f"""
            <div class="ticker" style="position: {position};">
                <span class="symbol">{symbol}</span>
                <span class="price">{format_volume(price)}</span>
                <span class="change">{change:.2f}%</span>
            </div>
            """

        return ticker_html
