# dashboard.py

import streamlit as st
import pandas as pd
from database import get_db
from data_manager import get_all_sales_records_for_dashboard
import altair as alt # For advanced charts

# --- 1. Page Config ---
st.set_page_config(
    page_title="Sales Dashboard",
    layout="wide"
)

st.title("📊 Sales Analytics Dashboard")

# --- 2. Load Data ---
# This function calls the new data_manager function and caches it.
@st.cache_data(ttl=600)
def load_data():
    """Wrapper to cache the main data load."""
    print("CACHE MISS: Loading dashboard data...")
    db = next(get_db())
    try:
        data = get_all_sales_records_for_dashboard(db)
        return data
    finally:
        db.close()

data = load_data()

if data.empty:
    st.warning("No sales data found in the database.")
    st.stop() # Stop execution if no data

# --- 3. Sidebar Filters ---
st.sidebar.header("Dashboard Filters")

# Branch Filter
all_branches = data['Branch_Name'].unique()
selected_branches = st.sidebar.multiselect(
    "Select Branch",
    options=all_branches,
    default=all_branches
)

# Date Range Filter
min_date = data['Timestamp'].min().date()
max_date = data['Timestamp'].max().date()

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Apply filters
try:
    filtered_data = data[
        (data['Branch_Name'].isin(selected_branches)) &
        (data['Timestamp'].dt.date >= date_range[0]) &
        (data['Timestamp'].dt.date <= date_range[1])
    ]
except Exception as e:
    st.error(f"Error filtering data. Ensure date range is valid. {e}")
    st.stop()

if filtered_data.empty:
    st.warning("No data found for the selected filters.")
    st.stop()

# --- 4. Main Page Metrics ---
total_revenue = filtered_data['Price_Negotiated_Final'].sum()
total_sales = len(filtered_data)
avg_sale = total_revenue / total_sales if total_sales > 0 else 0
total_discount = filtered_data['Discount_Given'].sum()

st.header("Key Metrics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Revenue", f"₹{total_revenue:,.0f}")
col2.metric("Total Units Sold", f"{total_sales}")
col3.metric("Average Sale Value", f"₹{avg_sale:,.0f}")
col4.metric("Total Discounts", f"₹{total_discount:,.0f}")

st.markdown("---")

# --- 5. Charts ---
st.header("Visualizations")

# Chart 1: Sales by Branch
st.subheader("Total Revenue by Branch")
branch_sales = filtered_data.groupby('Branch_Name')['Price_Negotiated_Final'].sum().reset_index()
chart_branch = alt.Chart(branch_sales).mark_bar().encode(
    x=alt.X('Branch_Name', title='Branch', sort=None),
    y=alt.Y('Price_Negotiated_Final', title='Total Revenue (₹)')
).interactive()
st.altair_chart(chart_branch, use_container_width=True)


# Chart 2: Sales Over Time
st.subheader("Sales Revenue Over Time")
# Resample data by day for a clean time-series chart
time_sales = filtered_data.set_index('Timestamp').resample('D')['Price_Negotiated_Final'].sum().reset_index()
chart_time = alt.Chart(time_sales).mark_line().encode(
    x=alt.X('Timestamp', title='Date'),
    y=alt.Y('Price_Negotiated_Final', title='Total Revenue (₹)')
).interactive()
st.altair_chart(chart_time, use_container_width=True)

# --- 6. Raw Data Table ---
st.header("Raw Sales Data")
st.data_editor(filtered_data)