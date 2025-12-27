import streamlit as st
import pandas as pd
from core.database import get_db # Updated
from core.data_manager import get_all_sales_records_for_dashboard, get_all_branches # Updated
from core import models # Updated
from features.sales.config import get_movement_category, get_vehicle_type # Updated

@st.cache_data(ttl=600)
def load_dashboard_data(branch_id_filter: str):
    """
    Loads and preprocesses all necessary data for the dashboard.
    Cached for 10 minutes to improve performance.
    """
    print(f"CACHE MISS: Dashboard data for {branch_id_filter or 'All'}")
    db = next(get_db())
    try:
        # 1. Fetch raw data
        data = get_all_sales_records_for_dashboard(db, branch_id_filter)
        
        # 2. Fetch branch info for filters
        if branch_id_filter:
            all_branches = [db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id_filter).first()]
        else:
            all_branches = get_all_branches(db)
            
        branch_map = {b.Branch_ID: b.Branch_Name for b in all_branches if b}
        data['Branch_Name'] = data['Branch_ID'].map(branch_map).fillna(data['Branch_ID'])
        if 'Model' in data.columns:
            data['Vehicle_Type'] = data['Model'].apply(get_vehicle_type)
        else:
            data['Vehicle_Type'] = 'Unknown'
            
        if 'Model' in data.columns and 'Paint_Color' in data.columns:
            data['Movement_Category'] = data.apply(
                lambda row: get_movement_category(row['Model'], row['Paint_Color']), 
                axis=1
            )
        else:
            data['Movement_Category'] = 'N/A'

        # 3. Data Type Cleaning & Calculations
        numeric_cols = ['Price_Negotiated_Final', 'Discount_Given', 'Payment_DD', 'Payment_DD_Received']
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)

        # Live calculation for accurate pending amounts
        data['Live_Shortfall'] = data['Payment_DD'] - data['Payment_DD_Received']

        # 1. Dynamic Dues Calculation (as requested): True if Live_Shortfall > 0 OR has_double_tax is True
        data['has_dues'] = (data['Live_Shortfall'] > 0.0) | (data['has_double_tax'] == True)
        
        # 2. WhatsApp Link Generation (Assuming India Country Code +91)
        base_wa_url = "https://wa.me/"
        
        # Message Templates
        INSURANCE_MSG = "Great news! Your vehicle's insurance papers are complete and ready. Find the attached document."
        TR_MSG = "Update: Your vehicle's Temporary/Permanent Registration (TR) is successfully processed."
        PLATES_MSG = "Final Step: Your HSRP plates have been received at our branch. Please visit us for fitting at your convenience."
        GENERIC_MSG = "Hello, this is a quick update regarding your vehicle delivery. Please contact our team for details."

        # Sanitize and prepend +91 to the 10-digit number
        data['WA_Phone'] = data['Phone_Number'].astype(str).str.replace(r'\D', '', regex=True)
        # Only add +91 if it looks like a 10-digit number and doesn't have a code already
        data['WA_Phone'] = data['WA_Phone'].apply(lambda x: f"+91{x}" if len(x) == 10 and not x.startswith('+') and not x.startswith('0') else x)

        def create_wa_link(phone: str, message: str) -> str | None:
            if len(phone) > 3 and phone.startswith('+91'):
                # Encode the message for the URL query, replacing spaces
                return f"{base_wa_url}{phone}?text={message.replace(' ', '%20')}"
            return None

        # Create a single contextual link column
        def get_contextual_link(row):
            phone = row['WA_Phone']
            
            # If the phone is not valid, stop immediately
            if not phone or not phone.startswith('+91'):
                return None
                
            # 1. Highest priority: Plates Received
            if row['plates_received']:
                return create_wa_link(phone, PLATES_MSG)
            # 2. Next priority: TR Done
            elif row['is_tr_done']:
                return create_wa_link(phone, TR_MSG)
            # 3. Last priority: Insurance Done
            elif row['is_insurance_done']:
                return create_wa_link(phone, INSURANCE_MSG)
            # 4. Fallback: No status met, but valid phone number, link to general chat
            else:
                 return create_wa_link(phone, GENERIC_MSG)

        return data, all_branches
    finally:
        db.close()