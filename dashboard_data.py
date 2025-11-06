import streamlit as st
import pandas as pd
from database import get_db
from data_manager import get_all_sales_records_for_dashboard, get_all_branches
import models

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

        # 3. Data Type Cleaning & Calculations
        numeric_cols = ['Price_Negotiated_Final', 'Discount_Given', 'Payment_DD', 'Payment_DD_Received']
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)

        # Live calculation for accurate pending amounts
        data['Live_Shortfall'] = data['Payment_DD'] - data['Payment_DD_Received']

        return data, all_branches
    finally:
        db.close()