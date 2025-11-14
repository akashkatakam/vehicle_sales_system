import streamlit as st
from auth import check_login
from dashboard_data import load_dashboard_data
from views import render_insurance_tr_view, render_metrics, render_owner_view, render_backoffice_view

# --- Page Setup ---
st.set_page_config(page_title="Sales Dashboard", layout="wide")

# --- Main App Flow ---
if check_login():
    user_role = st.session_state.role
    branch_filter = st.session_state.user_branch_id

    st.title("📊 Sales Analytics Dashboard")

    # 1. Load Data
    data, all_branches = load_dashboard_data(branch_filter)
    if data.empty:
        st.warning("No data available for your assigned branch.")
        st.stop()

    # 2. Sidebar Filters
    with st.sidebar:
        st.header("Filters")
        min_d, max_d = data['Timestamp'].min().date(), data['Timestamp'].max().date()
        dates = st.date_input("Date Range", [min_d, max_d], min_value=min_d, max_value=max_d)
        
        if user_role == "Owner":
            b_names = sorted(data['Branch_Name'].unique())
            sel_branches = st.multiselect("Branches", b_names, default=b_names)
        else:
            st.text_input("Branch", value=st.session_state.branch_name, disabled=True)
            sel_branches = [st.session_state.branch_name]

    # 3. Apply Filters
    if len(dates) == 2:
        mask = (data['Timestamp'].dt.date >= dates[0]) & (data['Timestamp'].dt.date <= dates[1]) & (data['Branch_Name'].isin(sel_branches))
        filtered_data = data[mask].copy()
    else:
        filtered_data = data.copy()

    if filtered_data.empty:
        st.warning("No data matches selected filters.")
        st.stop()

    # 4. Render Views
    render_metrics(filtered_data, user_role)
    
    if user_role == "Owner":
        render_owner_view(filtered_data)
    elif user_role == "Back Office":
        render_backoffice_view(filtered_data)
    elif user_role == "Insurance/TR" or user_role=="Owner":
        render_insurance_tr_view(filtered_data)