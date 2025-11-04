import streamlit as st
import pandas as pd
from database import get_db
from data_manager import (
    get_all_sales_records_for_dashboard, 
    get_all_branches, 
    get_user_by_username,
    update_dd_payment
)
import altair as alt
import models # <-- Import models

# --- 1. Page Config ---
st.set_page_config(
    page_title="Sales Dashboard",
    layout="wide"
)

# --- 2. LOGIN & ROLE CHECK ---
def check_login():
    """Shows login form and returns True if user is logged in."""
    
    if st.session_state.get("logged_in", False):
        st.sidebar.success(f"Logged in as: **{st.session_state.role}**")
        if st.session_state.role == "Back Office":
            st.sidebar.info(f"Branch: **{st.session_state.branch_name}**")
        
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()
        return True

    with st.form("login_form"):
        st.title("Staff Login")
        st.markdown("Please log in to access the dashboard.")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            db = next(get_db())
            try:
                user = get_user_by_username(db, username)
                
                if user and user.verify_password(password):
                    st.session_state["logged_in"] = True
                    st.session_state["role"] = user.role
                    st.session_state["user_branch_id"] = user.Branch_ID 
                    
                    if user.Branch_ID:
                        branch = db.query(models.Branch).filter(models.Branch.Branch_ID == user.Branch_ID).first()
                        st.session_state["branch_name"] = branch.Branch_Name if branch else "N/A"
                    else:
                        st.session_state["branch_name"] = "All Branches"
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
            finally:
                db.close()
    
    return False

