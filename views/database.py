import streamlit as st
import pandas as pd

def render(db_manager):
    st.title("🗄️ Trade Journal")
    col1, col2, col3 = st.columns(3)

    try:
        db_balance = db_manager.get_portfolio_balance()
        col1.metric("Database Status", "🟢 Ok" if db_balance is not None else "🔴 Error")
    except Exception as e:
        col1.metric("Database Status", "🔴 Error"); st.error(str(e))

    try:
        trades = db_manager.get_trades(limit=1000)
        col2.metric("Total Trades", len(trades))
    except:
        col2.metric("Total Trades", "Error")

    try:
        signals = db_manager.get_signals(limit=1000, active_only=False)
        col3.metric("Total Signals", len(signals))
    except:
        col3.metric("Total Signals", "Error")

    st.markdown("---")
    left, right = st.columns(2)
    with left:
        st.subheader("📊 Recent Trades")
        try:
            recent = db_manager.get_trades(limit=5)
            if recent:
                for t in recent:
                    pnl_color = "🟢" if t["pnl"] > 0 else "🔴"
                    st.write(f"{pnl_color} {t['symbol']} - ${t['pnl']:.2f}")
            else:
                st.info("No trades in database")
        except Exception as e:
            st.error(str(e))

    with right:
        st.subheader("🛠️ System Info")
        try:
            bal = db_manager.get_portfolio_balance()
            daily_pnl = db_manager.get_daily_pnl()
            stats = db_manager.get_automation_stats()
            st.write(f"**Wallet:** ${bal:.2f}")
            color = "🟢" if daily_pnl >= 0 else "🔴"
            st.write(f"**Daily P&L:** {color} ${daily_pnl:.2f}")
            st.write(f"**Automation Signals:** {stats.get('signals_generated', 0)}")
            st.write(f"**Automation Trades:** {stats.get('trades_executed', 0)}")
        except Exception as e:
            st.error(str(e))

    st.markdown("---")
    st.subheader("🔧 DB Operations")
    col1, col2, col3 = st.columns(3)
    if col1.button("🔄 Test Connection"):
        try:
            bal = db_manager.get_portfolio_balance()
            st.success(f"Connected — Balance: ${bal:.2f}")
        except Exception as e:
            st.error(f"Connection failed: {e}")

    if col2.button("📊 Refresh Stats"):
        st.rerun()


    if col3.button("🔄 Migrate JSON Data"):
        try:
            db_manager.migrate_json_data()
            st.success("Migration complete")
        except Exception as e:
            st.error(f"Migration error: {e}")

    st.subheader("📋 Database Tables")
    for tbl, desc in {
        "portfolio": "Wallet balance history",
        "trades": "Executed trades & P&L",
        "signals": "Generated trading signals",
        "automation_stats": "Automation logs",
        "system_settings": "Config key‑value pairs"
    }.items():
        with st.expander(f"{tbl.upper()}"):
            st.write(f"**{desc}**")
            try:
                df = getattr(db_manager, f"get_{tbl}")(limit=10)
                st.dataframe(pd.DataFrame(df), use_container_width=True)
            except Exception as e:
                st.error(f"Error loading {tbl}: {e}")
