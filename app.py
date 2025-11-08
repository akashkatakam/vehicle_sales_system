import streamlit as st
import pandas as pd
import io
from typing import Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

# --- Local Module Imports ---
from database import get_db, Base, engine
import models
from data_manager import (
    get_all_branches, get_config_lists_by_branch, get_universal_data,
    get_accessory_package_for_model, create_sales_record, log_sale
)
from data_logic import (
    calculate_finance_fees, get_next_dc_number, generate_accessory_invoice_number,
    process_accessories_and_split,
    HP_FEE_DEFAULT, HP_FEE_BANK_QUOTATION
)
from order import IST_TIMEZONE, SalesOrder

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sales DC Generator",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- 2. DATA LOADING & CACHING ---
@st.cache_data(ttl=3600)
def load_all_branches():
    """Loads all branches from the DB. Cached for 1 hour."""
    print("CACHE MISS: Loading all branches...")
    db = next(get_db())
    try:
        return get_all_branches(db)
    finally:
        db.close()

@st.cache_data(ttl=3600)
def load_universal_data():
    """Loads universal data (Vehicles, Firms). Cached for 1 hour."""
    print("CACHE MISS: Loading universal data (Vehicles, Firms)...")
    db = next(get_db())
    try:
        return get_universal_data(db)
    finally:
        db.close()

@st.cache_data(ttl=3600)
def load_branch_config(branch_id: str) -> Dict[str, Any]:
    """Loads branch-specific config (Staff, Execs, Financiers). Cached per branch_id."""
    print(f"CACHE MISS: Loading config for Branch ID: {branch_id}...")
    db = next(get_db())
    try:
        return get_config_lists_by_branch(db, branch_id)
    finally:
        db.close()

# --- 3. SESSION STATE INITIALIZATION ---
if 'selected_branch_id' not in st.session_state:
    st.session_state.selected_branch_id = None
if 'selected_branch_name' not in st.session_state:
    st.session_state.selected_branch_name = None

# --- 4. UI COMPONENTS ---

def BranchSelector():
    """
    Renders a full-page, centered grid of buttons for branch selection.
    This is the *only* thing shown on first load.
    """
    st.title("🚗 Welcome to the Sales DC Generator")
    st.subheader("Please select your branch to begin:")
    
    all_branches = load_all_branches()
    if not all_branches:
        st.error("FATAL: No branches found in the database. Please seed the 'branches' table.")
        return
    
    all_branches = [b for b in all_branches if b.dc_gen_enabled]

    # Create a responsive grid of buttons
    cols = st.columns(3) # 4 columns for a wider, cleaner look
    for i, branch in enumerate(all_branches):
        if cols[i % 3].button(branch.Branch_Name, key=branch.Branch_ID, use_container_width=True):
            # When a branch is clicked, save it to the session and rerun
            st.session_state.selected_branch_id = branch.Branch_ID
            st.session_state.selected_branch_name = branch.Branch_Name
            st.rerun()

