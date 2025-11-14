import streamlit as st
import pandas as pd
from database import get_db
from data_manager import update_dd_payment, update_insurance_tr_status
import charts

def render_metrics(data, role):
    """Renders high-level KPIs based on user role."""
    total_sales = len(data)
    total_dd_expected = data['Payment_DD'].sum()
    total_dd_received = data['Payment_DD_Received'].sum()
    total_dd_pending = total_dd_expected - total_dd_received

    with st.container(border=True):
        if role == "Owner":
            st.header("Key Metrics")
            cols = st.columns(5)
            cols[0].metric("Revenue", f"₹{data['Price_Negotiated_Final'].sum():,.0f}",width="content")
            cols[1].metric("Units Sold", f"{total_sales}")
            cash_sales_count = len(data[data['Banker_Name'] == 'N/A (Cash Sale)'])
            cols[2].metric("Cash Sale", f"{cash_sales_count}")
            cols[3].metric("Discounts", f"₹{data['Discount_Given'].sum():,.0f}",width="content")
            cols[4].metric("DD Pending", f"₹{total_dd_pending:,.0f}",width="content")
            total_hp_collected = data['Charge_HP_Fee'].sum()
            total_incentive_collected = data['Charge_Incentive'].sum()
            total_pr_count = data['pr_fee_checkbox'].sum()
            st.markdown("---")
            col6, col7, col8,col9,col10 = st.columns(5)
            col6.metric("Total PR", f"{int(total_pr_count)}")
            col7.metric("Total HP Fees", f"₹{(total_hp_collected)}")
            col8.metric("Total Finance Incentives", f"₹{(total_incentive_collected)}")
            finance_sales_count = len(data[data['Banker_Name'] != 'N/A (Cash Sale)'])
            col9.metric("Total Finance sale count", f"{finance_sales_count}")
        elif role=="Back Office":
            st.header("Key Metrics")
            cols = st.columns(3)
            cols[0].metric("Units Sold", f"{total_sales}")
            cols[1].metric("DD Expected", f"₹{total_dd_expected:,.0f}")
            cols[2].metric("DD Pending", f"₹{total_dd_pending:,.0f}")
        st.markdown("---")

def render_owner_view(data):
    """Renders the comprehensive 3-tab view for owners."""
    t1, t2, t3 = st.tabs(["💰 Financials", "🚗 Analytics", "📝 Data Entry"])
    with t1:
        c_left, c_right = st.columns([3, 2])
        
        with c_left:
            with st.container(border=True):
                st.subheader("Summary by Branch")
                bsum = data.groupby('Branch_Name').agg(
                    Rev=('Price_Negotiated_Final', 'sum'), Units=('id', 'count'),
                    Pending=('Live_Shortfall', 'sum')
                ).reset_index()
                bdisp = bsum.copy()
                bdisp['Rev'] = bdisp['Rev'].apply(lambda x: f"₹{(x)}")
                bdisp['Pending'] = bdisp['Pending'].apply(lambda x: f"₹{(x)}")
                st.dataframe(bdisp, use_container_width=True, hide_index=True)
        
        with c_right:
             with st.container(border=True):
                render_banker_table(data)


    # --- TAB 2: Analytics ---
    with t2:
        with st.container(border=True):
            st.subheader("Vehicle Sales Drill-down")
            charts.plot_vehicle_drilldown(data)
        
        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1:
                charts.plot_sales_by_type(data)
            with col2:
                # Placeholder for another chart, e.g., Movement by default
                move_data = data.groupby('Movement_Category')['id'].count().reset_index(name='Units')
                st.dataframe(move_data, use_container_width=True, hide_index=True)
        with st.container(border=True):
            st.subheader("Top Sales Staff")
            charts.plot_top_staff(data)

    with t3:
        render_data_editor(data, "Owner")

def render_backoffice_view(data):
    """Renders the focused view for back-office staff."""
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1: render_banker_table(data)
    render_data_editor(data, "Back Office")

