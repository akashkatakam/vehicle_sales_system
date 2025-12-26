# cashier_ui.py

import streamlit as st
import pandas as pd
from datetime import date
import cashier_logic
from database import get_db

import streamlit as st
import pandas as pd
from datetime import date
import cashier_logic
from database import get_db
import models  # Needed for querying branches if not passed


def render_entry_form(branch_id: str, selected_date: date):
    st.subheader("Enter Receipt or Voucher")

    # --- DC Lookup Section ---
    db = next(get_db())
    dc_search = st.text_input("Link to DC Number (Optional)", placeholder="e.g. DC-0050")

    linked_dc_number = None
    default_party = ""
    default_desc = ""

    if dc_search:
        sale_rec = cashier_logic.get_sales_record_by_dc(db, dc_search)
        if sale_rec:
            st.info(
                f"✅ Found: **{sale_rec.Customer_Name}** | Model: {sale_rec.Model} | Pending: **₹{sale_rec.Payment_Shortfall:,.2f}**")
            linked_dc_number = sale_rec.DC_Number
            default_party = sale_rec.Customer_Name
            default_desc = f"Payment for {sale_rec.Model} ({sale_rec.Variant})"
        else:
            st.warning("DC Number not found.")

    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            txn_type = st.selectbox("Type", ["Receipt", "Voucher"])
            if txn_type == "Receipt":
                category_opts = ["General Receipt", "Branch Receipt", "Service", "FCI", "Vehicle Sale"]
            else:
                category_opts = ["General Expense", "Fuel", "Salary", "Maintenance", "Branch Transfer"]

            category = st.selectbox("Category", category_opts)
            # Pre-fill Party Name if DC is found
            party_name = st.text_input("Party / Source Name", value=default_party)

        with col2:
            mode = st.selectbox("Payment Mode", ["Cash", "Online", "Card"])
            amount = st.number_input("Amount (₹)", min_value=0.0, step=100.0)
            # Pre-fill Description if DC is found
            description = st.text_area("Description", value=default_desc)

        if st.form_submit_button("Save Transaction", type="primary"):
            if amount > 0:
                data = {
                    "date": selected_date,
                    "transaction_type": txn_type,
                    "category": category,
                    "payment_mode": mode,
                    "amount": amount,
                    "description": description,
                    "branch_id": branch_id,
                    "party_name": party_name,
                    "dc_number": linked_dc_number  # Save the link
                }
                success, msg = cashier_logic.add_transaction(db, data)
                if success:
                    st.success("Transaction Saved!")
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Enter valid amount")
    db.close()


def render_import_tab(current_branch_id: str):
    """New Tab to import data from other branches."""
    st.subheader("📥 Import Branch Daybook")

    db = next(get_db())

    # 1. Select Remote Branch
    # Fetch all branches except current one
    branches = db.query(models.Branch).filter(models.Branch.Branch_ID != current_branch_id).all()
    branch_opts = {b.Branch_Name: b.Branch_ID for b in branches}

    col1, col2, col3 = st.columns(3)
    target_branch_name = col1.selectbox("Select Branch", list(branch_opts.keys()))
    target_date = col2.date_input("Select Date", date.today())

    if col3.button("Fetch Transactions"):
        st.session_state['fetch_clicked'] = True

    # 2. Show Data
    if st.session_state.get('fetch_clicked') and target_branch_name:
        remote_bid = branch_opts[target_branch_name]

        # Get unimported transactions
        txns = cashier_logic.get_remote_branch_transactions(db, remote_bid, current_branch_id, target_date)

        if txns:
            st.write(f"Found {len(txns)} new transactions from **{target_branch_name}**.")

            # Convert to DataFrame for DataEditor (Checkbox selection)
            data = [{
                "Select": False,
                "ID": t.id,
                "Type": t.transaction_type,
                "Category": t.category,
                "Amount": t.amount,
                "Party": t.party_name,
                "Desc": t.description
            } for t in txns]

            edited_df = st.data_editor(
                pd.DataFrame(data),
                column_config={"Select": st.column_config.CheckboxColumn(required=True)},
                disabled=["ID", "Type", "Category", "Amount", "Party", "Desc"],
                hide_index=True,
                key="import_editor"
            )

            # 3. Import Button
            selected_rows = edited_df[edited_df.Select]
            if not selected_rows.empty:
                if st.button(f"Import {len(selected_rows)} Records", type="primary"):
                    ids_to_import = selected_rows["ID"].tolist()
                    success, msg = cashier_logic.import_transactions(db, ids_to_import, current_branch_id)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            st.info("No new transactions found to import.")

    db.close()

