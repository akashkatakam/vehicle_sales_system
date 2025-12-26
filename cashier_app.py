# cashier_app.py

import streamlit as st
from datetime import date
import cashier_ui

KHAMMAM_BRANCH_ID = "1"


def main():
    st.set_page_config(page_title="Cashier App", layout="wide", page_icon="🧾")
    st.title("🧾 Cashier System")

    with st.sidebar:
        st.header("Settings")
        selected_branch_id = st.text_input("Branch ID", value=KHAMMAM_BRANCH_ID)
        selected_date = st.date_input("Working Date", value=date.today())
        st.divider()
        st.info(f"Active Branch ID: **{selected_branch_id}**")

    # Updated Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📝 New Entry", "📥 Import Daybook", "📖 Daybook", "📊 Ledger"])

    with tab1:
        cashier_ui.render_entry_form(selected_branch_id, selected_date)

    with tab2:
        # --- UPDATED: Pass selected_date (Working Date) here ---
        cashier_ui.render_import_tab(selected_branch_id, selected_date)

    with tab3:
        cashier_ui.render_daybook(selected_branch_id, selected_date)

    with tab4:
        cashier_ui.render_ledger(selected_branch_id)


if __name__ == "__main__":
    main()