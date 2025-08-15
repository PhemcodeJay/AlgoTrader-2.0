import streamlit as st
from datetime import datetime, timezone

def render(trading_engine, dashboard):
    st.title("💼 Wallet Summary")

    # Load capital info
    balance_info = trading_engine.load_capital()
    capital = balance_info.get("capital", 0.0)
    currency = balance_info.get("currency", "USD")
    start_balance = 100.0  # This could be made dynamic later

    # All trades from DB (virtual + real)
    all_trades = trading_engine.get_recent_trades(limit=100)

    # Filter selector
    selected_mode = st.radio("View Mode", ["All", "Real", "Virtual"], horizontal=True)

    def is_virtual_trade(trade):
        return trade.get("virtual", False)

    if selected_mode == "Real":
        trades = [t for t in all_trades if not is_virtual_trade(t)]
    elif selected_mode == "Virtual":
        trades = [t for t in all_trades if is_virtual_trade(t)]
    else:
        trades = all_trades

    # Total return %
    total_return_pct = ((capital - start_balance) / start_balance) * 100 if start_balance else 0.0

    # Daily P&L
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_pnl = sum(
        float(t.get("pnl", 0.0) or 0.0)
        for t in trades
        if isinstance(t.get("timestamp"), str) and t["timestamp"].startswith(today)
    )

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Balance", f"${capital:.2f}", currency)
    col2.metric("Total Return", f"{total_return_pct:.2f}%")
    col3.metric("Daily P&L", f"${daily_pnl:.2f}")
    col4.metric("Win Rate", f"{trading_engine.calculate_win_rate(trades):.2f}%")

    st.markdown("---")

    # Charts and Stats
    left, right = st.columns([2, 1])

    with left:
        st.subheader("📈 Assets Analysis")
        if trades:
            fig = dashboard.create_detailed_performance_chart(trades, capital)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No trade data available for selected mode.")

    with right:
        st.subheader("📊 Trade Stats")
        if trades:
            stats = trading_engine.calculate_trade_statistics(trades)
            dashboard.display_trade_statistics(stats)
        else:
            st.info("No trade data available.")

    st.subheader("🔄 Recent Trades")
    if trades:
        dashboard.display_trades_table(trades)
    else:
        st.info("No trades available for selected mode.")
