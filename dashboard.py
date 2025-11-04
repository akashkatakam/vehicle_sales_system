import streamlit as st
import pandas as pd
from database import get_db
# Import the new function we will create in data_manager
from data_manager import get_all_sales_records_for_dashboard, get_all_branches, get_user_by_username, update_dd_payment 
from models import User
import altair as alt

import models

# --- 1. Page Config ---
st.set_page_config(
    page_title="Sales Dashboard",
    layout="wide"
)

# --- 2. LOGIN & ROLE CHECK (MODIFIED) ---

def check_login():
    """Shows login form and returns True if user is logged in."""
    
    if st.session_state.get("logged_in", False):
        st.sidebar.success(f"Logged in as: **{st.session_state.role}**")
        # Also show the branch if they are restricted
        if st.session_state.role == "Back Office":
            st.sidebar.info(f"Branch: **{st.session_state.branch_name}**")
        
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()
        return True
    
    # Show the login form
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
                    
                    # --- NEW: STORE BRANCH ID AND NAME ---
                    st.session_state["user_branch_id"] = user.Branch_ID 
                    if user.Branch_ID:
                        branch = db.query(models.Branch).filter(models.Branch.Branch_ID == user.Branch_ID).first()
                        st.session_state["branch_name"] = branch.Branch_Name if branch else "N/A"
                    else:
                        st.session_state["branch_name"] = "All Branches"
                    # --- END NEW ---
                    
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

    # --- Load Data (MODIFIED) ---
    @st.cache_data(ttl=600) 
    def load_data(branch_id_filter: str):
        """
        Wrapper to cache the main data load.
        If branch_id_filter is None, load for Owner (all).
        Otherwise, load for the specific branch.
        """
        print(f"CACHE MISS: Loading dashboard data for Branch: {branch_id_filter or 'All'}")
        db = next(get_db())
        try:
            # Pass the branch_id to the data manager
            data = get_all_sales_records_for_dashboard(db, branch_id_filter)
            
            # Load branches for the filter (Owners need all, Back Office only needs their own)
            if branch_id_filter:
                all_branches_list = [db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id_filter).first()]
            else:
                all_branches_list = get_all_branches(db)
                
            branch_map = {b.Branch_ID: b.Branch_Name for b in all_branches_list}
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
    
    # Branch Filter (If Owner, show multi-select. If Back Office, show read-only)
    if user_role == "Owner":
        branch_name_list = sorted(data['Branch_Name'].unique())
        selected_branches = st.sidebar.multiselect(
            "Select Branch",
            options=branch_name_list,
            default=branch_name_list
        )
    else:
        # Back Office is locked to their branch
        st.sidebar.text_input("Branch", value=st.session_state.branch_name, disabled=True)
        selected_branches = [st.session_state.branch_name]

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

    # --- Main Page Metrics ---
    total_revenue = filtered_data['Price_Negotiated_Final'].sum()
    total_sales = len(filtered_data)
    avg_sale = total_revenue / total_sales if total_sales > 0 else 0
    total_discount = filtered_data['Discount_Given'].sum()

    st.header("Key Metrics")
    
    # --- ROLE-BASED METRICS ---
    if user_role == "Owner":
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Revenue", f"₹{total_revenue:,.0f}")
        col2.metric("Total Units Sold", f"{total_sales}")
        col3.metric("Average Sale Value", f"₹{avg_sale:,.0f}")
        col4.metric("Total Discounts", f"₹{total_discount:,.0f}")
    
    elif user_role == "Back Office":
        col1, col2 = st.columns(2)
        col1.metric("Total Units Sold", f"{total_sales}")
        col2.metric("Average Sale Value", f"₹{avg_sale:,.0f}")
    
    st.markdown("---")

    # --- 5. INTERACTIVE DRILL-DOWN CHARTS ---
    st.header("Vehicle Sales Analysis")
    
    # Chart 1: Vehicles Sold by Model
    st.subheader("Sales by Model")
    st.info("Click on a bar in the 'Sales by Model' chart to drill down into colors.")
    model_selection = alt.selection_point(fields=['Model'], empty=True)
    chart_model = alt.Chart(filtered_data).mark_bar().encode(
        x=alt.X('Model', title='Vehicle Model', sort=None),
        y=alt.Y('count()', title='Number of Units Sold'),
        tooltip=['Model', 'count()'],
        color=alt.condition(model_selection, alt.value('orange'), alt.value('steelblue'))
    ).add_params(model_selection).interactive()

    # Chart 2: Drill-down to Color
    chart_color = alt.Chart(filtered_data).mark_bar().encode(
        x=alt.X('Paint_Color', title='Paint Color', sort=None),
        y=alt.Y('count()', title='Number of Units Sold'),
        tooltip=['Model', 'Paint_Color', 'count()']
    ).transform_filter(model_selection).properties(
        title="Sales by Color (for selected model)"
    )
    st.altair_chart(chart_model, use_container_width=True)
    st.altair_chart(chart_color, use_container_width=True)
    
    # Chart 3: Top Sales Staff
    st.subheader("Top Sales Staff (by Units Sold)")
    sales_staff_data = filtered_data.groupby('Sales_Staff')['id'].count().reset_index(name='Units Sold')
    chart_staff = alt.Chart(sales_staff_data).mark_bar().encode(
        x=alt.X('Sales_Staff', title='Sales Staff', sort='-y'),
        y=alt.Y('Units Sold', title='Number of Units Sold')
    ).interactive()
    st.altair_chart(chart_staff, use_container_width=True)


    st.markdown("---")
    st.header("Sales Records & DD Entry")

    # Define which columns are editable
    column_config = {
        'id': st.column_config.NumberColumn("Record ID", disabled=True),
        'DC_Number': st.column_config.TextColumn("DC Number", disabled=True),
        'Branch_Name': st.column_config.TextColumn("Branch", disabled=True),
        'Timestamp': st.column_config.DatetimeColumn("Date", format="D/M/YYYY", disabled=True),
        'Customer_Name': st.column_config.TextColumn("Customer", disabled=True),
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
        'DC_Number', 'Branch_Name', 'Timestamp', 'Customer_Name', 'Sales_Staff','Model','Variant', 'Price_ORP', 'Price_Negotiated_Final','Banker_Name', 'Payment_DownPayment'
        ,'Payment_DD', 'Payment_DD_Received', 'Payment_Shortfall'
    ]
    
    # --- CRITICAL FIX 1: Assign a unique key ---
    editor_key = "sales_data_editor"

    # --- ROLE-BASED DATA ---
    if user_role == "Owner":
        st.info("Owner View: Double-click a 'DD Received' cell to edit.")
        
        edited_df = st.data_editor(
            filtered_data,
            column_config=column_config,
            disabled=filtered_data.columns.drop('Payment_DD_Received'),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key=editor_key # Assign the key
        )
        
    elif user_role == "Back Office":
        st.info("Back Office View: Double-click a 'DD Received' cell to edit.")
        
        edited_df = st.data_editor(
            filtered_data[columns_to_show_back_office],
            column_config=column_config,
            disabled=filtered_data[columns_to_show_back_office].columns.drop('Payment_DD_Received'),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key=editor_key # Assign the key
        )
    
    else: # Fallback for any other role (Read-only)
        st.dataframe(filtered_data, hide_index=True, use_container_width=True)


    # --- 7. SAVE BUTTON LOGIC (Corrected) ---
    if user_role in ["Owner", "Back Office"]:
        if st.button("Save DD amount updates", type="primary"):
            
            # --- CRITICAL FIX 2: Read changes from session state ---
            # Do NOT compare DataFrames. Read the "edited_rows" dictionary.
            
            if editor_key in st.session_state and st.session_state[editor_key]["edited_rows"]:
                
                # edited_rows looks like: {10: {'Payment_DD_Received': 5000}}
                # The key (10) is the *index* of the row in the displayed DataFrame.
                edited_rows = st.session_state[editor_key]["edited_rows"]
                
                db = next(get_db())
                try:
                    num_updates = 0
                    
                    # Loop over the dictionary of edited rows
                    for row_index, changes in edited_rows.items():
                        
                        # Get the 'id' of the record from the original filtered_data
                        # using the index provided by the editor
                        record_id = int(filtered_data.iloc[row_index]['id'])
                        
                        # Check if our target column was the one edited
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