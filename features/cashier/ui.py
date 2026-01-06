import streamlit as st
import time
from datetime import date
from features.cashier import logic as cashier_logic  # Updated Import
from core.database import get_db  # Updated Import
from core import models  # Updated Import
import pandas as pd
from decimal import Decimal


# --- CACHED DC LOOKUP ---
@st.cache_data(ttl=30)
def get_cached_branch_records(branch_id: str):
    """
    Fetches sales records and converts them to a dictionary for fast lookup.
    """
    db = next(get_db())
    try:
        branch_records = cashier_logic.get_all_sales_records_by_branch(db, branch_id)

        record_map = {}
        for r in branch_records:
            label = f"{r.Customer_Name} | {r.DC_Number}"
            record_map[label] = {
                "DC_Number": r.DC_Number,
                "Customer_Name": r.Customer_Name,
                "Banker_Name": r.Banker_Name,
                "Price_Negotiated_Final": r.Price_Negotiated_Final,
                "Payment_DD": r.Payment_DD,
                "Payment_DD_Received": r.Payment_DD_Received,
                "Payment_DownPayment": r.Payment_DownPayment,
                "Model": r.Model,
                "Variant": r.Variant
            }
        return record_map
    finally:
        db.close()


def render_entry_form(branch_id: str, selected_date: date):
    st.subheader("Enter Receipt or Voucher")

    # --- 1. DC LOOKUP ---
    record_map = get_cached_branch_records(branch_id)
    options = ["None"] + list(record_map.keys())

    selected_option = st.selectbox(
        "Link to DC (Search by Name or DC Number)",
        options=options,
        index=0,
        placeholder="Type to search...",
        help="List auto-refreshes every 30 seconds"
    )

    linked_dc_number = None
    default_party = ""
    default_desc = ""
    is_dc_linked = False

    if selected_option != "None":
        sale_data = record_map[selected_option]

        # --- NEW LOGIC START ---

        # 1. Identify Sale Type
        is_cash_sale = (sale_data["Banker_Name"] == "N/A (Cash Sale)")

        # Safe Decimal Conversion
        payment_dd_expected = Decimal(str(sale_data.get('Payment_DD', 0.0) or 0.0))

        # 2. Determine "Customer Payable Target"
        if is_cash_sale:
            # Cash Sale: Customer pays the Full Price
            target_amount = Decimal(str(sale_data['Price_Negotiated_Final']))
            amount_label = "Total Sale Value"
            finance_info_str = ""  # No DD for cash sales
        else:
            # Finance Sale: Customer ONLY pays the Down Payment
            target_amount = Decimal(str(sale_data['Payment_DownPayment']))
            amount_label = "Down Payment (Customer Share)"
            finance_info_str = f"🏦 **DD Expected:** ₹{payment_dd_expected:,.2f}"

        # 3. Fetch Total Already Paid
        db_lookup = next(get_db())
        total_paid = cashier_logic.get_total_paid_for_dc(db_lookup, sale_data["DC_Number"])
        db_lookup.close()

        # 4. Calculate Actual Due
        actual_balance = target_amount - total_paid

        # --- Display Info Block ---
        linked_dc_number = sale_data["DC_Number"]
        default_party = sale_data["Customer_Name"]
        default_desc = f"Payment for {sale_data['Model']} ({sale_data['Variant']})"
        is_dc_linked = True

        st.info(f"✅ Found: **{sale_data['Customer_Name']}** | Model: {sale_data['Model']}")

        c1, c2, c3 = st.columns(3)

        # Col 1: Target Amount (varies by type) + DD Info if Finance
        with c1:
            st.markdown(f"🎯 **{amount_label}:**\n### ₹{target_amount:,.2f}")
            if not is_cash_sale:
                st.caption(finance_info_str)  # Show DD Expected under the Down Payment

        # Col 2: Total Paid
        c2.markdown(f"💵 **Total Collected:**\n### ₹{total_paid:,.2f}")

        # Col 3: Balance Status
        if actual_balance > 0:
            c3.error(f"💰 **Customer Due:**\n### ₹{actual_balance:,.2f}")
        elif actual_balance < 0:
            c3.warning(f"⚠️ **Overpaid:**\n### ₹{abs(actual_balance):,.2f}")
        else:
            c3.success("🎉 **Fully Paid**\n### ₹0.00")
    # --- Transaction Type & Category ---
    col_ctrl_1, col_ctrl_2 = st.columns(2)

    with col_ctrl_1:
        txn_type = st.radio("Type", ["Receipt", "Voucher"], horizontal=True)

    default_cat_index = 0
    if txn_type == "Receipt":
        # --- UPDATE: Added "Short Amount Receipt" ---
        category_opts = [
            "Branch Receipt", "General Receipt", "Booking Receipt", "Short Amount Receipt",
            "DD Received", "Vehicle Sale", "TA", "Accessories Sale",
            "Service", "GST Finance", "Others Vehicle Sale"
        ]

        # Add Service Sub-Categories for Non-Head Branches
        if branch_id != "1":
            category_opts.extend(["Job Card Sale", "Out Bill Sale"])

        if is_dc_linked:
            try:
                # Restrict options if DC is linked
                # Added "Short Amount Receipt" here as well
                category_opts = ["Vehicle Sale", "DD Received", "Others Vehicle Sale", "Booking Receipt",
                                 "Short Amount Receipt"]
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
                db = next(get_db())
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
                db.close()

                if success:
                    st.success(f"✅ {msg}")
                    with st.spinner("Saved! Refreshing..."):
                        time.sleep(3)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Enter valid amount")


