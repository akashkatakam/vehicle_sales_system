# cashier_ui.py

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
    branch_records = cashier_logic.get_all_sales_records_by_branch(db, branch_id)
    record_map = {f"{r.Customer_Name} | {r.DC_Number}": r for r in branch_records}
    options = ["None"] + list(record_map.keys())

    selected_option = st.selectbox(
        "Link to DC (Search by Name or DC Number)",
        options=options,
        index=0,
        placeholder="Type to search..."
    )

    linked_dc_number = None
    default_party = ""
    default_desc = ""
    is_dc_linked = False

    if selected_option != "None":
        sale_rec = record_map[selected_option]
        is_cash_sale = (sale_rec.Banker_Name == "N/A (Cash Sale)")

        if is_cash_sale:
            info_str = f"Total Sale Value: **₹{sale_rec.Price_Negotiated_Final:,.2f}**"
        else:
            dd_exp = sale_rec.Payment_DD or 0
            dd_rec = sale_rec.Payment_DD_Received or 0
            dd_due = dd_exp - dd_rec
            info_str = (
                f"Down Payment Due: **₹{sale_rec.Payment_DownPayment:,.2f}** | "
                f"DD Amount Due: **₹{dd_due:,.2f}**"
            )

        st.info(f"✅ Found: **{sale_rec.Customer_Name}** | Model: {sale_rec.Model} | {info_str}")
        linked_dc_number = sale_rec.DC_Number
        default_party = sale_rec.Customer_Name
        default_desc = f"Payment for {sale_rec.Model} ({sale_rec.Variant})"
        is_dc_linked = True

    # --- Transaction Type & Category ---
    col_ctrl_1, col_ctrl_2 = st.columns(2)

    with col_ctrl_1:
        txn_type = st.radio("Type", ["Receipt", "Voucher"], horizontal=True)

    default_cat_index = 0
    if txn_type == "Receipt":
        category_opts = [
            "DD Received", "Vehicle Sale", "TA", "Accessories Sale",
            "Service", "GST Finance", "Others Vehicle Sale"
        ]
        if is_dc_linked:
            try:
                default_cat_index = category_opts.index("Vehicle Sale")
            except ValueError:
                default_cat_index = 0
    else:
        category_opts = [
            "General Expenses", "Petrol", "Godown to Honda Transport",
            "Sadar", "Staff Vouchers", "Bank Deposit",
            "Ayodhya", "Service Branch", "General"
        ]

    with col_ctrl_2:
        category = st.selectbox("Category", category_opts, index=default_cat_index, key=f"cat_{txn_type}")

    # --- ENTRY FORM ---
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            party_name = st.text_input("Party / Source Name", value=default_party)

            generate_receipt_no = True
            is_expense = False

            if txn_type == "Receipt":
                is_expense = False
                no_receipt_no_cats = ["Accessories Sale", "Service", "GST Finance", "Others Vehicle Sale"]
                default_chk_val = False if category in no_receipt_no_cats else True
                generate_receipt_no = st.checkbox(
                    "Generate Receipt Number", value=default_chk_val, key=f"chk_rcpt_{category}"
                )
            else:
                default_exp_val = False if category == "Bank Deposit" else True
                is_expense = st.checkbox(
                    "Book as Actual Expense", value=default_exp_val, key=f"chk_exp_{category}"
                )

        with col2:
            mode = st.selectbox("Payment Mode", ["Cash", "Online", "Card"])
            amount = st.number_input("Amount (₹)", min_value=0.0, step=100.0)
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
                    "dc_number": linked_dc_number,
                    "generate_receipt_no": generate_receipt_no,
                    "is_expense": is_expense
                }
                success, msg = cashier_logic.add_transaction(db, data)
                if success:
                    st.success(f"{msg}")
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Enter valid amount")
    db.close()


def render_import_tab(current_branch_id: str, working_date: date):
    st.subheader(f"📥 Import Branch Daybook (Booking Date: {working_date.strftime('%d-%b-%Y')})")
    db = next(get_db())
    branches = db.query(models.Branch).filter(models.Branch.Branch_ID != current_branch_id).all()
    branch_opts = {b.Branch_Name: b.Branch_ID for b in branches}

    col1, col2, col3 = st.columns(3)
    target_branch_name = col1.selectbox("Select Remote Branch", list(branch_opts.keys()))
    source_date = col2.date_input("Select Source Date", date.today())

    if col3.button("Fetch Transactions"):
        st.session_state['fetch_clicked'] = True
        st.session_state['import_select_all'] = False

    if st.session_state.get('fetch_clicked') and target_branch_name:
        remote_bid = branch_opts[target_branch_name]
        txns = cashier_logic.get_remote_branch_transactions(db, remote_bid, current_branch_id, source_date)

        if txns:
            st.write(f"Found {len(txns)} new transactions from **{target_branch_name}** on {source_date}.")
            select_all = st.checkbox("Select All", key="import_select_all")

            data = [{
                "Select": select_all,
                "ID": t.id,
                "Type": t.transaction_type,
                "Category": t.category,
                "Amount": t.amount,
                "Party": t.party_name,
                "Desc": t.description,
                "Ref No": t.receipt_number if t.transaction_type == 'Receipt' else t.voucher_number
            } for t in txns]

            edited_df = st.data_editor(
                pd.DataFrame(data),
                column_config={"Select": st.column_config.CheckboxColumn(required=True)},
                disabled=["ID", "Type", "Category", "Amount", "Party", "Desc", "Ref No"],
                hide_index=True,
                key=f"import_editor_{select_all}"
            )

            if not edited_df[edited_df.Select].empty:
                if st.button(f"Import {len(edited_df[edited_df.Select])} Records", type="primary"):
                    ids_to_import = edited_df[edited_df.Select]["ID"].tolist()
                    success, msg = cashier_logic.import_transactions(
                        db, ids_to_import, current_branch_id, working_date
                    )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            st.info(f"No new transactions found from {target_branch_name} on {source_date}.")
    db.close()


