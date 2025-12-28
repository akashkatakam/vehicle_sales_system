import streamlit as st
from core.auth import check_login
from features.dashboard.data import load_dashboard_data
from ui.views import render_insurance_tr_view, render_metrics, render_owner_view, render_backoffice_view

st.set_page_config(page_title="Sales Dashboard", layout="wide")

if check_login():
    user_roles = st.session_state.get("roles", [])
    accessible_branches = st.session_state.get("accessible_branches", [])
    st.title("📊 Sales Analytics Dashboard")

    data, all_branches = load_dashboard_data(None)
    if data.empty:
        st.warning("No data available.")
        st.stop()

    with st.sidebar:
        st.header("Filters")
        min_d, max_d = data['Timestamp'].min().date(), data['Timestamp'].max().date()
        range_min = max_d.replace(day=1)
        dates = st.date_input("Date Range", [range_min, max_d], min_value=min_d, max_value=max_d)

        if "Owner" in user_roles or "ALL" in accessible_branches:
            allowed = sorted(data['Branch_Name'].unique())
        else:
            allowed = sorted([b.Branch_Name for b in all_branches if b.Branch_ID in accessible_branches])

        sel_branches = st.multiselect("Branches", allowed, default=allowed)

    if len(dates) == 2:
        mask = ((data['Timestamp'].dt.date >= dates[0]) & (data['Timestamp'].dt.date <= dates[1]) & (
            data['Branch_Name'].isin(sel_branches)))
        filtered_data = data[mask].copy()
    else:
        filtered_data = data[data['Branch_Name'].isin(sel_branches)].copy()

    if filtered_data.empty:
        st.warning("No data matches selected filters.")
        st.stop()

    primary_role = user_roles[0] if user_roles else "Guest"
    render_metrics(filtered_data, primary_role)

    if "Owner" in user_roles:
        render_owner_view(filtered_data)
    elif "Back Office" in user_roles:
        render_backoffice_view(filtered_data)
    elif "Insurance/TR" in user_roles:
        render_insurance_tr_view(filtered_data)
    else:
        st.info("No dashboard view configured for this role.")