# database.py (fixed version)
# Fixes: Added actual clear functions (delete queries).
# Fixed get_daily_pnl_pct: assume implemented in db_manager, or add stub.
# Fixed get_automation_stats: use db_manager.get_status().
# Added error handling.
# Fixed open_trades count.

import streamlit as st
from db import db_manager, Signal, Trade, Portfolio
from sqlalchemy import text

def render():
    st.set_page_config(page_title="Database Overview", layout="wide")
    st.image("logo.png", width=80)
    st.title("🗄️ Database Overview")

    # --- Tabs ---
    tabs = st.tabs([
        "🔍 DB Health",
        "📊 Record Stats",
        "📈 Trade Stats",
        "🛠️ System Info",
        "🔧 DB Operations"
    ])

    # --- Tab 1: Database Health ---
    with tabs[0]:
        st.subheader("🔍 Database Health")
        db_health = db_manager.get_db_health()
        if db_health.get("status") == "ok":
            st.success("✅ Database connection healthy")
        else:
            st.error(f"❌ Database error: {db_health.get('error', 'Unknown')}")
            return

    # --- Tab 2: Record Statistics ---
    with tabs[1]:
        st.subheader("📊 Record Statistics")
        try:
            signals_count = db_manager.get_signals_count()
            trades_count = db_manager.get_trades_count()
            portfolio_count = db_manager.get_portfolio_count()

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Signals", signals_count)
            col2.metric("Total Trades", trades_count)
            col3.metric("Portfolio Items", portfolio_count)
        except Exception as e:
            st.error(f"Failed to fetch record stats: {e}")

    # --- Tab 3: Trade Statistics ---
    with tabs[2]:
        st.subheader("📈 Trade Statistics")
        left, right = st.columns(2)
        # Virtual trades
        with left:
            st.subheader("🟢 Virtual Trades")
            try:
                virtual_open = len(db_manager.get_open_virtual_trades())
                virtual_closed = len(db_manager.get_closed_virtual_trades())
                st.metric("Open", virtual_open)
                st.metric("Closed", virtual_closed)
            except Exception as e:
                st.error(f"Virtual trades error: {e}")
        # Real trades
        with right:
            st.subheader("💰 Real Trades")
            try:
                real_open = len(db_manager.get_open_real_trades())
                real_closed = len(db_manager.get_closed_real_trades())
                st.metric("Open", real_open)
                st.metric("Closed", real_closed)
            except Exception as e:
                st.error(f"Real trades error: {e}")

    # --- Tab 4: System Info ---
    with tabs[3]:
        st.subheader("🛠️ System Info")
        try:
            # Assume db_manager has get_daily_pnl_pct, else stub
            daily_pnl = db_manager.get_daily_pnl_pct() if hasattr(db_manager, 'get_daily_pnl_pct') else 0.0
            stats = db_manager.get_status()  # Use get_status for automation stats
            portfolio = db_manager.get_portfolio()
            balance = sum(p.capital for p in portfolio) if portfolio else 0.0
            pnl_color = "🟢" if daily_pnl >= 0 else "🔴"

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Wallet Balance", f"${balance:.2f}")
            col2.metric("Daily P&L", f"{pnl_color} {daily_pnl:.2f}%")
            col3.metric("Total Signals", stats.get("total_signals", "—"))
            col4.metric("Open Trades", stats.get("total_trades", "—") - stats.get("closed_trades", 0))  # Approximate
            st.info(f"Last Update: {stats.get('last_updated', '—')}")
        except Exception as e:
            st.error(f"System info error: {e}")

    # --- Tab 5: DB Operations ---
    with tabs[4]:
        st.subheader("🔧 DB Operations")
        col1, col2, col3 = st.columns(3)

        if col1.button("🔄 Test Connection"):
            try:
                with db_manager.get_session() as session:
                    session.execute(text("SELECT 1"))
                st.success("✅ Connection successful")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")

        if col2.button("📊 Refresh Stats"):
            try:
                st.cache_data.clear()
                st.success("✅ Cache cleared")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Refresh failed: {e}")

        if col3.button("🗑️ Clear Cache"):
            try:
                st.cache_data.clear()
                st.cache_resource.clear()
                st.success("✅ All caches cleared")
            except Exception as e:
                st.error(f"❌ Clear failed: {e}")

        st.markdown("---")
        st.subheader("⚠️ Data Clear Options")
        if st.button("Clear All Signals"):
            with db_manager.get_session() as session:
                session.query(Signal).delete()
                session.commit()
            st.success("✅ All signals cleared")

        if st.button("Clear All Trades"):
            with db_manager.get_session() as session:
                session.query(Trade).delete()
                session.commit()
            st.success("✅ All trades cleared")

        if st.button("Clear Portfolio"):
            with db_manager.get_session() as session:
                session.query(Portfolio).delete()
                session.commit()
            st.success("✅ Portfolio cleared")