def render_daybook(branch_id: str, selected_date: date):
    st.subheader(f"Daybook: {selected_date.strftime('%d-%b-%Y')}")
    db = next(get_db())
    view_mode = st.radio("View Mode:", ["Cash Only", "Online/Card", "All"], horizontal=True)
    db_filter = "Cash" if view_mode == "Cash Only" else ("Online" if view_mode == "Online/Card" else None)
    opening_bal = cashier_logic.get_opening_balance(db, branch_id, selected_date, mode=db_filter)
    transactions = cashier_logic.get_daybook_transactions(db, branch_id, selected_date)
    db.close()

    if view_mode == "Cash Only":
        transactions = [t for t in transactions if t.payment_mode == "Cash"]
    elif view_mode == "Online/Card":
        transactions = [t for t in transactions if t.payment_mode in ["Online", "Card"]]

    total_credits = sum(t.amount for t in transactions if t.transaction_type == "Receipt")
    total_debits = sum(t.amount for t in transactions if t.transaction_type == "Voucher")
    actual_expenses = sum(
        t.amount for t in transactions if t.transaction_type == "Voucher" and t.is_expense is not False)
    closing_bal = opening_bal + total_credits - total_debits

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Opening", f"₹{opening_bal:,.2f}")
    c2.metric("Receipts (+)", f"₹{total_credits:,.2f}")
    c3.metric("Vouchers (-)", f"₹{total_debits:,.2f}", help=f"Actual Expenses: ₹{actual_expenses:,.2f}")
    c4.metric("Closing", f"₹{closing_bal:,.2f}", delta=closing_bal - opening_bal)

    if transactions:
        df = pd.DataFrame([{
            "Ref No": t.receipt_number if t.transaction_type == 'Receipt' else (
                t.voucher_number if t.transaction_type == 'Voucher' else '-'),
            "Type": t.transaction_type,
            "Category": t.category,
            "Party": t.party_name,
            "Mode": t.payment_mode,
            "Credit": t.amount if t.transaction_type == "Receipt" else 0,
            "Debit": t.amount if t.transaction_type == "Voucher" else 0,
            "Exp?": "✅" if (t.transaction_type == "Voucher" and t.is_expense is not False) else (
                "❌" if t.transaction_type == "Voucher" else "-"),
            "Desc": t.description
        } for t in transactions])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No transactions found.")


def render_ledger(branch_id: str):
    """Renders the ledger with PDF generation."""
    st.subheader("General Ledger")

    c1, c2 = st.columns(2)
    start_date = c1.date_input("Start Date", value=date.today().replace(day=1))
    end_date = c2.date_input("End Date", value=date.today())

    if st.button("Generate Ledger"):
        db = next(get_db())
        transactions = cashier_logic.get_ledger_transactions(db, branch_id, start_date, end_date)
        initial_balance_cash = cashier_logic.get_opening_balance(db, branch_id, start_date, mode="Cash")
        db.close()

        # 1. Generate PDF (Logic moved to cashier_logic)
        pdf_buffer = cashier_logic.generate_pdf_ledger(
            branch_id, start_date, end_date, initial_balance_cash, transactions
        )

        # 2. Download Button
        st.divider()
        st.download_button(
            label="📄 Download PDF Ledger (A4 Landscape)",
            data=pdf_buffer,
            file_name=f"Ledger_{branch_id}_{start_date}_{end_date}.pdf",
            mime="application/pdf",
            type="primary"
        )
        st.divider()

        # 3. On-Screen Display
        rows_screen = []
        running_bal = initial_balance_cash
        rows_screen.append({
            "Date": start_date, "Ref No": "-", "Category": "OP BAL (Cash)",
            "Description": "-", "Mode": "-", "Credit": 0, "Debit": 0, "Balance": running_bal
        })

        for t in transactions:
            credit = t.amount if t.transaction_type == "Receipt" else 0
            debit = t.amount if t.transaction_type == "Voucher" else 0
            if t.payment_mode == "Cash":
                running_bal = running_bal + credit - debit

            ref_no = t.receipt_number if t.transaction_type == 'Receipt' else (
                t.voucher_number if t.transaction_type == 'Voucher' else '-')
            desc_text = f"{t.party_name or ''} {t.description or ''}".strip()
            if t.dc_number: desc_text = f"(DC: {t.dc_number}) {desc_text}"

            rows_screen.append({
                "Date": t.date, "Ref No": ref_no, "Category": t.category,
                "Description": desc_text, "Mode": t.payment_mode,
                "Credit": credit, "Debit": debit, "Balance": running_bal
            })

        df_all = pd.DataFrame(rows_screen)
        tab_all, tab_receipts, tab_vouchers = st.tabs(["All Transactions", "Receipts", "Vouchers"])

        with tab_all:
            st.dataframe(df_all, use_container_width=True, hide_index=True,
                         column_config={"Date": st.column_config.DateColumn(format="DD-MM-YYYY")})
        with tab_receipts:
            st.dataframe(df_all[df_all['Credit'] > 0], use_container_width=True, hide_index=True)
        with tab_vouchers:
            st.dataframe(df_all[df_all['Debit'] > 0], use_container_width=True, hide_index=True)