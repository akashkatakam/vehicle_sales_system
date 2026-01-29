import streamlit as st
import io
from datetime import datetime
from typing import Dict, Any

from core.database import db_session
from core import models
from core.data_manager import (
    get_all_branches, get_config_lists_by_branch, get_recent_records_for_reprint, get_universal_data,
    get_accessory_package_for_model, create_sales_record, log_sale,
    get_unlinked_booking_receipts, link_booking_receipts,
    create_approval_request, get_pending_approvals, update_approval_status
)
from features.sales.logic import (
    calculate_finance_fees, get_next_dc_number, generate_accessory_invoice_number,
    process_accessories_and_split, reconstruct_sales_order
)
from features.sales.order import SalesOrder
from utils import CASH_SALE_TAG, IST_TIMEZONE, format_currency

st.set_page_config(page_title="Sales DC Generator", layout="wide", initial_sidebar_state="collapsed")

# --- CONFIGURATION ---
APPROVAL_LIMIT = 1500.0
OWNER_PHONE = "9198480xxxxx"


@st.cache_data(ttl=3600)
def load_all_branches_cached():
    with db_session() as db: return get_all_branches(db)


@st.cache_data(ttl=3600)
def load_universal_data_cached():
    with db_session() as db: return get_universal_data(db)


@st.cache_data(ttl=3600)
def load_branch_config_cached(branch_id: str) -> Dict[str, Any]:
    with db_session() as db: return get_config_lists_by_branch(db, branch_id)


if 'selected_branch_id' not in st.session_state: st.session_state.selected_branch_id = None
if 'selected_branch_name' not in st.session_state: st.session_state.selected_branch_name = None


def generate_approval_link(owner_phone, customer, vehicle, discount, amount):
    msg = f"⚠️ *Approval Request* ⚠️\n\n*Customer:* {customer}\n*Vehicle:* {vehicle}\n*Discount:* ₹{discount:,.0f}\n*Final Price:* ₹{amount:,.0f}\n\nPlease approve in Dashboard."
    return f"https://wa.me/{owner_phone}?text={msg.replace(' ', '%20')}"


# --- RESET LOGIC ---
def reset_form_state():
    """Clears all form input keys and the dialog trigger from session state."""
    keys_to_clear = [
        "customer_name", "customer_phone", "customer_place", "sales_staff_selector",
        "vehicle_model_selector", "vehicle_variant_selector", "vehicle_color_selector",
        "pr_check", "double_tax_check", "ew_select", "final_cost_input",
        "booking_receipts_select", "sale_type_radio", "out_finance_check",
        "financier_selector", "custom_financier", "custom_executive",
        "banker_name_input", "finance_executive_selector", "dd_amount_input",
        "generated_pdf_info"  # Clearing this closes the dialog and prevents reopening
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]


# --- POPUP DIALOG FOR SUCCESS ---
@st.dialog("🎉 Order Finalized!")
def show_success_dialog(pdf_info):
    st.balloons()
    st.success(f"✅ DC **{pdf_info['dc_number']}** Generated Successfully!")

    st.write("The Delivery Challan has been generated.")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.download_button(
            label="⬇️ Download PDF",
            data=pdf_info['buffer'],
            file_name=pdf_info['filename'],
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key="popup_download_btn"
            # NOTE: on_click removed so form does NOT reset on download
        )

    with col2:
        # "Close" button to trigger the reset action explicitly
        if st.button("Close", type="secondary", use_container_width=True, key="popup_close_btn"):
            reset_form_state()
            st.rerun()


def BranchSelector():
    st.title("🚗 Sales DC Generator")
    all_branches = [b for b in load_all_branches_cached() if b.dc_gen_enabled]
    cols = st.columns(3)
    for i, branch in enumerate(all_branches):
        if cols[i % 3].button(branch.Branch_Name, key=branch.Branch_ID, use_container_width=True):
            st.session_state.selected_branch_id = branch.Branch_ID
            st.session_state.selected_branch_name = branch.Branch_Name
            st.rerun()


