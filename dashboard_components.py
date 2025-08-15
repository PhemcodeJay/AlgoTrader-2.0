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
    def __init__(self):
        pass

    def display_signal_card(self, signal):
        col1, col2 = st.columns([2, 1])
        
        entry = signal.get('entry_price') or signal.get('entry') or 0
        tp = signal.get('tp_price') or signal.get('tp') or 0
        sl = signal.get('sl_price') or signal.get('sl') or 0
        leverage = signal.get('leverage', 20)
        margin_usdt = signal.get('margin_usdt')
        confidence = round(float(signal.get('score', 0)), 1)
        strategy = signal.get('strategy') or "N/A"
        symbol = signal.get('symbol', 'N/A')
        side = signal.get('side', 'N/A')

        # Format margin safely
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
            return val

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
            'Margin USDT': f"${s.get('margin_usdt', 0):.2f}",
            'Trend': s.get('trend', 'N/A'),
            'Timestamp': s.get('timestamp', 'N/A')
        } for s in signals])
        st.dataframe(df, use_container_width=True, height=400)

    def display_trades_table(self, trades):
        df = pd.DataFrame([{
            'Symbol': t.get('symbol'),
            'Side': t.get('side'),
            'Entry': f"${t.get('entry', 0):.2f}",
            'Exit': f"${t.get('exit', 0):.2f}",
            'Qty': f"{t.get('qty', 0):,.2f}",
            'Leverage': f"{t.get('leverage', 20)}x",
            'Margin USDT': f"${t.get('margin_usdt', 0):.2f}",
            'P&L': f"{'🟢' if float(t.get('pnl') or 0) > 0 else '🔴'} ${float(t.get('pnl') or 0):.2f}",
            'Duration': t.get('duration', 'N/A'),
            'Strategy': t.get('strategy', 'N/A'),
            'Timestamp': t.get('timestamp')
        } for t in trades])
        st.dataframe(df, use_container_width=True, height=400)

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

        pnl_data, dates = []
        cumulative = float(start_balance)

        for t in trades:
            raw_pnl = t.get('pnl', 0)

            try:
                pnl = float(raw_pnl) if not isinstance(raw_pnl, dict) else 0.0
            except (ValueError, TypeError):
                pnl = 0.0

            cumulative += pnl
            pnl_data.append(cumulative)

            try:
                dt = datetime.fromisoformat(t.get('timestamp', ''))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)

            dates.append(dt)

        fig = go.Figure(go.Scatter(
            x=dates,
            y=pnl_data,
            mode='lines+markers',
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
            pnl = float(t.get('pnl') or 0)
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

        fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3], vertical_spacing=0.05,
                            subplot_titles=['Cumulative P&L', 'Daily P&L'])

        fig.add_trace(go.Scatter(x=dates, y=cumulative, mode='lines+markers', name='Equity',
                                 line=dict(color='lime')), row=1, col=1)
        fig.add_trace(go.Bar(x=dates, y=daily_pnl, name='Daily P&L',
                             marker_color=['green' if x > 0 else 'red' for x in daily_pnl]), row=2, col=1)

        fig.update_layout(template='plotly_dark', height=600, showlegend=False)
        return fig

    def create_technical_chart(self, chart_data, symbol, indicators):
        if not chart_data:
            return go.Figure()

        df = pd.DataFrame(chart_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 👇 Recalculate all indicators at once
        df = calculate_indicators(cast(List[Dict[str, Any]], df.to_dict(orient='records')))

        close = df['close'].tolist()
        open_ = df['open'].tolist()

        fig = make_subplots(rows=3, cols=1, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03,
                            subplot_titles=(f'{symbol} Price Chart', 'Volume', 'RSI'))

        fig.add_trace(go.Candlestick(
            x=df['timestamp'], open=df['open'], high=df['high'],
            low=df['low'], close=df['close'], name="Candles"), row=1, col=1)

        if 'EMA 9' in indicators and 'EMA_21' in df:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['EMA_21'], name="EMA 21", line=dict(color='orange')), row=1, col=1)

        if 'EMA 21' in indicators and 'EMA_50' in df:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['EMA_50'], name="EMA 50", line=dict(color='blue')), row=1, col=1)

        if 'Bollinger Bands' in indicators and 'BB_upper' in df:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['BB_upper'], name="BB Upper", line=dict(color='gray', dash='dot')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['BB_lower'], name="BB Lower", line=dict(color='gray', dash='dot')), row=1, col=1)

        bar_colors = ['green' if c > o else 'red' for c, o in zip(df['close'], df['open'])]
        fig.add_trace(go.Bar(x=df['timestamp'], y=df['volume'], marker_color=bar_colors), row=2, col=1)

        if 'RSI' in indicators and 'RSI' in df:
            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['RSI'], name='RSI', line=dict(color='purple')), row=3, col=1)

        fig.update_layout(template='plotly_dark', height=700)
        return fig


    def render_ticker(self, ticker_data, position='top'):
        if not ticker_data:
            return

        def format_volume(val):
            if val >= 1_000_000_000:
                return f"{val / 1_000_000_000:.1f}B"
            elif val >= 1_000_000:
                return f"{val / 1_000_000:.1f}M"
            elif val >= 1_000:
                return f"{val / 1_000:.1f}K"
            else:
                return f"{val:.2f}"

        cleaned = []
        for item in ticker_data:
            try:
                symbol = item.get('symbol')
                price = float(item.get('lastPrice', 0))
                change = float(item.get('price24hPcnt', 0)) * 100
                volume = float(item.get('turnover24h') or item.get('volume24h') or 0)
                cleaned.append({'symbol': symbol, 'price': price, 'change': change, 'volume': volume})
            except:
                continue

        top_50 = sorted(cleaned, key=lambda x: x['volume'], reverse=True)[:50]
        ticker_html = " | ".join([
            f"<b>{x['symbol']}</b>: ${x['price']:.6f} "
            f"(<span style='color:{'#00cc66' if x['change'] > 0 else '#ff4d4d'}'>{x['change']:.2f}%</span>) "
            f"Vol: {format_volume(x['volume'])}"
            for x in top_50
        ])

        if ticker_html:
            st.markdown(f"""
                <div style='position: fixed; {position}: 0; left: 0; width: 100%; background-color: #111; 
                color: white; padding: 10px; font-family: monospace; font-size: 16px; 
                white-space: nowrap; overflow: hidden; z-index: 9999;' >
                    <marquee>{ticker_html}</marquee>
                </div>
            """, unsafe_allow_html=True)

    def render_real_mode_toggle(self):
        real_mode = st.checkbox("✅ Enable Real Bybit Trading", value=os.getenv("USE_REAL_TRADING", "false") == "true")
        os.environ["USE_REAL_TRADING"] = str(real_mode).lower()
        db_manager.set_setting("real_trading", str(real_mode).lower())
        return real_mode