def SalesForm():
    """
    Renders the complete sales form for the selected branch.
    This function is called *after* a branch is selected.
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
    # --- A. Load Branch Data --- 
    # Load data (will be pulled from cache)
    branch_config = load_branch_config(branch_id)
    universal_data = load_universal_data()
    pricing_adjustment = 0.0 # Default
    for branch in load_all_branches():
        if branch.Branch_ID == branch_id:
            pricing_adjustment = branch.Pricing_Adjustment
            break
    
    vehicles_df = universal_data['vehicles']
    firm_master_df = universal_data['firm_master']
    
    STAFF_LIST = branch_config['staff_names']
    EXECUTIVE_LIST = branch_config['executive_names']
    # Add "Other" to the financier list for the dropdown
    FINANCIER_LIST = branch_config['financier_names'] + ['Other']
    incentive_rules = branch_config['incentive_rules']

    # --- B. Initialize Form Variables ---
    # These variables will hold the *final* values passed to the SalesOrder
    final_financier_name_for_order = "N/A (Cash Sale)"
    final_executive_name_for_order = "N/A (Cash Sale)"
    banker_name = ""
    dd_amount = 0.0
    down_payment = 0.0
    hp_fee_to_charge = 0.0
    incentive_earned = 0.0

    # --- C. Render Form ---
    
    # --- 1. Customer & Staff Container ---
    with st.container(border=True):
        st.header("1. Customer & Staff Details")
        col_name, col_phone = st.columns(2)
        name = col_name.text_input("Customer Name:")
        phone = col_phone.text_input("Customer Phone Number:")
        
        place = st.text_input("Place/City:")
        sales_staff = st.selectbox("Sales Staff:", STAFF_LIST) 

    # --- 2. Vehicle Selection & Configuration Container ---
    with st.container(border=True):
        st.header("2. Vehicle Configuration & Pricing")
        
        all_models = sorted(list(set(vehicles_df['Model'].str.strip().unique())))
        col_model, col_variant = st.columns(2)
        
        selected_model = col_model.selectbox("Vehicle Model:", all_models)

        available_variants_df = vehicles_df[vehicles_df['Model'].str.strip() == selected_model]
        variant_options = available_variants_df['Variant'].tolist()
        
        selected_variant = col_variant.selectbox("Variant/Trim Level:", variant_options)

        colors = ["N/A"]
        if selected_variant:
            try:
                color_str = available_variants_df[available_variants_df['Variant'] == selected_variant]['Color_List'].iloc[0]
                colors = [c.strip() for c in color_str.split(',')]
            except Exception: pass
        selected_paint_color = st.selectbox("Paint Color:", colors)
        
        selected_vehicle_row = available_variants_df[available_variants_df['Variant'] == selected_variant]
        
        col_pr, col_ew = st.columns(2)
        
        with col_pr:
            # Checkbox now just tracks if it's applicable
            pr_fee_checkbox = st.checkbox("PR Fee Applicable?")
        
        with col_ew:
            ew_options = ["None", "3+1", "3+2", "3+3"]
            ew_selection = st.selectbox("Extended Warranty:", ew_options)

        if selected_vehicle_row.empty:
            st.error("Could not find price data.")
            listed_price = 0.0
        else:
            listed_price = selected_vehicle_row['FINAL_PRICE'].iloc[0] + pricing_adjustment
            st.info(f"Listed Price (Final Price): **₹{listed_price:,.2f}**")

        # Negotiation
        col_final_cost, col_discount_info = st.columns(2)
        final_cost_by_staff = col_final_cost.number_input(
            "Final Vehicle Cost (after discount):", 
            min_value=0.0, value=float(listed_price), step=100.0, format="%.2f"
        )
        
        discount_amount = listed_price - final_cost_by_staff
        with col_discount_info:
            if discount_amount > 0: st.success(f"Discount: **₹{discount_amount:,.2f}**")
            elif discount_amount < 0: st.warning(f"Markup: ₹{abs(discount_amount):,.2f}")

    # --- 3. PAYMENT & FINANCE CONTAINER ---
    with st.container(border=True):
        st.header("3. Payment & Financing")
        
        sale_type = st.radio("Sale Type:", ["Cash", "Finance"], horizontal=True)

        if sale_type == "Finance":
            
            with st.expander("Financing Source & Executive", expanded=True):
                st.markdown("##### Financier Source")
                out_finance_flag = st.checkbox("Check if **Out Finance** (External):")
                
                # The selected value from the dropdown
                financier_name_selection = st.selectbox("Financier Company:", FINANCIER_LIST)

                # --- NEW: Conditional Placeholders ---
                if financier_name_selection == "Other" and out_finance_flag:
                    st.markdown("---")
                    st.subheader("Enter Financier Details")
                    
                    # Placeholder 1: Custom Company Name
                    custom_financier_name = st.text_input("Finance Company Name:")
                    
                    # Placeholder 2: Custom Executive Name
                    custom_executive_name = st.text_input("Finance Executive Name:")
                    
                    # Set the final names to the custom inputs
                    final_financier_name_for_order = custom_financier_name
                    final_executive_name_for_order = custom_executive_name
                    st.markdown("---")
                
                elif financier_name_selection == 'Bank':
                    banker_name = st.text_input("Banker's Name (for tracking quote):")
                    final_financier_name_for_order = banker_name # Use banker name if Bank is selected
                    

                else:
                    # Standard non-Bank, non-Other selection
                    final_financier_name_for_order = financier_name_selection
                    banker_name = "" # Ensure banker_name is cleared
                    
                    # Show standard executive dropdown
                    st.markdown("##### Finance Executive")
                    final_executive_name_for_order = st.selectbox("Executive Name:", EXECUTIVE_LIST)

                # --- Payment Input ---
                st.subheader("Payment Amounts")
                dd_amount = st.number_input("DD / Booking Amount:", min_value=0.0, step=100.0)
            
                hp_fee_to_charge, incentive_earned = calculate_finance_fees(
                    financier_name_selection, dd_amount, out_finance_flag, incentive_rules
                )
                
                total_customer_obligation = final_cost_by_staff + hp_fee_to_charge + incentive_earned
                remaining_upfront_needed = total_customer_obligation - dd_amount
                calculated_dp = max(0.0, remaining_upfront_needed)
                down_payment = calculated_dp
                financed_amount = total_customer_obligation - dd_amount - down_payment
                if financed_amount < 0: financed_amount = 0.0

            st.markdown("### Final Figures")
            col_hp, col_incentive = st.columns(2)
            col_hp.metric("HP Fee Charged", f"₹{hp_fee_to_charge:,.2f}")
            col_incentive.metric("Incentive Collected", f"₹{incentive_earned:,.2f}")
            
            st.info(f"**Total Customer Obligation:** **₹{total_customer_obligation:,.2f}**")
            st.success(f"**Required Down Payment:** **₹{calculated_dp:,.2f}**")
            
        else: # Cash Sale
            st.success(f"Total Cash Amount Due: **₹{final_cost_by_staff:,.2f}**")


    # --- 4. Generate PDF Button ---
    st.markdown("---")
    if st.button("GENERATE DUAL-FIRM BILLS", type="primary", use_container_width=True):
        
        # --- Validation ---
        if not name or not phone:
            st.error("Please enter Customer Name and Phone Number.")
            return
        
        # NEW Validation for 'Other'
        if sale_type == 'Finance' and financier_name_selection == 'Other':
            if not final_financier_name_for_order or not final_executive_name_for_order:
                st.error("Please enter the Custom Finance Company and Executive names.")
                return
        
        if sale_type == 'Finance' and financier_name_selection == 'Bank' and not banker_name.strip():
            st.error("Please enter the Banker's Name for the 'Bank' quotation.")
            return

        # --- DB TRANSACTION BLOCK ---
        db: Session = next(get_db())
        try:
            dc_number, dc_seq_no = get_next_dc_number(db, branch_id)
            branch_obj = db.query(models.Branch).get(branch_id)
            # Generate Accessory Bills
            acc_list = get_accessory_package_for_model(db, selected_model)
            acc_bills_data = process_accessories_and_split(selected_model, acc_list, firm_master_df, branch_obj)
            
            bill_1_seq, bill_2_seq = 0, 0
            for bill in acc_bills_data:
                inv_str, inv_seq = generate_accessory_invoice_number(db,branch_obj, bill['firm_id'], bill['accessory_slot'])
                bill['Invoice_No'] = inv_str
                bill['Acc_Inv_Seq'] = inv_seq
                if bill['accessory_slot'] == 1: bill_1_seq = inv_seq
                if bill['accessory_slot'] == 2: bill_2_seq = inv_seq

            # Instantiate SalesOrder
            order = SalesOrder(
                name, place, phone, selected_vehicle_row.iloc[0].to_dict(), final_cost_by_staff, 
                sales_staff, 
                final_financier_name_for_order, # Use the final determined name
                final_executive_name_for_order, # Use the final determined name
                selected_paint_color,
                hp_fee_to_charge, incentive_earned, banker_name, dc_number,
                branch_name, 
                [bill for bill in acc_bills_data if bill['grand_total'] > 0],
                branch_id,
                pr_fee_checkbox, # <-- NEW (Pass the boolean flag)
                ew_selection
            )
            
            if sale_type == "Finance":
                order.set_finance_details(dd_amount, down_payment)
            
            # Save Data to Database
            export_data = order.get_data_for_export(dc_seq_no, bill_1_seq, bill_2_seq)
            create_sales_record(db, export_data) # This function handles the commit
            log_sale(
                db, branch_id, selected_model, 
                selected_vehicle_row.iloc[0]['Variant'], 
                selected_paint_color, 1, datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S IST'), 
                f"Auto-logged from DC: {dc_number}"
            )
            
            # PDF Generation (In-Memory)
            pdf_buffer = io.BytesIO()
            order.generate_pdf_challan(pdf_buffer)
            pdf_buffer.seek(0)
            
            pdf_filename = f"{dc_number}_{name.replace(' ', '_')}.pdf"

            st.download_button(
                label="Download Official DC Form (PDF)",
                data=pdf_buffer,
                file_name=pdf_filename,
                mime="application/pdf"
            )
            
            st.success(f"{dc_number} generated and saved successfully!")
            st.balloons()
            
        except Exception as e:
            st.error(f"An error occurred during the transaction: {e}")
        finally:
            db.close()
# --- 5. MAIN ROUTER ---

def main():
    """Main application router."""
    
    # Check session state to decide which page to show
    if st.session_state.selected_branch_id is None:
        BranchSelector()
    else:
        SalesForm()

if __name__ == "__main__":
    main()