def render_daybook(branch_id: str, selected_date: date):
    """Renders the daybook view with opening/closing balances."""
    st.subheader(f"Daybook: {selected_date.strftime('%d-%b-%Y')}")

    db = next(get_db())

    # Filter Controls
    view_mode = st.radio("View Mode:", ["Cash Only", "Online/Card", "All"], horizontal=True)

    # Logic Calls
    db_filter = "Cash" if view_mode == "Cash Only" else ("Online" if view_mode == "Online/Card" else None)
    opening_bal = cashier_logic.get_opening_balance(db, branch_id, selected_date, mode=db_filter)
    transactions = cashier_logic.get_daybook_transactions(db, branch_id, selected_date)

    db.close()

    # Client-side filtering for display
    if view_mode == "Cash Only":
        transactions = [t for t in transactions if t.payment_mode == "Cash"]
    elif view_mode == "Online/Card":
        transactions = [t for t in transactions if t.payment_mode in ["Online", "Card"]]

    # Metrics Calculation
    total_credits = sum(t.amount for t in transactions if t.transaction_type == "Receipt")
    total_debits = sum(t.amount for t in transactions if t.transaction_type == "Voucher")
    closing_bal = opening_bal + total_credits - total_debits

    # Metrics Display
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Opening", f"₹{opening_bal:,.2f}")
    c2.metric("Receipts (+)", f"₹{total_credits:,.2f}")
    c3.metric("Vouchers (-)", f"₹{total_debits:,.2f}")
    c4.metric("Closing", f"₹{closing_bal:,.2f}", delta=closing_bal - opening_bal)

    # Table Display
    if transactions:
        df = pd.DataFrame([{
            "Type": t.transaction_type,
            "Category": t.category,
            "Party": t.party_name,
            "Mode": t.payment_mode,
            "Credit": t.amount if t.transaction_type == "Receipt" else 0,
            "Debit": t.amount if t.transaction_type == "Voucher" else 0,
            "Desc": t.description
        } for t in transactions])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No transactions found.")


def render_ledger(branch_id: str):
    """Renders the ledger with date range selection."""
    st.subheader("General Ledger")

    c1, c2 = st.columns(2)
    start_date = c1.date_input("Start Date", value=date.today().replace(day=1))
    end_date = c2.date_input("End Date", value=date.today())

    if st.button("Generate Ledger"):
        db = next(get_db())
        transactions = cashier_logic.get_ledger_transactions(db, branch_id, start_date, end_date)
        initial_balance = cashier_logic.get_opening_balance(db, branch_id, start_date)
        db.close()

        rows = []
        running_bal = initial_balance

        # Opening Row
        rows.append({
            "Date": start_date, "Category": "OPENING BALANCE", "Description": "-",
            "Mode": "-", "Credit": 0, "Debit": 0, "Balance": running_bal
        })

        for t in transactions:
            credit = t.amount if t.transaction_type == "Receipt" else 0
            debit = t.amount if t.transaction_type == "Voucher" else 0
            running_bal = running_bal + credit - debit

            rows.append({
                "Date": t.date,
                "Category": t.category,
                "Description": f"{t.party_name or ''} {t.description or ''}",
                "Mode": t.payment_mode,
                "Credit": credit,
                "Debit": debit,
                "Balance": running_bal
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={"Date": st.column_config.DateColumn(format="DD-MM-YYYY")}
        )