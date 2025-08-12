import streamlit as st
from datetime import datetime, timezone
from utils import format_trades

def render(trading_engine, dashboard):
    st.image("logo.png", width=80)
    st.title("💼 Wallet Summary")

    def get_attr(t, attr, default=None):
        return t.get(attr, default) if isinstance(t, dict) else getattr(t, attr, default)

    # Wallet Overview
    try:
        capital_data = trading_engine.load_capital("all") or {}
        real = capital_data.get("real", {})
        virtual = capital_data.get("virtual", {})

        col1, col2 = st.columns(2)
        with col1:
            st.metric("💰 Real Balance", f"${float(real.get('capital', 0.0)):,.2f}")
            st.metric("Available Real", f"${float(real.get('available', real.get('capital', 0.0))):,.2f}")
        with col2:
            st.metric("🧪 Virtual Balance", f"${float(virtual.get('capital', 0.0)):,.2f}")
            st.metric("Available Virtual", f"${float(virtual.get('available', virtual.get('capital', 0.0))):,.2f}")
    except Exception as e:
        st.error(f"Error loading wallet data: {e}")

    st.markdown("---")

    # Tabs
    tabs = st.tabs(["🔄 All Trades", "📂 Open Trades", "✅ Closed Trades"])

    # === TAB 1: ALL TRADES ===
    with tabs[0]:
        show_trades_tab(trading_engine, dashboard, get_attr, mode_key="mode_all", tab_index=0)

    # === TAB 2: OPEN TRADES ===
    with tabs[1]:
        show_trades_tab(trading_engine, dashboard, get_attr, mode_key="mode_open", tab_index=1)

    # === TAB 3: CLOSED TRADES ===
    with tabs[2]:
        show_trades_tab(trading_engine, dashboard, get_attr, mode_key="mode_closed", tab_index=2)


def show_trades_tab(trading_engine, dashboard, get_attr, mode_key, tab_index):
    """Handles the rendering logic for each tab."""
    mode = st.radio("Mode", ["All", "Real", "Virtual"], key=mode_key, horizontal=True)

    try:
        trades = load_trades_for_tab(trading_engine, tab_index, mode)
        trades = ensure_dict_format(trades)

        if trades:
            dashboard.display_trades_table(trades)

            if tab_index == 2:  # Closed trades chart
                st.subheader("📈 Performance Chart")
                fig = dashboard.create_portfolio_performance_chart(trades, start_balance=100.0)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"No {['', 'open', 'closed'][tab_index]} trades found.")
    except Exception as e:
        st.error(f"Error loading trades: {e}")
        trades = []

    # Capital & Metrics
    capital, available, start_balance, currency = load_capital_data(trading_engine, mode)
    display_metrics(trading_engine, trades, get_attr, capital, available, start_balance, tab_index)

    # Charts & Stats
    left, right = st.columns([2, 1])
    with left:
        st.subheader("📈 Assets Analysis")
        if trades:
            fig = dashboard.create_detailed_performance_chart(trades, capital)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No trade data available.")

    with right:
        st.subheader("📊 Trade Stats")
        if trades:
            stats = trading_engine.calculate_trade_statistics(trades)
            dashboard.display_trade_statistics(stats)
        else:
            st.info("No statistics available.")

    st.markdown("---")

    # Trades Table
    st.subheader("🧾 Trades Table")
    paginated_trades = paginate_trades(format_trades(trades), f"page_{tab_index}")

    # Open Trade Management
    if tab_index == 1:
        manage_open_trades(paginated_trades, trading_engine)
    else:
        dashboard.display_trades_table(paginated_trades)


# === Helper functions ===

def load_trades_for_tab(trading_engine, tab_index, mode):
    if tab_index == 0:  # All trades
        return trading_engine.get_recent_trades(limit=100) or []
    elif tab_index == 1:  # Open trades
        if mode == "All":
            return (trading_engine.get_open_real_trades() or []) + (trading_engine.get_open_virtual_trades() or [])
        return trading_engine.get_open_real_trades() if mode == "Real" else trading_engine.get_open_virtual_trades()
    else:  # Closed trades
        if mode == "All":
            return (trading_engine.get_closed_real_trades() or []) + (trading_engine.get_closed_virtual_trades() or [])
        return trading_engine.get_closed_real_trades() if mode == "Real" else trading_engine.get_closed_virtual_trades()


def ensure_dict_format(trades):
    processed = []
    for trade in trades:
        if hasattr(trade, 'to_dict'):
            processed.append(trade.to_dict())
        elif isinstance(trade, dict):
            processed.append(trade)
        else:
            trade_dict = {attr: getattr(trade, attr, None)
                          for attr in ['symbol', 'side', 'qty', 'entry_price', 'exit_price', 'pnl', 'status', 'timestamp', 'virtual']}
            processed.append(trade_dict)
    return processed