def render_insurance_tr_view(data: pd.DataFrame):
    """
    Renders the focused view for the Insurance/TR team.
    Shows records that have completed PDI but not TR.
    """
    st.header("Insurance & TR Processing Queue")
    
    # 1. Filter data to the relevant queue
    # We only want to see records that are 'PDI Complete' or 'Insurance Done'
    statuses_to_show = ['PDI Complete', 'Insurance Done']
    queue_df = data[data['fulfillment_status'].isin(statuses_to_show)].copy()
    
    if queue_df.empty:
        st.info("No vehicles are currently pending Insurance or TR processing.")
        return

    # 2. Define columns for the data editor
    columns_to_show = [
        'id',
        'DC_Number',
        'Customer_Name',
        'Model',
        'Variant',
        'Paint_Color',
        'chassis_no',
        'engine_no',
        'is_insurance_done',
        'is_tr_done',
        'has_dues',
        'has_double_tax'
    ]
    
    # Filter the DataFrame
    df_to_show = queue_df[columns_to_show].reset_index(drop=True)

    # 3. Configure the data editor
    column_config = {
        'id': st.column_config.NumberColumn("ID", disabled=True),
        'DC_Number': st.column_config.TextColumn("DC No.", disabled=True),
        'Customer_Name': st.column_config.TextColumn("Customer", disabled=True),
        'Model': st.column_config.TextColumn("Model", disabled=True),
        'chassis_no': st.column_config.TextColumn("Chassis", disabled=True),
        'engine_no': st.column_config.TextColumn("Engine", disabled=True),
        
        # These are the editable columns
        'is_insurance_done': st.column_config.CheckboxColumn("Insurance Done?"),
        'is_tr_done': st.column_config.CheckboxColumn("TR Done?"),
        'has_dues': st.column_config.CheckboxColumn("Dues?"),
        'has_double_tax': st.column_config.CheckboxColumn("Double Tax?"),
    }
    
    # Define which columns are disabled
    disabled_cols = [
        'id', 'DC_Number', 'Customer_Name', 'Model', 'chassis_no', 'engine_no'
    ]
    
    editor_key = "insurance_tr_editor"
    
    edited_df = st.data_editor(
        df_to_show,
        column_config=column_config,
        disabled=disabled_cols,
        hide_index=True, 
        use_container_width=True, 
        key=editor_key
    )

    # 4. Add the Save button
    if st.button("Save Insurance/TR Updates", type="primary"):
        if editor_key in st.session_state and st.session_state[editor_key]["edited_rows"]:
            db = next(get_db())
            try:
                updates = 0
                # Get the changes from session state
                edited_rows = st.session_state[editor_key]["edited_rows"]
                
                for idx, changes in edited_rows.items():
                    # Get the 'id' of the record from our filtered DataFrame
                    record_id = int(df_to_show.iloc[int(idx)]['id'])
                    
                    # 'changes' is a dict like {'is_insurance_done': True}
                    # We pass this directly to our new data_manager function
                    update_insurance_tr_status(db, record_id, changes)
                    updates += 1
                    
                st.success(f"Updated {updates} records!")
                st.cache_data.clear() # Clear the cache to refresh data
                st.rerun()
            except Exception as e: 
                st.error(f"Save failed: {e}")
            finally: 
                db.close()
        else:
            st.info("No changes to save.")

# --- Helper Components ---

def render_banker_table(data):
    st.subheader("DD Pending by Banker")
    banker_data = data[(data['Banker_Name'].notna()) & (data['Banker_Name'] != '') & (data['Live_Shortfall'] > 0)]
    if not banker_data.empty:
        summary = banker_data.groupby('Banker_Name').agg(Pending=('Live_Shortfall', 'sum'), Units=('id', 'count')).reset_index().sort_values('Pending', ascending=False)
        st.dataframe(summary.style.format({'Pending': '₹{:,.0f}'}), use_container_width=True, hide_index=True)
    else:
        st.info("No pending DD amounts for bankers.")

def render_data_editor(data, role):
    st.markdown("---")
    st.header("Sales Records & DD Entry")
    
    # --- NEW: Pills Filter for Banker ---
    banker_options = sorted([str(b) for b in data['Banker_Name'].unique() if pd.notna(b) and b != ''])
    selected_bankers = st.pills("Filter by Financier:", options=banker_options, selection_mode="multi", key="banker_pills",default=banker_options)
    
    if selected_bankers:
        filtered_table_data = data[data['Banker_Name'].isin(selected_bankers)].copy().reset_index(drop=True)
    else:
        filtered_table_data = data.copy().reset_index(drop=True)

    column_config = {
        'id': st.column_config.NumberColumn("ID", disabled=True),
        'DC_Number': st.column_config.TextColumn("DC No.", disabled=True),
        'Payment_DD': st.column_config.NumberColumn("DD Exp.", format="₹%.2f", disabled=True),
        'Payment_DD_Received': st.column_config.NumberColumn("DD Rec. (Actual)", format="₹%.2f", disabled=False),
        'Live_Shortfall': st.column_config.NumberColumn("Pending", format="₹%.2f", disabled=True)
    }
    cols_back_office = ['DC_Number', 'Branch_Name', 'Timestamp', 'Customer_Name', 'Model','Variant','Sales_Staff','Banker_Name','Payment_DownPayment','Price_ORP','Payment_DD', 'Payment_DD_Received', 'Live_Shortfall']
    
    editor_key = "sales_editor"
    # Determine which DF and columns to show based on role
    if role == "Owner":
        df_to_show = filtered_table_data
        disabled_cols = [c for c in df_to_show.columns if c != 'Payment_DD_Received']
        st.info("Owner View: Edit 'DD Rec.' to update.")
    else:
        df_to_show = filtered_table_data[cols_back_office]
        disabled_cols = [c for c in df_to_show.columns if c != 'Payment_DD_Received']
        st.info("Back Office View: Edit 'DD Rec.' to update.")

    edited_df = st.data_editor(
        df_to_show,
        column_config=column_config,
        disabled=disabled_cols,
        hide_index=True, use_container_width=True, key=editor_key
    )

    if st.button("Save DD Updates", type="primary"):
        if editor_key in st.session_state and st.session_state[editor_key]["edited_rows"]:
            db = next(get_db())
            try:
                updates = 0
                for idx, changes in st.session_state[editor_key]["edited_rows"].items():
                    if 'Payment_DD_Received' in changes:
                        # CRITICAL: Use the ID from the *filtered* table data
                        rid = int(filtered_table_data.iloc[int(idx)]['id'])
                        update_dd_payment(db, rid, float(changes['Payment_DD_Received']))
                        updates += 1
                st.success(f"Updated {updates} records!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e: st.error(f"Save failed: {e}")
            finally: db.close()
        else:
            st.info("No changes to save.")