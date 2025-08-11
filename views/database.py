import streamlit as st
from db import db_manager

def render():
    st.image("logo.png", width=80)
    st.title("🗄️ Database Overview")

    # --- Tabs ---
    tabs = st.tabs([
        "🔍 Database Health",
        "📊 Record Statistics",
        "📈 Trade Statistics",
        "🛠️ System Info",
        "🔧 DB Operations"
    ])

    # --- Database Health Tab ---
    with tabs[0]:
        st.subheader("🔍 Database Health")
        db_health = db_manager.get_db_health()
        
        if db_health.get("status") == "ok":
            st.success("✅ Database connection healthy")
        else:
            st.error(f"❌ Database error: {db_health.get('error', 'Unknown error')}")
            return

    # --- Record Statistics Tab ---
    with tabs[1]:
        st.subheader("📊 Record Statistics")
        col1, col2, col3 = st.columns(3)
        
        try:
            signals_count = db_manager.get_signals_count()
            trades_count = db_manager.get_trades_count()
            portfolio_count = db_manager.get_portfolio_count()
            
            col1.metric("Total Signals", signals_count)
            col2.metric("Total Trades", trades_count)
            col3.metric("Portfolio Items", portfolio_count)
        except Exception as e:
            st.error(f"Failed to get record counts: {e}")

    # --- Trade Statistics Tab ---
    with tabs[2]:
        st.subheader("📈 Trade Statistics")
        left, right = st.columns(2)
        
        with left:
            st.subheader("🟢 Virtual Trades")
            try:
                virtual_open = len(db_manager.get_open_virtual_trades())
                virtual_closed = len(db_manager.get_closed_virtual_trades())
                st.write(f"**Open:** {virtual_open}")
                st.write(f"**Closed:** {virtual_closed}")
            except Exception as e:
                st.error(f"Virtual trades error: {e}")

        with right:
            st.subheader("💰 Real Trades")
            try:
                real_open = len(db_manager.get_open_real_trades())
                real_closed = len(db_manager.get_closed_real_trades())
                st.write(f"**Open:** {real_open}")
                st.write(f"**Closed:** {real_closed}")
            except Exception as e:
                st.error(f"Real trades error: {e}")

    # --- System Info Tab ---
    with tabs[3]:
        st.subheader("🛠️ System Info")
        try:
            portfolio = db_manager.get_portfolio()
            balance = sum(p.capital for p in portfolio) if portfolio else 0.0
            daily_pnl = db_manager.get_daily_pnl_pct()
            stats = db_manager.get_automation_stats()

            color = "🟢" if daily_pnl >= 0 else "🔴"
            st.write(f"**Wallet:** ${balance:.2f}")
            st.write(f"**Daily P&L:** {color} {daily_pnl:.2f}%")
            st.write(f"**Total Signals:** {stats.get('total_signals', '—')}")
            st.write(f"**Open Trades:** {stats.get('open_trades', '—')}")
            st.write(f"**Last Update:** {stats.get('timestamp', '—')}")
        except Exception as e:
            st.error(f"System info error: {e}")

    # --- DB Operations Tab ---
    with tabs[4]:
        st.subheader("🔧 DB Operations")
        col1, col2, col3 = st.columns(3)

        if col1.button("🔄 Test Connection"):
            try:
                with db_manager.get_session() as session:
                    session.execute("SELECT 1")
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
