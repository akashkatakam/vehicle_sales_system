import streamlit as st
import io
from datetime import datetime
from typing import Dict, Any

# --- New Imports based on Refactoring ---
from core.database import get_db, db_session
from core import models
from core.data_manager import (
    get_all_branches, get_config_lists_by_branch, get_recent_records_for_reprint, get_universal_data,
    get_accessory_package_for_model, create_sales_record, log_sale
)
from features.sales.logic import (
    calculate_finance_fees, get_next_dc_number, generate_accessory_invoice_number,
    process_accessories_and_split, reconstruct_sales_order
)
from features.sales.order import SalesOrder
from utils import CASH_SALE_TAG, IST_TIMEZONE, format_currency

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sales DC Generator",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# --- 2. DATA LOADING & CACHING ---
# Using db_session context manager for cleaner resource handling

@st.cache_data(ttl=3600)
def load_all_branches_cached():
    """Loads all branches from the DB. Cached for 1 hour."""
    with db_session() as db:
        return get_all_branches(db)


@st.cache_data(ttl=3600)
def load_universal_data_cached():
    """Loads universal data (Vehicles, Firms). Cached for 1 hour."""
    with db_session() as db:
        return get_universal_data(db)


@st.cache_data(ttl=3600)
def load_branch_config_cached(branch_id: str) -> Dict[str, Any]:
    """Loads branch-specific config (Staff, Execs, Financiers). Cached per branch_id."""
    with db_session() as db:
        return get_config_lists_by_branch(db, branch_id)


# --- 3. SESSION STATE INITIALIZATION ---
if 'selected_branch_id' not in st.session_state:
    st.session_state.selected_branch_id = None
if 'selected_branch_name' not in st.session_state:
    st.session_state.selected_branch_name = None


# --- 4. UI COMPONENTS ---

def BranchSelector():
    """
    Renders a full-page, centered grid of buttons for branch selection.
    """
    st.title("🚗 Welcome to the Sales DC Generator")
    st.subheader("Please select your branch to begin:")

    all_branches = load_all_branches_cached()
    if not all_branches:
        st.error("FATAL: No branches found. Please seed the database.")
        return

    # Filter for enabled branches
    active_branches = [b for b in all_branches if b.dc_gen_enabled]

    cols = st.columns(3)
    for i, branch in enumerate(active_branches):
        if cols[i % 3].button(branch.Branch_Name, key=branch.Branch_ID, use_container_width=True):
            st.session_state.selected_branch_id = branch.Branch_ID
            st.session_state.selected_branch_name = branch.Branch_Name
            st.rerun()