def SalesForm():
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

    # --- 1. DOWNLOAD SUCCESS AREA (POPUP) ---
    if 'generated_pdf_info' in st.session_state:
        show_success_dialog(st.session_state['generated_pdf_info'])

    # --- 2. PENDING APPROVALS (RESUME SALE) ---
    with st.expander("⏳ Pending Approvals (Resume Sale)", expanded=True):
        with db_session() as db:
            pending = get_pending_approvals(db, branch_id)

            if pending:
                for p in pending:
                    with st.container(border=True):
                        col_p1, col_p2, col_p3 = st.columns([3, 2, 2])
                        col_p1.markdown(
                            f"**{p.Customer_Name}** | {p.Model}\n\nDiscount: :red[**₹{p.Discount_Requested:,.0f}**]")

                        if p.Status == 'Pending':
                            col_p2.warning("🕒 Waiting for Owner...")
                            if col_p2.button("Check Status", key=f"chk_{p.id}"):
                                st.rerun()

                        elif p.Status == 'Approved':
                            col_p2.success("✅ Approved!")
                            if col_p3.button("🖨️ Finalize & Print", key=f"fin_{p.id}", type="primary",
                                             use_container_width=True):
                                try:
                                    # A. LOAD DATA
                                    saved_data = dict(p.Order_JSON)

                                    # B. GENERATE REAL SEQUENCES
                                    dc_number, dc_seq = get_next_dc_number(db, branch_id)

                                    branch_obj = db.query(models.Branch).get(branch_id)
                                    uni_data = get_universal_data(db)
                                    firm_master_df = uni_data['firm_master']
                                    acc_list = get_accessory_package_for_model(db, saved_data.get('Model', ''))

                                    acc_bills_data = process_accessories_and_split(
                                        saved_data.get('Model', ''), acc_list, firm_master_df, branch_obj
                                    )

                                    bill_1_seq, bill_2_seq = 0, 0
                                    for bill in acc_bills_data:
                                        inv_str, inv_seq = generate_accessory_invoice_number(db, branch_obj,
                                                                                             bill['firm_id'],
                                                                                             bill['accessory_slot'])
                                        if bill['accessory_slot'] == 1:
                                            bill_1_seq = inv_seq
                                        elif bill['accessory_slot'] == 2:
                                            bill_2_seq = inv_seq

                                    # C. UPDATE DATA
                                    saved_data['DC_Number'] = dc_number
                                    saved_data['DC_Sequence_No'] = dc_seq
                                    saved_data['Acc_Inv_1_No'] = bill_1_seq
                                    saved_data['Acc_Inv_2_No'] = bill_2_seq
                                    saved_data['Timestamp'] = datetime.now(IST_TIMEZONE)

                                    # D. INSERT
                                    real_record = create_sales_record(db, saved_data)
                                    update_approval_status(db, p.id, "Completed")
                                    log_sale(db, branch_id, real_record.Model, real_record.Variant,
                                             real_record.Paint_Color, 1,
                                             datetime.now(IST_TIMEZONE), f"Auto-logged: {dc_number}")

                                    reprint_order = reconstruct_sales_order(db, real_record.id)
                                    pdf_buffer = io.BytesIO()
                                    reprint_order.generate_pdf_challan(pdf_buffer)

                                    # G. SAVE TO SESSION
                                    st.session_state['generated_pdf_info'] = {
                                        'dc_number': dc_number,
                                        'buffer': pdf_buffer.getvalue(),
                                        'filename': f"{dc_number}.pdf"
                                    }
                                    st.rerun()

                                except Exception as e:
                                    st.error(f"Finalization Error: {str(e)}")
            else:
                st.caption("No pending approvals.")
    st.markdown("---")

    # --- REPRINT SECTION ---
    with st.expander("🔄 DC Reprint", expanded=False):
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
                            st.download_button("Download PDF", pdf_buffer,
                                               f"{selected_reprint.split(' | ')[0]}_Reprint.pdf", "application/pdf",
                                               type="primary")
                        else:
                            st.error("Could not reconstruct order data.")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("No recent records found.")

    # --- MAIN FORM LOADING ---
    branch_config = load_branch_config_cached(branch_id)
    universal_data = load_universal_data_cached()
    all_branches = load_all_branches_cached()
    pricing_adjustment = next((b.Pricing_Adjustment for b in all_branches if b.Branch_ID == branch_id), 0.0)

    vehicles_df = universal_data['vehicles']
    firm_master_df = universal_data['firm_master']

    STAFF_LIST = branch_config['staff_names']
    EXECUTIVE_LIST = branch_config['executive_names']
    FINANCIER_LIST = branch_config['financier_names'] + ['Other']
    incentive_rules = branch_config['incentive_rules']

    final_financier_name = CASH_SALE_TAG
    final_executive_name = CASH_SALE_TAG
    banker_name = ""
    dd_amount, down_payment, hp_fee_to_charge, incentive_earned = 0.0, 0.0, 0.0, 0.0

    with st.container(border=True):
        st.header("1. Customer & Staff Details")
        c1, c2 = st.columns(2)
        name = c1.text_input("Customer Name:", key="customer_name")
        phone = c2.text_input("Customer Phone Number:", key="customer_phone")
        place = st.text_input("Place/City:", key="customer_place")
        sales_staff = st.selectbox("Sales Staff:", STAFF_LIST, key="sales_staff_selector")

    with st.container(border=True):
        st.header("2. Vehicle Configuration & Pricing")
        all_models = sorted(list(set(vehicles_df['Model'].str.strip().unique())))
        c1, c2 = st.columns(2)
        selected_model = c1.selectbox("Vehicle Model:", all_models, key="vehicle_model_selector")
        avail_variants = vehicles_df[vehicles_df['Model'].str.strip() == selected_model]
        selected_variant = c2.selectbox("Variant:", avail_variants['Variant'].tolist(), key="vehicle_variant_selector")

        colors = ["N/A"]
        if not avail_variants.empty and selected_variant:
            try:
                c_str = avail_variants[avail_variants['Variant'] == selected_variant]['Color_List'].iloc[0]
                colors = [c.strip() for c in c_str.split(',')]
            except:
                pass
        selected_paint_color = st.selectbox("Paint Color:", colors, key="vehicle_color_selector")
        selected_vehicle_row = avail_variants[avail_variants['Variant'] == selected_variant]

        # Double Tax & PR Checkbox
        c3, c4, c5 = st.columns(3)
        pr_fee_checkbox = c3.checkbox("PR Fee Applicable?", key="pr_check")
        double_tax_checkbox = c4.checkbox("Double Tax Collected?", key="double_tax_check")
        ew_selection = c5.selectbox("Extended Warranty:", ["None", "3+1", "3+2", "3+3"], key="ew_select")

        listed_price = (selected_vehicle_row['FINAL_PRICE'].iloc[
                            0] + pricing_adjustment) if not selected_vehicle_row.empty else 0.0
        st.info(f"Listed Price: **{format_currency(listed_price)}**")

        c5, c6 = st.columns(2)
        final_cost_by_staff = c5.number_input("Final Cost (after discount):", value=float(listed_price), step=100.0,
                                              key="final_cost_input")
        discount = listed_price - final_cost_by_staff
        if discount > 0:
            c6.success(f"Discount: **{format_currency(discount)}**")
        elif discount < 0:
            c6.warning(f"Markup: {format_currency(abs(discount))}")

    with st.container(border=True):
        st.header("3. Payment & Financing")

        linked_total = 0.0
        selected_receipt_ids = []

        with db_session() as db:
            unlinked_receipts = get_unlinked_booking_receipts(db, branch_id)

        if unlinked_receipts:
            receipt_options = {
                f"{r.party_name} | {format_currency(r.amount)} | {r.date.strftime('%d-%m')}": r
                for r in unlinked_receipts
            }

            selected_keys = st.multiselect(
                "🔗 Link Existing Booking Receipts (Optional):",
                options=list(receipt_options.keys()),
                help="Select booking receipts already paid by this customer.",
                key="booking_receipts_select"
            )

            for key in selected_keys:
                r = receipt_options[key]
                linked_total += float(r.amount)
                selected_receipt_ids.append(r.id)

            if linked_total > 0:
                st.info(f"✅ **Linked Amount:** {format_currency(linked_total)} (This will be recorded as 'Received')")
        else:
            st.caption("No unlinked booking receipts found for this branch.")

        sale_type = st.radio("Sale Type:", ["Cash", "Finance"], horizontal=True, key="sale_type_radio")

        if sale_type == "Finance":
            out_finance_flag = st.checkbox("Check if Out Finance:", key="out_finance_check")
            financier_selection = st.selectbox("Financier Company:", FINANCIER_LIST, key="financier_selector")

            if financier_selection == "Other" and out_finance_flag:
                st.markdown("---")
                final_financier_name = st.text_input("Custom Finance Company:", key="custom_financier")
                final_executive_name = st.text_input("Custom Executive Name:", key="custom_executive")
            elif financier_selection == 'Bank':
                banker_name = st.text_input("Banker's Name:", key="banker_name_input")
                final_financier_name = banker_name
            else:
                final_financier_name = financier_selection
                final_executive_name = st.selectbox("Executive Name:", EXECUTIVE_LIST, key="finance_executive_selector")

            dd_val = linked_total if linked_total > 0 else 0.0
            dd_amount = st.number_input("DD / Booking Amount (Expected):", min_value=0.0, step=100.0, value=dd_val,
                                        key="dd_amount_input")

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

    st.markdown("---")

    # --- DECISION LOGIC: APPROVAL OR GENERATE ---
    requires_approval = discount > APPROVAL_LIMIT

    row = selected_vehicle_row.iloc[0]
    order = SalesOrder(
        name, place, phone, row.to_dict(), final_cost_by_staff, sales_staff,
        final_financier_name, final_executive_name, selected_paint_color,
        hp_fee_to_charge, incentive_earned, banker_name, "TEMP",
        branch_name, [], branch_id,
        pr_fee_checkbox, ew_selection,
        float(row['ACCESSORIES']), float(row['HC']),
        float(row['EW_3_1']) if ew_selection != "None" else 0.0,
        float(row['PR_CHARGES']) if pr_fee_checkbox else 0.0,
        double_tax_checkbox
    )
    if sale_type == "Finance": order.set_finance_details(dd_amount, down_payment)

    if requires_approval:
        st.warning(
            f"⚠️ **High Discount Warning**: {format_currency(discount)} exceeds limit of {format_currency(APPROVAL_LIMIT)}.")
        st.info("This transaction requires Owner Approval. Request will be sent to the Owner's dashboard.")

        col_app1, col_app2 = st.columns(2)

        if col_app1.button("📨 Submit for Approval", type="primary", use_container_width=True):
            if not name or not phone:
                st.error("Missing Customer Name or Phone.")
                return

            with db_session() as db:
                try:
                    record_data = order.get_data_for_export(0, 0, 0)
                    if linked_total > 0:
                        record_data['Payment_DD_Received'] = linked_total

                    create_approval_request(db, record_data, branch_id)
                    st.success("Request Submitted Successfully!")

                    wa_link = generate_approval_link(OWNER_PHONE, name, f"{selected_model} {selected_variant}",
                                                     discount, final_cost_by_staff)
                    st.link_button("📲 Notify Owner on WhatsApp", wa_link)

                except Exception as e:
                    st.error(f"Request failed: {e}")

    else:
        # STANDARD GENERATION (DIRECT)
        if st.button("GENERATE DUAL-FIRM BILLS", type="primary", use_container_width=True):
            if not name or not phone:
                st.error("Missing Customer Name or Phone.")
                return

            with db_session() as db:
                try:
                    dc_number, dc_seq_no = get_next_dc_number(db, branch_id)
                    order.dc_number = dc_number

                    branch_obj = db.query(models.Branch).get(branch_id)
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

                    order.accessory_bills = [b for b in acc_bills_data if b['grand_total'] > 0]
                    record_data = order.get_data_for_export(dc_seq_no, bill_1_seq, bill_2_seq)

                    if linked_total > 0:
                        record_data['Payment_DD_Received'] = linked_total

                    create_sales_record(db, record_data)

                    if selected_receipt_ids:
                        link_booking_receipts(db, dc_number, selected_receipt_ids)

                    log_sale(db, branch_id, selected_model, row['Variant'], selected_paint_color, 1,
                             datetime.now(IST_TIMEZONE), f"Auto-logged: {dc_number}")

                    pdf_buffer = io.BytesIO()
                    order.generate_pdf_challan(pdf_buffer)

                    # Direct Download (No need for session state loop here usually, but consistent behavior is fine)
                    st.session_state['generated_pdf_info'] = {
                        'dc_number': dc_number,
                        'buffer': pdf_buffer.getvalue(),
                        'filename': f"{dc_number}.pdf"
                    }
                    st.rerun()

                except Exception as e:
                    st.error(f"Transaction failed: {e}")


def main():
    if st.session_state.selected_branch_id is None:
        BranchSelector()
    else:
        SalesForm()


if __name__ == "__main__":
    main()