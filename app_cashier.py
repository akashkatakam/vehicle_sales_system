import streamlit as st
from datetime import date
from core.database import db_session
from core.auth import check_login
from core.data_manager import get_user_accessible_branches
from features.cashier import ui as cashier_ui

def main():
    st.set_page_config(page_title="Cashier App", layout="wide", page_icon="🧾")
    if not check_login(): return
    st.title("🧾 Cashier System")

    user_access = st.session_state.get("accessible_branches", [])
    with db_session() as db:
        all_branches = get_user_accessible_branches(db, user_access)
        branch_options = {b.Branch_Name: b.Branch_ID for b in all_branches}

    if not branch_options:
        st.error("⛔ Access Denied.")
        return

    with st.sidebar:
        st.header("Settings")
        selected_branch_name = st.selectbox("Select Branch", list(branch_options.keys()))
        selected_branch_id = branch_options[selected_branch_name]
        selected_date = st.date_input("Working Date", value=date.today())
        st.info(f"Active: **{selected_branch_id}**")

    t1, t2, t3, t4 = st.tabs(["📝 New Entry", "📥 Import Daybook", "📖 Daybook", "📊 Ledger"])
    with t1: cashier_ui.render_entry_form(selected_branch_id, selected_date)
    with t2: cashier_ui.render_import_tab(selected_branch_id, selected_date)
    with t3: cashier_ui.render_daybook(selected_branch_id, selected_date)
    with t4: cashier_ui.render_ledger(selected_branch_id)

if __name__ == "__main__":
    main()