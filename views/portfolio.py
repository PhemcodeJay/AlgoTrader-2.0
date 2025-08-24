# portfolio.py (fixed version)
# Fixes: Completed truncated sections in render_trades_tab, manage_open_trades.
# Added from utils import safe_float, format_currency, get_current_price
# Defined safe_timestamp.
# Fixed fetch_trades to use trading_engine.get_open_positions(mode), etc.
# For real mode, sync open trades from Bybit client.
# For PnL, use get_current_price for virtual, client.get_ticker for real.
# Added error handling.
# Ensured trade is dict.

import streamlit as st
from datetime import datetime, timezone
from utils import format_currency, safe_float, get_current_price

# =========================
# Helper Functions
# =========================
def safe_timestamp(ts):
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M")
    return ts or "N/A"

def ensure_dict(trade):
    if not isinstance(trade, dict):
        return trade.to_dict() if hasattr(trade, 'to_dict') else {}
    return trade

def fetch_trades(trading_engine, trade_type, mode):
    virtual = None if mode == "All" else (mode == "Virtual")
    if trade_type == "open":
        trades = trading_engine.get_open_positions(mode=mode.lower() if mode != "All" else "all")
    elif trade_type == "closed":
        trades = trading_engine.get_closed_real_trades() + trading_engine.get_closed_virtual_trades() if mode == "All" else \
                 trading_engine.get_closed_virtual_trades() if mode == "Virtual" else trading_engine.get_closed_real_trades()
    else:
        trades = trading_engine.get_open_positions(mode=mode.lower() if mode != "All" else "all") + \
                 (trading_engine.get_closed_real_trades() + trading_engine.get_closed_virtual_trades() if mode == "All" else \
                  trading_engine.get_closed_virtual_trades() if mode == "Virtual" else trading_engine.get_closed_real_trades())
    
    # For real mode, sync from Bybit if open
    if trade_type in ["open", "all"] and mode in ["Real", "All"]:
        trading_engine.client.update_unrealized_pnl()  # Sync PnL
    
    return trades

# =========================
# Main Render Function
# =========================
def render(trading_engine, dashboard, db_manager, automated_trader):
    # --- Page Config ---
    st.set_page_config(page_title="💼 Wallet Summary", layout="wide")
    st.image("logo.png", width=80)
    st.title("💼 Wallet Summary")

    # --- Wallet Overview ---
    try:
        capital_data = trading_engine.load_capital("all") or {}
        real = capital_data.get("real", {})
        virtual = capital_data.get("virtual", {})

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Real Balance", f"${safe_float(real.get('capital')):,.2f}")
        col2.metric("Available Real", f"${safe_float(real.get('available')):,.2f}")
        col3.metric("🧪 Virtual Balance", f"${safe_float(virtual.get('capital')):,.2f}")
        col4.metric("Available Virtual", f"${safe_float(virtual.get('available')):,.2f}")

    except Exception as e:
        st.error(f"Error loading wallet data: {e}")

    st.markdown("---")

    # ---------------------------
    # Trades Tabs
    # ---------------------------
    tabs = st.tabs(["🔄 All Trades", "📂 Open Trades", "✅ Closed Trades"])
    tab_types = ["all", "open", "closed"]

    for idx, trade_type in enumerate(tab_types):
        with tabs[idx]:
            render_trades_tab(trading_engine, dashboard, trade_type, idx)

# =========================
# Trades Tab Renderer
# =========================
def render_trades_tab(trading_engine, dashboard, trade_type, tab_index):
    mode = st.radio("Mode", ["All", "Real", "Virtual"], key=f"mode_{trade_type}", horizontal=True)
    trades = fetch_trades(trading_engine, trade_type, mode)
    trades = [ensure_dict(t) for t in trades]

    # Calculate PnL and trade age
    for t in trades:
        entry_price = safe_float(t.get("entry_price"))
        qty = safe_float(t.get("qty"))
        side = (t.get("side") or "buy").lower()

        if (t.get("status") or "").lower() == "open":
            try:
                last_price = get_current_price(t.get("symbol"))  # Real market data for both
                t["pnl"] = (last_price - entry_price) * qty if side == "buy" else (entry_price - last_price) * qty
            except Exception:
                t["pnl"] = 0.0
        else:
            t["pnl"] = safe_float(t.get("pnl"))

    if trades:
        st.subheader(f"{trade_type.capitalize()} Trades ({mode})")
        manage_open_trades(trades, trading_engine)
    else:
        st.info(f"No {trade_type} trades in {mode} mode.")

# =========================
# Manage Open Trades
# =========================
def manage_open_trades(trades, trading_engine):
    for idx, trade in enumerate(trades):
        symbol = trade.get("symbol") or "N/A"
        side = trade.get("side") or "buy"
        entry = safe_float(trade.get("entry_price"))
        qty = safe_float(trade.get("qty"))
        sl = safe_float(trade.get("stop_loss"))
        tp = safe_float(trade.get("take_profit"))
        pnl = safe_float(trade.get("pnl"))
        status = trade.get("status") or "N/A"
        virtual = trade.get("virtual") or False
        ts = safe_timestamp(trade.get("timestamp"))
        trade_id = trade.get("order_id") or f"{symbol}_{idx}"

        pnl_key = f"pnl_{trade_id}"
        close_key = f"close_{trade_id}"

        if pnl_key not in st.session_state:
            st.session_state[pnl_key] = pnl

        if status.lower() == "open":
            try:
                last_price = get_current_price(symbol)
                st.session_state[pnl_key] = (last_price - entry) * qty if side.lower() == "buy" else (entry - last_price) * qty
            except Exception:
                st.session_state[pnl_key] = pnl

        pnl_display = safe_float(st.session_state.get(pnl_key, 0.0))
        color = "green" if pnl_display >= 0 else "red"

        with st.expander(f"{symbol} | {side} | Entry: {entry:.2f} | PnL: {pnl_display:+.2f}", expanded=True):
            cols = st.columns(4)
            cols[0].markdown(f"**Qty:** {qty:.2f}")
            cols[1].markdown(f"**SL:** {sl:.2f}")
            cols[2].markdown(f"**TP:** {tp:.2f}")
            cols[3].markdown(f"**PnL:** <span style='color:{color}'>{pnl_display:+.2f}</span>", unsafe_allow_html=True)

            st.markdown(f"**Status:** {status} | **Mode:** {'Virtual' if virtual else 'Real'} ⏱ `{ts}`")

            if status.lower() == "open":
                if st.button("❌ Close Trade", key=close_key):
                    success = trading_engine.close_trade(str(trade_id), virtual)
                    if success:
                        st.success(f"{'Virtual' if virtual else 'Real'} trade closed successfully.")
                        trade["status"] = "closed"
                        trade["pnl"] = st.session_state[pnl_key]
                        # Update capital for virtual
                        if virtual:
                            trading_engine.apply_pnl_to_capital(trade)
                    else:
                        st.error("Failed to close trade.")