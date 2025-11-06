import streamlit as st
import pandas as pd
from database import get_db
from data_manager import update_dd_payment
import charts

def render_metrics(data, role):
    """Renders high-level KPIs based on user role."""
    total_sales = len(data)
    total_dd_expected = data['Payment_DD'].sum()
    total_dd_received = data['Payment_DD_Received'].sum()
    total_dd_pending = total_dd_expected - total_dd_received

    st.header("Key Metrics")
    if role == "Owner":
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
    else:
        cols = st.columns(3)
        cols[0].metric("Units Sold", f"{total_sales}")
        cols[1].metric("DD Expected", f"₹{total_dd_expected:,.0f}")
        cols[2].metric("DD Pending", f"₹{total_dd_pending:,.0f}")
    st.markdown("---")

def render_owner_view(data):
    """Renders the comprehensive 3-tab view for owners."""
    t1, t2, t3 = st.tabs(["💰 Financials", "🚗 Analytics", "📝 Data Entry"])
    with t1:
        st.subheader("Summary by Branch")
        branch_sum = data.groupby('Branch_Name').agg(
            Revenue=('Price_Negotiated_Final', 'sum'),
            Units=('id', 'count'),
            DD_Expected=('Payment_DD', 'sum'),
            DD_Received=('Payment_DD_Received', 'sum')
        ).reset_index()
        branch_sum['DD_Pending'] = branch_sum['DD_Expected'] - branch_sum['DD_Received']
        st.dataframe(branch_sum[['Branch_Name', 'Revenue', 'Units', 'DD_Pending']].style.format({'Revenue':'₹{:,.0f}','DD_Pending':'₹{:,.0f}'}), use_container_width=True, hide_index=True)
        
        render_banker_table(data)
        
        st.subheader("Revenue Trend")

    with t2:
        st.altair_chart(
            charts.plot_vehicle_drilldown(data), 
            use_container_width=True, 
            theme="streamlit"
        )
        st.subheader("Staff Performance")
        charts.plot_top_staff(data)

    with t3:
        render_data_editor(data, "Owner")

def render_backoffice_view(data):
    """Renders the focused view for back-office staff."""
    render_banker_table(data)
    render_data_editor(data, "Back Office")

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
    
    col_cfg = {
        'id': st.column_config.NumberColumn("ID", disabled=True),
        'Payment_DD': st.column_config.NumberColumn("DD Exp.", format="₹%.2f", disabled=True),
        'Payment_DD_Received': st.column_config.NumberColumn("DD Rec. (Edit)", format="₹%.2f", disabled=False),
        'Live_Shortfall': st.column_config.NumberColumn("Pending", format="₹%.2f", disabled=True)
    }
    cols_bo = ['id', 'DC_Number', 'Branch_Name', 'Timestamp', 'Customer_Name', 'Sales_Staff', 'Payment_DD', 'Payment_DD_Received', 'Live_Shortfall']
    
    key = "sales_editor"
    edited_df = st.data_editor(
        data if role == "Owner" else data[cols_bo],
        column_config=col_cfg,
        disabled=[c for c in data.columns if c != 'Payment_DD_Received'],
        use_container_width=True, hide_index=True, key=key
    )

    if st.button("Save DD Updates", type="primary"):
        if key in st.session_state and st.session_state[key]["edited_rows"]:
            db = next(get_db())
            try:
                updates = 0
                for idx, changes in st.session_state[key]["edited_rows"].items():
                    if 'Payment_DD_Received' in changes:
                        # Use the index to find the original record ID in the filtered data
                        record_id = int(data.iloc[int(idx)]['id'])
                        update_dd_payment(db, record_id, float(changes['Payment_DD_Received']))
                        updates += 1
                st.success(f"Updated {updates} records!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
            finally:
                db.close()
        else:
            st.info("No changes detected.")