def render_import_tab(current_branch_id: str, working_date: date):
    st.subheader(f"📥 Import Branch Daybook (Booking Date: {working_date.strftime('%d-%b-%Y')})")
    db = next(get_db())
    branches = db.query(models.Branch).filter(models.Branch.Branch_ID != current_branch_id,
                                              models.Branch.dc_gen_enabled == True).all()
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
    # 1. Prepare DB Filter (for Opening Balance)
    if view_mode == "Cash Only":
        db_filter = "Cash"
    elif view_mode == "Online/Card":
        db_filter = ["Online", "Card"]
    else:
        db_filter = None

    opening_bal = cashier_logic.get_opening_balance(db, branch_id, selected_date, mode=db_filter)
    transactions = cashier_logic.get_daybook_transactions(db, branch_id, selected_date)
    db.close()

    # 2. Filter Transactions for Display (Robust Logic)
    if view_mode == "Cash Only":
        transactions = [
            t for t in transactions
            if t.payment_mode and t.payment_mode.strip().title() == "Cash"
        ]
    elif view_mode == "Online/Card":
        transactions = [
            t for t in transactions
            if t.payment_mode and t.payment_mode.strip().title() in ["Online", "Card"]
        ]

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

        st.divider()
        st.download_button(
            label="📄 Download PDF Ledger (A4 Landscape)",
            data=pdf_buffer,
            file_name=f"Ledger_{branch_id}_{start_date}_{end_date}.pdf",
            mime="application/pdf",
            type="primary"
        )
        st.divider()

        # 2. On-Screen Display (Sorted by DC)
        # We manually sort the transactions to match the PDF view
        # Sort Key: (Is Receipt? 0=Rec 1=Vouch, DC Number (Empty last), Date)
        sorted_txns = sorted(
            transactions,
            key=lambda t: (
                0 if t.transaction_type == 'Receipt' else 1,
                str(t.dc_number) if t.dc_number else "zzzz",
                t.date
            )
        )

        rows_screen = []
        running_bal = initial_balance_cash  # Note: Running Balance visual might look jumpy due to sorting

        # Add Opening Balance Row
        rows_screen.append({
            "Date": start_date, "Ref No": "-", "Category": "OP BAL (Cash)",
            "Description": "-", "Mode": "-", "Credit": 0, "Debit": 0, "Balance": running_bal
        })

        for t in sorted_txns:
            credit = t.amount if t.transaction_type == "Receipt" else 0
            debit = t.amount if t.transaction_type == "Voucher" else 0

            # Update running balance (mathematically correct based on the *displayed* order)
            if t.payment_mode and t.payment_mode.strip() == "Cash":
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

        # Display
        tab_all, tab_receipts, tab_vouchers = st.tabs(["All Transactions (Grouped)", "Receipts", "Vouchers"])

        with tab_all:
            st.dataframe(
                df_all,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Date": st.column_config.DateColumn(format="DD-MM-YYYY"),
                    "Credit": st.column_config.NumberColumn(format="%.2f"),
                    "Debit": st.column_config.NumberColumn(format="%.2f"),
                    "Balance": st.column_config.NumberColumn(format="%.2f"),
                }
            )
        with tab_receipts:
            st.dataframe(df_all[df_all['Credit'] > 0], use_container_width=True, hide_index=True)
        with tab_vouchers:
            st.dataframe(df_all[df_all['Debit'] > 0], use_container_width=True, hide_index=True)