# cashier_app.py

import streamlit as st
from datetime import date
import cashier_ui
import models
from database import get_db
from auth import check_login  # <--- Import the login logic


def main():
    # 1. Page Config must be the very first command
    st.set_page_config(page_title="Cashier App", layout="wide", page_icon="🧾")

    # 2. Check Login
    # This renders the login form if not logged in, and returns False.
    # If logged in, it renders the user info in sidebar and returns True.
    if not check_login():
        return

    st.title("🧾 Cashier System")

    # 3. Fetch Accessible Branches for the User
    # auth.py stores access in st.session_state["accessible_branches"]
    user_access = st.session_state.get("accessible_branches", [])

    db = next(get_db())
    branch_options = {}
    try:
        if "ALL" in user_access:
            # User can access all branches
            all_branches = db.query(models.Branch).filter(models.Branch.dc_gen_enabled==True).all()
        else:
            # Filter branches based on assigned IDs
            all_branches = db.query(models.Branch).filter(models.Branch.Branch_ID.in_(user_access)).all()

        # Create a dictionary for the dropdown: "Branch Name" -> "Branch ID"
        branch_options = {b.Branch_Name: b.Branch_ID for b in all_branches}
    finally:
        db.close()

    if not branch_options:
        st.error("⛔ Access Denied: You do not have access to any branches. Please contact the administrator.")
        return

    # 4. Sidebar Settings
    with st.sidebar:
        st.header("Settings")

        # Replace Text Input with Secure Dropdown
        selected_branch_name = st.selectbox("Select Branch", list(branch_options.keys()))
        selected_branch_id = branch_options[selected_branch_name]

        selected_date = st.date_input("Working Date", value=date.today())
        st.divider()
        st.info(f"Active Branch ID: **{selected_branch_id}**")

    # 5. Main Application Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📝 New Entry", "📥 Import Daybook", "📖 Daybook", "📊 Ledger"])

    with tab1:
        cashier_ui.render_entry_form(selected_branch_id, selected_date)

    with tab2:
        cashier_ui.render_import_tab(selected_branch_id, selected_date)

    with tab3:
        cashier_ui.render_daybook(selected_branch_id, selected_date)

    with tab4:
        cashier_ui.render_ledger(selected_branch_id)


if __name__ == "__main__":
    main()