def load_capital_data(trading_engine, mode):
    if mode == "All":
        balances = trading_engine.load_capital("all") or {}
        real = balances.get("real", {})
        virtual = balances.get("virtual", {})
        capital = float(real.get("capital", 0.0)) + float(virtual.get("capital", 0.0))
        available = float(real.get("available", real.get("capital", 0.0))) + float(virtual.get("available", virtual.get("capital", 0.0)))
        start_balance = float(real.get("start_balance", 0.0)) + float(virtual.get("start_balance", 0.0))
        currency = real.get("currency") or virtual.get("currency", "USD")
    else:
        balance = trading_engine.load_capital(mode.lower()) or {}
        capital = float(balance.get("capital", 0.0))
        available = float(balance.get("available", balance.get("capital", 0.0)))
        start_balance = float(balance.get("start_balance", 0.0))
        currency = balance.get("currency", "USD")
    return capital, available, start_balance, currency


def display_metrics(trading_engine, trades, get_attr, capital, available, start_balance, tab_index):
    total_return_pct = ((capital - start_balance) / start_balance * 100) if start_balance else 0.0
    win_rate = trading_engine.calculate_win_rate(trades)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_pnl = sum(float(get_attr(t, "pnl", 0.0) or 0.0) for t in trades if str(get_attr(t, "timestamp", "")).startswith(today_str))
    unrealized_pnl = sum(float(get_attr(t, "unrealized_pnl", 0.0)) for t in trades) if tab_index == 1 else 0.0
    realized_pnl = sum(float(get_attr(t, "pnl", 0.0)) for t in trades) if tab_index == 2 else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Capital", f"${capital:,.2f}")
    col2.metric("Available", f"${available:,.2f}")
    col3.metric("Total Return", f"{total_return_pct:+.2f}%")
    col4.metric("Daily P&L", f"${daily_pnl:+.2f}")
    col5.metric("Win Rate", f"{win_rate:.2f}%")

    if tab_index == 1:
        st.markdown("### 📊 Unrealized P&L")
        st.metric("Unrealized PnL", f"${unrealized_pnl:+.2f}")
    if tab_index == 2:
        st.markdown("### 💰 Realized P&L")
        st.metric("Realized PnL", f"${realized_pnl:+.2f}")


def paginate_trades(formatted_trades, page_key):
    if not formatted_trades:
        st.info("No trades found.")
        return []
    page_size = 10
    total = len(formatted_trades)
    page_num = st.number_input("Page", min_value=1, max_value=(total - 1) // page_size + 1, step=1, key=page_key)
    start = (page_num - 1) * page_size
    end = start + page_size
    return formatted_trades[start:end]


def manage_open_trades(trades, trading_engine):
    for trade in trades:
        symbol = trade.get('symbol', 'UNKNOWN')
        side = trade.get('side', 'N/A')
        entry = trade.get('entry_price', 'N/A')
        qty = trade.get('qty', 0)
        sl = trade.get('stop_loss', 'N/A')
        tp = trade.get('take_profit', 'N/A')
        pnl = trade.get('pnl', 0.0)
        status = trade.get('status', 'N/A')
        virtual = trade.get('virtual', False)
        time_str = trade.get('timestamp', '')

        with st.expander(f"{symbol} | {side} | Entry: {entry}"):
            cols = st.columns(4)
            cols[0].markdown(f"**Qty:** {qty}")
            cols[1].markdown(f"**SL:** {sl}")
            cols[2].markdown(f"**TP:** {tp}")
            cols[3].markdown(f"**PnL:** {pnl}")
            st.markdown(f"**Status:** {status} | **Mode:** {'Virtual' if virtual else 'Real'} ⏱ `{time_str}`")

            if status.lower() == "open":
                trade_id = trade.get("order_id")
                is_virtual = virtual

                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("❌ Close Trade", key=f"close_{symbol}_{trade_id}_{time_str}"):
                        if trade_id:
                            success = trading_engine.close_trade(str(trade_id), is_virtual)
                            if success:
                                st.success(f"{'Virtual' if is_virtual else 'Real'} trade closed successfully.")
                                st.experimental_rerun()
                            else:
                                st.error("Failed to close trade.")
                        else:
                            st.error("Trade ID not found.")
                with col2:
                    st.info(f"Mode: {'🧪 Virtual Trading' if is_virtual else '💰 Real Trading'}")
