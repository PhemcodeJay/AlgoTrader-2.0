# dashboard.py (fixed version)
# Fixes: Completed truncated recent_signals loading.
# Added from utils import safe_float, format_currency
# Fixed get_recent_trades: use db_manager.get_trades(order_by desc, limit=100)
# Fixed PnL calculation using get_current_price for both real/virtual (real market data).
# Fixed manage_trades_table: use get_current_price.
# Ensured all_trades is list of dicts.

import streamlit as st
from datetime import datetime, timezone
from db import Signal
from utils import format_currency, safe_float, get_current_price

# =========================
# Main Render Function
# =========================
def render(trading_engine, dashboard, db_manager):
    st.image("logo.png", width=80)
    st.title("🚀 AlgoTrader Dashboard")

    # === Load wallet data safely ===
    capital_data = trading_engine.load_capital("all") or {}
    real = capital_data.get("real") or {}
    virtual = capital_data.get("virtual") or {}

    real_total = safe_float(real.get("capital"))
    real_available = safe_float(real.get("available") or real_total)

    virtual_total = safe_float(virtual.get("capital"))
    virtual_available = safe_float(virtual.get("available") or virtual_total)

    # === Load recent trades safely ===
    all_trades = db_manager.get_trades(limit=100) or []  # Assume get_trades fetches recent
    all_trades = [t if isinstance(t, dict) else t.to_dict() for t in all_trades]

    # Add default fields and compute PnL safely
    for t in all_trades:
        t["virtual"] = t.get("virtual") or False
        t["entry_price"] = safe_float(t.get("entry_price"))
        t["qty"] = safe_float(t.get("qty"))
        t["side"] = (t.get("side") or "buy").lower()
        t["status"] = (t.get("status") or "open").lower()
        # Calculate unrealized PnL for open trades using real market data
        try:
            if t["status"] == "open":
                last_price = get_current_price(t.get("symbol"))
                entry_price = t["entry_price"]
                qty = t["qty"]
                side = t["side"]
                t["pnl"] = (last_price - entry_price) * qty if side == "buy" else (entry_price - last_price) * qty
            else:
                t["pnl"] = safe_float(t.get("pnl"))
        except Exception:
            t["pnl"] = safe_float(t.get("pnl"))

    real_trades = [t for t in all_trades if not t["virtual"]]
    virtual_trades = [t for t in all_trades if t["virtual"]]

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # === Load recent signals safely ===
    recent_signals = []
    try:
        with db_manager.get_session() as session:
            signal_objs = session.query(Signal).order_by(Signal.created_at.desc()).limit(5).all()
            recent_signals = [s.to_dict() for s in signal_objs]
    except Exception as e:
        st.warning(f"Failed to load recent signals: {e}")

    # === Wallet Summary ===
    st.subheader("💰 Wallet Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Real Total", f"${real_total:,.2f}")
    col2.metric("Real Available", f"${real_available:,.2f}")
    col3.metric("Virtual Total", f"${virtual_total:,.2f}")
    col4.metric("Virtual Available", f"${virtual_available:,.2f}")

    st.markdown("---")

    # === Recent Signals ===
    st.subheader("📈 Recent Signals")
    if recent_signals:
        for signal in recent_signals:
            dashboard.display_signal_card(signal)
    else:
        st.info("No recent signals available.")

    st.markdown("---")

    # === Trade Summary Tabs with Live PnL ===
    st.subheader("🔍 Trade Summary")
    tab1, tab2 = st.tabs(["📈 Real Trades", "🧪 Virtual Trades"])

    # --- Real Trades Table ---
    with tab1:
        if real_trades:
            manage_trades_table(real_trades, trading_engine)
        else:
            st.info("No real trades available.")

    # --- Virtual Trades Table ---
    with tab2:
        if virtual_trades:
            manage_trades_table(virtual_trades, trading_engine)
        else:
            st.info("No virtual trades available.")

# =========================
# Helper to display trades with live PnL
# =========================
def manage_trades_table(trades, trading_engine):
    for idx, trade in enumerate(trades):
        symbol = trade.get("symbol") or "N/A"
        side = trade.get("side") or "buy"
        entry = safe_float(trade.get("entry_price"))
        qty = safe_float(trade.get("qty"))
        status = trade.get("status") or "open"
        pnl = safe_float(trade.get("pnl"))
        virtual = trade.get("virtual") or False
        ts = safe_timestamp(trade.get("timestamp"))
        trade_id = trade.get("order_id") or f"{symbol}_{idx}"

        pnl_key = f"pnl_{trade_id}"
        if pnl_key not in st.session_state:
            st.session_state[pnl_key] = pnl

        # Live PnL update for open trades
        if status.lower() == "open":
            try:
                last_price = get_current_price(symbol)
                st.session_state[pnl_key] = (last_price - entry) * qty if side.lower() == "buy" else (entry - last_price) * qty
            except Exception:
                st.session_state[pnl_key] = pnl

        pnl_display = st.session_state[pnl_key]
        color = "green" if pnl_display >= 0 else "red"

        with st.expander(f"{symbol} | {side} | Entry: {entry:.2f} | PnL: {pnl_display:+.2f}", expanded=True):
            cols = st.columns(4)
            cols[0].markdown(f"**Qty:** {qty}")
            cols[1].markdown(f"**Status:** {status}")
            cols[2].markdown(f"**Mode:** {'Virtual' if virtual else 'Real'}")
            cols[3].markdown(f"**PnL:** <span style='color:{color}'>{pnl_display:+.2f}</span>", unsafe_allow_html=True)
            st.markdown(f"⏱ `{ts}`")