def SalesForm():
    """
    Renders the complete sales form for the selected branch.
    """
    branch_id = st.session_state.selected_branch_id
    branch_name = st.session_state.selected_branch_name

    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"Delivery Challan: {branch_name}")
    with col2:
        if st.button("Change Branch", use_container_width=True):
            st.session_state.selected_branch_id = None
            st.session_state.selected_branch_name = None
            st.rerun()
    st.markdown("---")

    # --- DC Reprint Section ---
    with st.expander("🔄 DC Reprint", expanded=False):
        st.info("Select a recent DC from this branch to download the PDF again.")

        with db_session() as db:
            recent_recs = get_recent_records_for_reprint(db, branch_id)

            if recent_recs:
                reprint_options = {f"{r.DC_Number} | {r.Customer_Name}": r.id for r in recent_recs}
                selected_reprint = st.selectbox("Select Record:", list(reprint_options.keys()))

                if st.button("Generate PDF Copy", type="secondary"):
                    try:
                        rec_id = reprint_options[selected_reprint]
                        reprint_order = reconstruct_sales_order(db, rec_id)
                        if reprint_order:
                            pdf_buffer = io.BytesIO()
                            reprint_order.generate_pdf_challan(pdf_buffer)
                            pdf_buffer.seek(0)
                            st.download_button(
                                label="Download PDF Now",
                                data=pdf_buffer,
                                file_name=f"{selected_reprint.split(' | ')[0]}_Reprint.pdf",
                                mime="application/pdf",
                                type="primary"
                            )
                        else:
                            st.error("Could not reconstruct order data.")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("No recent records found for this branch.")

    # --- Load Data ---
    branch_config = load_branch_config_cached(branch_id)
    universal_data = load_universal_data_cached()

    # Get Pricing Adjustment
    all_branches = load_all_branches_cached()
    pricing_adjustment = next((b.Pricing_Adjustment for b in all_branches if b.Branch_ID == branch_id), 0.0)

    vehicles_df = universal_data['vehicles']
    firm_master_df = universal_data['firm_master']

    STAFF_LIST = branch_config['staff_names']
    EXECUTIVE_LIST = branch_config['executive_names']
    FINANCIER_LIST = branch_config['financier_names'] + ['Other']
    incentive_rules = branch_config['incentive_rules']

    # --- Initialize Variables ---
    final_financier_name = CASH_SALE_TAG
    final_executive_name = CASH_SALE_TAG
    banker_name = ""
    dd_amount, down_payment, hp_fee_to_charge, incentive_earned = 0.0, 0.0, 0.0, 0.0

    # --- Render Form ---
    with st.container(border=True):
        st.header("1. Customer & Staff Details")
        c1, c2 = st.columns(2)
        name = c1.text_input("Customer Name:", key="customer_name")
        phone = c2.text_input("Customer Phone Number:", key="customer_phone")
        place = st.text_input("Place/City:")
        sales_staff = st.selectbox("Sales Staff:", STAFF_LIST)

    with st.container(border=True):
        st.header("2. Vehicle Configuration & Pricing")

        all_models = sorted(list(set(vehicles_df['Model'].str.strip().unique())))
        c1, c2 = st.columns(2)
        selected_model = c1.selectbox("Vehicle Model:", all_models)

        avail_variants = vehicles_df[vehicles_df['Model'].str.strip() == selected_model]
        selected_variant = c2.selectbox("Variant:", avail_variants['Variant'].tolist())

        colors = ["N/A"]
        if not avail_variants.empty and selected_variant:
            try:
                c_str = avail_variants[avail_variants['Variant'] == selected_variant]['Color_List'].iloc[0]
                colors = [c.strip() for c in c_str.split(',')]
            except:
                pass

        selected_paint_color = st.selectbox("Paint Color:", colors)
        selected_vehicle_row = avail_variants[avail_variants['Variant'] == selected_variant]

        c3, c4 = st.columns(2)
        pr_fee_checkbox = c3.checkbox("PR Fee Applicable?")
        ew_selection = c4.selectbox("Extended Warranty:", ["None", "3+1", "3+2", "3+3"])

        if selected_vehicle_row.empty:
            st.error("Price data not found.")
            listed_price = 0.0
        else:
            listed_price = selected_vehicle_row['FINAL_PRICE'].iloc[0] + pricing_adjustment
            st.info(f"Listed Price: **{format_currency(listed_price)}**")

        c5, c6 = st.columns(2)
        final_cost_by_staff = c5.number_input("Final Cost (after discount):", value=float(listed_price), step=100.0)
        discount = listed_price - final_cost_by_staff

        if discount > 0:
            c6.success(f"Discount: **{format_currency(discount)}**")
        elif discount < 0:
            c6.warning(f"Markup: {format_currency(abs(discount))}")

    with st.container(border=True):
        st.header("3. Payment & Financing")
        sale_type = st.radio("Sale Type:", ["Cash", "Finance"], horizontal=True)

        if sale_type == "Finance":
            out_finance_flag = st.checkbox("Check if Out Finance:")
            financier_selection = st.selectbox("Financier Company:", FINANCIER_LIST)

            if financier_selection == "Other" and out_finance_flag:
                st.markdown("---")
                final_financier_name = st.text_input("Custom Finance Company:")
                final_executive_name = st.text_input("Custom Executive Name:")
                st.markdown("---")
            elif financier_selection == 'Bank':
                banker_name = st.text_input("Banker's Name:")
                final_financier_name = banker_name
            else:
                final_financier_name = financier_selection
                final_executive_name = st.selectbox("Executive Name:", EXECUTIVE_LIST)

            dd_amount = st.number_input("DD / Booking Amount:", min_value=0.0, step=100.0)

            hp_fee_to_charge, incentive_earned = calculate_finance_fees(
                financier_selection, dd_amount, out_finance_flag, incentive_rules
            )

            total_obligation = final_cost_by_staff + hp_fee_to_charge + incentive_earned
            down_payment = max(0.0, total_obligation - dd_amount)

            c_hp, c_inc = st.columns(2)
            c_hp.metric("HP Fee", format_currency(hp_fee_to_charge))
            c_inc.metric("Incentive", format_currency(incentive_earned))

            st.info(f"Total Customer Obligation: **{format_currency(total_obligation)}**")
            st.success(f"Required Down Payment: **{format_currency(down_payment)}**")
        else:
            st.success(f"Total Cash Due: **{format_currency(final_cost_by_staff)}**")

    # --- Generate PDF ---
    st.markdown("---")
    if st.button("GENERATE DUAL-FIRM BILLS", type="primary", use_container_width=True):
        if not name or not phone:
            st.error("Missing Customer Name or Phone.")
            return

        with db_session() as db:
            try:
                dc_number, dc_seq_no = get_next_dc_number(db, branch_id)
                branch_obj = db.query(models.Branch).get(branch_id)

                # Accessories
                acc_list = get_accessory_package_for_model(db, selected_model)
                acc_bills_data = process_accessories_and_split(selected_model, acc_list, firm_master_df, branch_obj)

                bill_1_seq, bill_2_seq = 0, 0
                for bill in acc_bills_data:
                    inv_str, inv_seq = generate_accessory_invoice_number(db, branch_obj, bill['firm_id'],
                                                                         bill['accessory_slot'])
                    bill['Invoice_No'] = inv_str
                    bill['Acc_Inv_Seq'] = inv_seq
                    if bill['accessory_slot'] == 1:
                        bill_1_seq = inv_seq
                    elif bill['accessory_slot'] == 2:
                        bill_2_seq = inv_seq

                # Pricing Components
                row = selected_vehicle_row.iloc[0]

                order = SalesOrder(
                    name, place, phone, row.to_dict(), final_cost_by_staff, sales_staff,
                    final_financier_name, final_executive_name, selected_paint_color,
                    hp_fee_to_charge, incentive_earned, banker_name, dc_number,
                    branch_name, [b for b in acc_bills_data if b['grand_total'] > 0], branch_id,
                    pr_fee_checkbox, ew_selection,
                    float(row['ACCESSORIES']), float(row['HC']),
                    float(row['EW_3_1']) if ew_selection != "None" else 0.0,
                    float(row['PR_CHARGES']) if pr_fee_checkbox else 0.0
                )

                if sale_type == "Finance":
                    order.set_finance_details(dd_amount, down_payment)

                # Save & Log
                create_sales_record(db, order.get_data_for_export(dc_seq_no, bill_1_seq, bill_2_seq))
                log_sale(db, branch_id, selected_model, row['Variant'], selected_paint_color, 1,
                         datetime.now(IST_TIMEZONE), f"Auto-logged: {dc_number}")

                # PDF Download
                pdf_buffer = io.BytesIO()
                order.generate_pdf_challan(pdf_buffer)
                pdf_buffer.seek(0)
                st.download_button("Download DC (PDF)", pdf_buffer, f"{dc_number}_{name}.pdf", "application/pdf")
                st.success(f"{dc_number} Generated Successfully!")
                st.balloons()

            except Exception as e:
                st.error(f"Transaction failed: {e}")


def main():
    if st.session_state.selected_branch_id is None:
        BranchSelector()
    else:
        SalesForm()


if __name__ == "__main__":
    main()