# --- 3. Main Dashboard Function ---
def show_dashboard(user_role: str, user_branch_id: str):
    """This function contains the entire dashboard UI."""
    
    st.title("📊 Sales Analytics Dashboard")

    # --- Load Data ---
    @st.cache_data(ttl=600) 
    def load_data(branch_id_filter: str):
        """Wrapper to cache the main data load."""
        print(f"CACHE MISS: Loading dashboard data for Branch: {branch_id_filter or 'All'}")
        db = next(get_db())
        try:
            data = get_all_sales_records_for_dashboard(db, branch_id_filter)
            
            if branch_id_filter:
                all_branches_list = [db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id_filter).first()]
            else:
                all_branches_list = get_all_branches(db)
                
            branch_map = {b.Branch_ID: b.Branch_Name for b in all_branches_list if b}
            data['Branch_Name'] = data['Branch_ID'].map(branch_map).fillna(data['Branch_ID'])
            return data, all_branches_list
        finally:
            db.close()

    # Load data based on the user's assigned branch
    data, all_branches = load_data(user_branch_id)

    if data.empty:
        st.warning("No sales data found for your branch.")
        st.stop()

    # --- Sidebar Filters ---
    st.sidebar.header("Dashboard Filters")
    
    if user_role == "Owner":
        branch_name_list = sorted(data['Branch_Name'].unique())
        selected_branches = st.sidebar.multiselect(
            "Select Branch", options=branch_name_list, default=branch_name_list
        )
    else:
        st.sidebar.text_input("Branch", value=st.session_state.branch_name, disabled=True)
        selected_branches = [st.session_state.branch_name]

    min_date = data['Timestamp'].min().date()
    max_date = data['Timestamp'].max().date()
    date_range = st.sidebar.date_input(
        "Select Date Range", value=(min_date, max_date),
        min_value=min_date, max_value=max_date
    )

    # Apply filters
    try:
        if len(date_range) != 2:
            st.warning("Please select a valid date range.")
            st.stop()
        filtered_data = data[
            (data['Branch_Name'].isin(selected_branches)) &
            (data['Timestamp'].dt.date >= date_range[0]) &
            (data['Timestamp'].dt.date <= date_range[1])
        ]
    except Exception as e:
        st.error(f"Error filtering data. {e}")
        st.stop()

    if filtered_data.empty:
        st.warning("No data found for the selected filters.")
        st.stop()
    
    numeric_cols = [
        'Price_Negotiated_Final', 'Discount_Given', 
        'Payment_DD', 'Payment_DD_Received', 'Payment_Shortfall'
    ]
    
    for col in numeric_cols:
        filtered_data[col] = pd.to_numeric(filtered_data[col], errors='coerce').fillna(0)

    # --- Main Page Metrics ---
    total_revenue = filtered_data['Price_Negotiated_Final'].sum()
    total_sales = len(filtered_data)
    total_discount = filtered_data['Discount_Given'].sum()
    
    total_dd_expected = filtered_data['Payment_DD'].sum()
    total_dd_received = filtered_data['Payment_DD_Received'].sum()
    total_short_fall = filtered_data['Payment_Shortfall'].sum()
    total_dd_pending = total_dd_expected - total_dd_received
    
    st.header("Key Metrics")
    
    if user_role == "Back Office":
        col1, col2, col3,col4,col5 = st.columns(5)
        col1.metric("Total Units Sold", f"{total_sales}")
        col2.metric("Total DD Expected", f"₹{total_dd_expected:,.0f}")
        col3.metric("Total DD Received", f"₹{total_dd_received:,.0f}")
        col4.metric("Total DD Pending", f"₹{total_dd_pending:,.0f}")
        col5.metric("Total short amount", f"₹{total_short_fall:,.0f}")

        filtered_data['Live_Shortfall'] = filtered_data['Payment_DD'] - filtered_data['Payment_DD_Received']
            
        banker_data = filtered_data[
            (filtered_data['Banker_Name'].notna()) & 
            (filtered_data['Banker_Name'] != 'N/A (Cash Sale)') & 
            (filtered_data['Banker_Name'] != '') &
            (filtered_data['Live_Shortfall'] > 0) # Use the live calculation
        ]
        if not banker_data.empty:
            banker_summary = banker_data.groupby('Banker_Name')['Live_Shortfall'].sum().reset_index()
            banker_summary = banker_summary.rename(columns={'Live_Shortfall': 'Total Pending (₹)'})
            banker_summary['Total Pending (₹)'] = banker_summary['Total Pending (₹)'].apply(lambda x: f"₹{x:,.0f}")
            st.dataframe(banker_summary, width="stretch", hide_index=True)
        else:
            st.info("No pending DD amounts found for any bankers in this period.")
            

    # --- 5. INTERACTIVE DRILL-DOWN CHARTS ---
    if user_role == "Owner":
        st.header("Vehicle Sales Analysis")
        
        tab_finance, tab_staff = st.tabs(["Finance summary", "Vehicle summary"])

        with tab_staff:
            st.subheader("Vehicle Sales by Model (Click to Drill Down)")
            st.info("Click on a bar in the 'Sales by Model' chart to filter the 'Sales by Color' chart below.")
            model_selection = alt.selection_point(fields=['Model'], empty=True)
            chart_model = alt.Chart(filtered_data).mark_bar().encode(
                x=alt.X('Model', title='Vehicle Model', sort=None),
                y=alt.Y('count()', title='Number of Units Sold'),
                tooltip=['Model', 'count()'],
                color=alt.condition(model_selection, alt.value('orange'), alt.value('steelblue'))
            ).add_params(model_selection).interactive()

            chart_color = alt.Chart(filtered_data).mark_bar().encode(
                x=alt.X('Paint_Color', title='Paint Color', sort=None),
                y=alt.Y('count()', title='Number of Units Sold'),
                tooltip=['Model', 'Paint_Color', 'count()']
            ).transform_filter(model_selection).properties(
                title="Sales by Color (for selected model)"
            )
            st.altair_chart(chart_model, use_container_width=True)
            st.altair_chart(chart_color, use_container_width=True)

            sales_staff_data = filtered_data.groupby('Sales_Staff')['id'].count().reset_index(name='Units Sold')
            chart_staff = alt.Chart(sales_staff_data).mark_bar().encode(
                x=alt.X('Sales_Staff', title='Sales Staff', sort='-y'),
                y=alt.Y('Units Sold', title='Number of Units Sold')
            ).interactive()
            st.altair_chart(chart_staff, use_container_width=True)
            
        with tab_finance:
            st.subheader("Financial analysis")
            total_revenue = filtered_data['Price_Negotiated_Final'].sum()
            total_sales = len(filtered_data)
            avg_sale = total_revenue / total_sales if total_sales > 0 else 0
            total_discount = filtered_data['Discount_Given'].sum()
            
            # This is the LIVE calculation
            total_dd_expected = filtered_data['Payment_DD'].sum()
            total_dd_received = filtered_data['Payment_DD_Received'].sum()
            total_dd_pending = total_dd_expected - total_dd_received

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Revenue", f"₹{total_revenue:,.0f}")
            col2.metric("Total Units Sold", f"{total_sales}")
            col4.metric("Total Discounts", f"₹{total_discount:,.0f}")
            col5.metric("Total DD Pending", f"₹{total_dd_pending:,.0f}")
            
            st.markdown("---")

            # --- NEW: Summary by Branch Table (Using Live Calculation) ---
            st.subheader("Summary by Branch")
            # 1. Group by Branch and aggregate all necessary columns
            branch_summary = filtered_data.groupby('Branch_Name').agg(
                Total_Revenue=('Price_Negotiated_Final', 'sum'),
                Units_Sold=('id', 'count'),
                Total_DD_Expected=('Payment_DD', 'sum'),
                Total_DD_Received=('Payment_DD_Received', 'sum')
                # We no longer sum the stale 'Payment_Shortfall' column
            ).reset_index()
            
            # 2. Perform the live calculation (Expected - Received)
            branch_summary['Total_DD_Pending'] = branch_summary['Total_DD_Expected'] - branch_summary['Total_DD_Received']
            
            # 3. Format for display
            branch_summary_display = branch_summary[[
                'Branch_Name', 
                'Total_Revenue', 
                'Units_Sold', 
                'Total_DD_Pending'
            ]].copy() # Use .copy() to avoid SettingWithCopyWarning
            
            branch_summary_display['Total_Revenue'] = branch_summary_display['Total_Revenue'].apply(lambda x: f"₹{x:,.0f}")
            branch_summary_display['Total_DD_Pending'] = branch_summary_display['Total_DD_Pending'].apply(lambda x: f"₹{x:,.0f}")
            
            st.dataframe(branch_summary_display, use_container_width=True, hide_index=True)

            
            st.subheader("DD Pending by Banker")
            
            # Calculate live shortfall for the filter
            filtered_data['Live_Shortfall'] = filtered_data['Payment_DD'] - filtered_data['Payment_DD_Received']
            
            banker_data = filtered_data[
                (filtered_data['Banker_Name'].notna()) & 
                (filtered_data['Banker_Name'] != 'N/A (Cash Sale)') & 
                (filtered_data['Banker_Name'] != '') &
                (filtered_data['Live_Shortfall'] > 0) # Use the live calculation
            ]
            if not banker_data.empty:
                banker_summary = banker_data.groupby('Banker_Name')['Live_Shortfall'].sum().reset_index()
                banker_summary = banker_summary.rename(columns={'Live_Shortfall': 'Total Pending (₹)'})
                banker_summary['Total Pending (₹)'] = banker_summary['Total Pending (₹)'].apply(lambda x: f"₹{x:,.0f}")
                st.dataframe(banker_summary, width="stretch", hide_index=True)
            else:
                st.info("No pending DD amounts found for any bankers in this period.")
            # --- END NEW BANKER TABLE ---
            


    # --- 6. Raw Data Table (EDITABLE) ---
    st.markdown("---")
    st.header("Sales Records & DD Entry")

    # Define which columns are editable
    column_config = {
        'id': st.column_config.NumberColumn("Record ID", disabled=True),
        'DC_Number': st.column_config.TextColumn("DC Number", disabled=True),
        'Branch_Name': st.column_config.TextColumn("Branch", disabled=True),
        'Timestamp': st.column_config.DatetimeColumn("Date", format="D/M/YYYY", disabled=True),
        'Customer_Name': st.column_config.TextColumn("Customer", disabled=True),
        'Sales_Staff': st.column_config.TextColumn("Sales Staff", disabled=True),
        'Payment_DD': st.column_config.NumberColumn("DD Expected", format="₹%.2f", disabled=True),
        'Payment_DD_Received': st.column_config.NumberColumn(
            "DD Received (Actual)",
            help="Enter the actual DD amount received by the back office.",
            format="₹%.2f",
            disabled=False # <-- This is editable
        ),
        'Payment_Shortfall': st.column_config.NumberColumn("Shortfall", format="₹%.2f", disabled=True)
    }
    
    # Define columns to show
    columns_to_show_back_office = [
        'id', 'DC_Number', 'Branch_Name', 'Timestamp', 'Customer_Name', 'Sales_Staff','Model','Variant','Banker_name','Price_ORP','Payment_DownPayment'
        'Payment_DD', 'Payment_DD_Received', 'Payment_Shortfall'
    ]
    
    editor_key = "sales_data_editor"

    # --- ROLE-BASED DATA ---
    if user_role == "Owner":
        st.info("Owner View: Double-click a 'DD Received' cell to edit.")
        edited_df = st.data_editor(
            filtered_data,
            column_config=column_config,
            # Owner can see all columns, but only edit one
            disabled=filtered_data.columns.drop('Payment_DD_Received'),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key=editor_key
        )
        
    elif user_role == "Back Office":
        st.info("Back Office View: Double-click a 'DD Received' cell to edit.")
        
        # --- FIX: Use column_order to show only relevant columns ---
        edited_df = st.data_editor(
            filtered_data,
            column_config=column_config,
            column_order=columns_to_show_back_office, 
            disabled=filtered_data.columns.drop('Payment_DD_Received'),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key=editor_key
        )
    
    else: # Fallback for any other role (Read-only)
        st.dataframe(filtered_data, hide_index=True, use_container_width=True)


    # --- 7. SAVE BUTTON LOGIC (Only for authorized roles) ---
    if user_role in ["Owner", "Back Office"]:
        if st.button("Save DD Updates to Database", type="primary"):
            
            # Read changes directly from session state
            if editor_key in st.session_state and st.session_state[editor_key]["edited_rows"]:
                
                edited_rows = st.session_state[editor_key]["edited_rows"]
                db = next(get_db())
                try:
                    num_updates = 0
                    
                    for row_index, changes in edited_rows.items():
                        
                        # Get the 'id' of the record from the original filtered_data
                        record_id = int(filtered_data.iloc[row_index]['id'])
                        
                        if 'Payment_DD_Received' in changes:
                            dd_received = float(changes['Payment_DD_Received'])
                            
                            # Call the update function for each changed row
                            update_dd_payment(db, record_id, dd_received)
                            num_updates += 1
                    
                    st.success(f"Successfully updated {num_updates} record(s)!")
                    # Clear the data cache to force a reload from the DB
                    st.cache_data.clear()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"An error occurred during save: {e}")
                finally:
                    db.close()
            else:
                st.info("No changes detected.")

# --- 4. Main App Router ---
if __name__ == "__main__":
    if check_login():
        show_dashboard(
            user_role=st.session_state.role,
            user_branch_id=st.session_state.user_branch_id
        )