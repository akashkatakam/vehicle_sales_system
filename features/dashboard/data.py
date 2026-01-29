import streamlit as st
import pandas as pd
from core.database import get_db
from core.data_manager import get_all_sales_records_for_dashboard, get_all_branches
from core import models
from features.sales.config import get_movement_category, get_vehicle_type

@st.cache_data(ttl=600)
def load_dashboard_data(branch_id_filter: str):
    """
    Loads and preprocesses all necessary data for the dashboard.
    Cached for 10 minutes to improve performance.
    """
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
        numeric_cols = [
            'Price_Negotiated_Final', 'Discount_Given', 'Payment_DD',
            'Payment_DD_Received', 'shortfall_received', 'Payment_Shortfall'
        ]
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)

        # Live calculation for accurate pending amounts
        # FIX: Subtract both initial DD received AND any subsequent shortfall recovery
        data['Live_Shortfall'] = data['Payment_DD'] - (data['Payment_DD_Received'] + data['shortfall_received'])

        # 1. Dynamic Dues Calculation
        # Use a small epsilon (1.0) to account for floating point variance, though 0.0 is usually fine for strict logic
        data['has_dues'] = (data['Live_Shortfall'] > 1.0) | (data['has_double_tax'] == True)

        # --- NEW: Aging & Status Logic (Text Only for Styling) ---
        if 'Timestamp' in data.columns:
            now = pd.Timestamp.now()
            data['Aging_Days'] = (now - data['Timestamp']).dt.days.fillna(0).astype(int)
        else:
            data['Aging_Days'] = 0

        def get_aging_status(row):
            # Ignore Cash Sales / Invalid Bankers
            if row['Banker_Name'] == 'N/A (Cash Sale)' or pd.isna(row['Banker_Name']) or row['Banker_Name'] == '':
                return "Cash/Other"

            # 1. Fully Paid -> Green Status
            # Check if total received (Initial + Recovery) matches Expected
            total_received = row['Payment_DD_Received'] + row['shortfall_received']
            if total_received >= (row['Payment_DD'] - 1.0):
                return "Paid"

            # 2. Pending -> Check Aging
            days = row['Aging_Days']
            if days > 15:
                return ">15 Days"
            elif days >= 7:
                return "7-15 Days"
            else:
                return "0-7 Days"

        data['Aging_Status'] = data.apply(get_aging_status, axis=1)
        # ---------------------------------------

        # 2. WhatsApp Link Generation
        base_wa_url = "https://wa.me/"

        INSURANCE_MSG = "Great news! Your vehicle's insurance papers are complete and ready. Find the attached document."
        TR_MSG = "Update: Your vehicle's Temporary/Permanent Registration (TR) is successfully processed."
        PLATES_MSG = "Final Step: Your HSRP plates have been received at our branch. Please visit us for fitting at your convenience."
        GENERIC_MSG = "Hello, this is a quick update regarding your vehicle delivery. Please contact our team for details."

        data['WA_Phone'] = data['Phone_Number'].astype(str).str.replace(r'\D', '', regex=True)
        data['WA_Phone'] = data['WA_Phone'].apply(
            lambda x: f"+91{x}" if len(x) == 10 and not x.startswith('+') and not x.startswith('0') else x)

        def create_wa_link(phone: str, message: str) -> str | None:
            if len(phone) > 3 and phone.startswith('+91'):
                return f"{base_wa_url}{phone}?text={message.replace(' ', '%20')}"
            return None

        def get_contextual_link(row):
            phone = row['WA_Phone']
            if not phone or not phone.startswith('+91'):
                return None
            if row['plates_received']:
                return create_wa_link(phone, PLATES_MSG)
            elif row['is_tr_done']:
                return create_wa_link(phone, TR_MSG)
            elif row['is_insurance_done']:
                return create_wa_link(phone, INSURANCE_MSG)
            else:
                return create_wa_link(phone, GENERIC_MSG)

        return data, all_branches
    finally:
        db.close()