import streamlit as st
from auth import check_login
from dashboard_data import load_dashboard_data
from views import render_insurance_tr_view, render_metrics, render_owner_view, render_backoffice_view

# --- Page Setup ---
st.set_page_config(page_title="Sales Dashboard", layout="wide")

# --- Main App Flow ---
if check_login():
    # 1. Retrieve User Permissions from Session State
    # (These are populated in auth.py upon login)
    user_roles = st.session_state.get("roles", [])
    accessible_branches = st.session_state.get("accessible_branches", [])

    st.title("📊 Sales Analytics Dashboard")

    # 2. Load Data
    # We load ALL data initially (passing None) and then filter it in memory 
    # based on the user's access rights. This simplifies the multi-branch logic.
    data, all_branches = load_dashboard_data(None)
    
    if data.empty:
        st.warning("No data available.")
        st.stop()

    # 3. Sidebar Filters
    with st.sidebar:
        st.header("Filters")
        
        # A. Date Range Filter
        min_d, max_d = data['Timestamp'].min().date(), data['Timestamp'].max().date()
        min_d = min_d.replace(day=1)
        dates = st.date_input("Date Range", [min_d, max_d], min_value=min_d, max_value=max_d)
        
        # B. Branch Filter
        # Determine which branches this user is ALLOWED to see in the dropdown
        if "Owner" in user_roles or "ALL" in accessible_branches:
            # Owner or Super Admin sees ALL branches
            allowed_branch_names = sorted(data['Branch_Name'].unique())
        else:
            # Filter the master branch list to only those IDs the user has access to
            # accessible_branches contains strings like ['BR-001', 'BR-002']
            allowed_branch_names = sorted([
                b.Branch_Name for b in all_branches 
                if b.Branch_ID in accessible_branches
            ])
        
        # If the user has access to nothing (edge case), stop
        if not allowed_branch_names:
            st.error("You do not have access to any branches.")
            st.stop()

        # The actual dropdown/multiselect
        sel_branches = st.multiselect("Branches", allowed_branch_names, default=allowed_branch_names)

    # 4. Apply Filters to Data
    if len(dates) == 2:
        mask = (
            (data['Timestamp'].dt.date >= dates[0]) & 
            (data['Timestamp'].dt.date <= dates[1]) & 
            (data['Branch_Name'].isin(sel_branches))
        )
        filtered_data = data[mask].copy()
    else:
        # Fallback if date picker is incomplete
        filtered_data = data[data['Branch_Name'].isin(sel_branches)].copy()

    if filtered_data.empty:
        st.warning("No data matches selected filters.")
        st.stop()

    # 5. Render Views based on Role
    # We pass the first role found as the "primary" role for metrics display context,
    # or default to "Guest" if something is wrong.
    primary_role_context = user_roles[0] if user_roles else "Guest"
    render_metrics(filtered_data, primary_role_context)
    
    # Logic to decide which main view(s) to show.
    # Priority: Owner View > Back Office View > Insurance View
    # (Or you could show tabs if a user has multiple roles, but simple priority is often cleaner)
    
    if "Owner" in user_roles:
        render_owner_view(filtered_data)
        # Owners also often want to see the Insurance queue, so we can append it or check tabs.
        # For now, following the original structure where Owner sees specific analytics.
        
    elif "Back Office" in user_roles:
        render_backoffice_view(filtered_data)
        
    elif "Insurance/TR" in user_roles:
        render_insurance_tr_view(filtered_data)
        
    else:
        st.info("Your assigned role does not have a specific dashboard view configured.")