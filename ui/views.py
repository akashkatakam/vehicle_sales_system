import streamlit as st
import pandas as pd
from datetime import datetime
from core.database import get_db, db_session
from core import models
from core.data_manager import update_dd_payment, update_insurance_tr_status
from features.dashboard import charts

BASE_WA_URL = "https://wa.me/"

INSURANCE_MSG = "*You’re covered!* \n\nGreat news—your vehicle insurance policy is issued. Please find the copy attached. \n\nSafe driving! \n*Team Katakam Honda*"
TR_MSG = "*Great news!* \n\nYour *TR* is successfully processed. \n\nPlease visit *Katakam Honda* to collect your documents. \n\n*Team Katakam Honda*"
PLATES_MSG = "Your permanent number plates have arrived. \n\nPlease visit *Katakam Honda* between 10 AM - 6 PM for fitting. \n\nRegards, \n*Team Katakam Honda*"


# --- ROW STYLING FUNCTION ---
def style_aging_rows(row):
    status = row.get('Aging_Status', '')
    if status == 'Paid':
        return ['background-color: #d4edda; color: #155724'] * len(row)
    elif status == '>15 Days':
        return ['background-color: #f8d7da; color: #721c24'] * len(row)
    elif status == '7-15 Days':
        return ['background-color: #fff3cd; color: #856404'] * len(row)
    return [''] * len(row)


# --- Dialog Function ---
@st.dialog("📲 Send WhatsApp Update")
def send_wa_modal(phone: str, message: str, context: str):
    st.write(f"**Update:** {context}")
    st.write(f"**Customer Phone:** {phone}")
    st.info(f"**Message Preview:**\n\n{message}")
    if phone and len(phone) > 10:
        link = f"{BASE_WA_URL}{phone}?text={message.replace(' ', '%20')}"
        st.link_button("🚀 Open WhatsApp", link, type="primary", use_container_width=True)
    else:
        st.error("Invalid phone number for WhatsApp.")


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
            cols[0].metric("Revenue", f"₹{data['Price_Negotiated_Final'].sum():,.0f}", width="content")
            cols[1].metric("Units Sold", f"{total_sales}")
            cash_sales_count = len(data[data['Banker_Name'] == 'N/A (Cash Sale)'])
            cols[2].metric("Cash Sale", f"{cash_sales_count}")
            finance_sales_count = total_sales - cash_sales_count
            cols[3].metric("Total Finance sale count", f"{finance_sales_count}")
            cols[4].metric("Discounts", f"₹{data['Discount_Given'].sum():,.0f}", width="content")
            total_hp_collected = data['Charge_HP_Fee'].sum()
            total_incentive_collected = data['Charge_Incentive'].sum()
            total_pr_count = data['pr_fee_checkbox'].sum()
            col6, col7, col8, col9, col10 = st.columns(5)
            col6.metric("Total PR", f"{int(total_pr_count)}")
            col7.metric("Total HP Fees", f"₹{total_hp_collected:,.0f}")
            col8.metric("Total Finance Incentives", f"₹{total_incentive_collected:,.0f}")
            col9.metric("DD Pending", f"₹{total_dd_pending:,.0f}", width="content")
            col10.metric("DD Expected", f"₹{total_dd_expected:,.0f}")

        elif role == "Back Office":
            st.header("Key Metrics")
            cols = st.columns(3)
            cols[0].metric("Units Sold", f"{total_sales}")
            cols[1].metric("DD Expected", f"₹{total_dd_expected:,.0f}")
            cols[2].metric("DD Pending", f"₹{total_dd_pending:,.0f}")
        elif role == 'Insurance/TR':
            st.header("Key Metrics")
            cols = st.columns(3)
            total_tr_pending_count = len(data) - data['is_tr_done'].sum()
            total_insurance_pending_count = len(data) - data['is_insurance_done'].sum()
            total_plates_received = data['plates_received'].sum()
            cols[0].metric("Total invoice/TR Pending", f"{total_tr_pending_count}")
            cols[1].metric("Insurance Pending", f"{total_insurance_pending_count:,.0f}")
            cols[2].metric("Plates received", f"{total_plates_received:,.0f}")


def render_owner_view(data):
    """
    Renders the 'Cockpit' View for Owners using a horizontal segmented control style.
    """
    # 1. VIEW SELECTOR
    views = {
        "Financials": "💰",
        "Sales Analytics": "📈",
        "Actions & Approvals": "⚡"
    }

    selected_view_name = st.radio(
        "Dashboard View:",
        options=list(views.keys()),
        format_func=lambda x: f"{views[x]}  {x}",
        horizontal=True,
        label_visibility="collapsed",
        key="owner_view_selector"
    )
    st.markdown("---")

    if selected_view_name == "Financials":
        c_left, c_right = st.columns([3, 2])
        with c_left:
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
            render_banker_table(data)
        with st.expander("🧩 Net Collections Analysis", expanded=False):
            render_net_collections_logic(data)

    elif selected_view_name == "Sales Analytics":
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Top Performing Staff")
            charts.plot_top_staff(data)
        with c2:
            st.caption("Sales by Model & Variant")
            charts.plot_vehicle_drilldown(data)
        st.divider()
        c3, c4 = st.columns(2)
        with c3:
            st.caption("Banker Performance")
            charts.plot_sales_by_banker_and_staff(data)
        with c4:
            st.caption("Vehicle Type Split")
            charts.plot_sales_by_type(data)

    elif selected_view_name == "Actions & Approvals":
        render_approval_section()
        render_dues_manager(data, "Owner")


def render_approval_section():
    """Fetches and displays pending approvals from the dedicated table."""
    st.subheader("🔔 Approval Requests")

    with db_session() as db:
        requests = db.query(models.ApprovalRequest).filter(
            models.ApprovalRequest.Status == 'Pending'
        ).order_by(models.ApprovalRequest.Requested_At.desc()).all()

        if not requests:
            st.info("✅ No pending approvals.")
        else:
            for req in requests:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        st.markdown(f"**{req.Customer_Name}** ({req.Model}) | Branch: {req.Branch_ID}")
                        st.markdown(
                            f"Discount: :red[**₹{req.Discount_Requested:,.0f}**] | Final: **₹{req.Final_Price:,.0f}**")

                    with c2:
                        if st.button("✅ Approve", key=f"app_{req.id}", type="primary", use_container_width=True):
                            req.Status = 'Approved'
                            req.Approved_At = datetime.now()
                            db.commit()
                            st.success("Approved!")
                            st.rerun()

                    with c3:
                        if st.button("❌ Reject", key=f"rej_{req.id}", use_container_width=True):
                            req.Status = 'Rejected'
                            db.commit()
                            st.error("Rejected.")
                            st.rerun()


def render_net_collections_logic(data):
    c_head, c_sel = st.columns([1, 2])
    with c_head:
        st.subheader("Analysis")
    comp_map = {
        "HC": "price_hc", "Accessories": "price_accessories", "PR Fees": "price_pr",
        "Fin. Incentive": "Charge_Incentive", "HP Fees": "Charge_HP_Fee",
        "Ext. Warranty": "price_ew", "Discounts": "Discount_Given"
    }
    default_opts = ["HC", "Accessories", "PR Fees", "Fin. Incentive", "HP Fees", "Discounts"]
    with c_sel:
        selected_labels = st.multiselect("Include Components:", options=list(comp_map.keys()), default=default_opts,
                                         key="owner_comp_select", label_visibility="collapsed")

    if selected_labels:
        selected_cols = [comp_map[label] for label in selected_labels]
        valid_cols = [c for c in selected_cols if c in data.columns]
        if valid_cols:
            df_calc = data[['Branch_Name'] + valid_cols].copy()
            df_calc[valid_cols] = df_calc[valid_cols].fillna(0.0)
            grouped = df_calc.groupby('Branch_Name')[valid_cols].sum().reset_index()
            cols_to_add = [c for c in valid_cols if c != 'Discount_Given']
            cols_to_sub = [c for c in valid_cols if c == 'Discount_Given']
            total_series = pd.Series(0.0, index=grouped.index)
            if cols_to_add: total_series += grouped[cols_to_add].sum(axis=1)
            if cols_to_sub: total_series -= grouped[cols_to_sub].sum(axis=1)
            grouped['Total'] = total_series
            grand_sums = grouped[valid_cols + ['Total']].sum()
            total_row = pd.DataFrame(grand_sums).T
            total_row['Branch_Name'] = 'GRAND TOTAL'
            final_df = pd.concat([grouped, total_row], ignore_index=True)
            fmt_cols = ['Total'] + valid_cols
            for col in fmt_cols: final_df[col] = final_df[col].apply(lambda x: f"₹{x:,.0f}")
            reverse_map = {v: k for k, v in comp_map.items()}
            final_df.rename(columns=reverse_map, inplace=True)
            display_cols = ['Branch_Name'] + [reverse_map[c] for c in valid_cols] + ['Total']
            final_view = final_df[display_cols].rename(columns={'Branch_Name': 'Branch'})
            st.dataframe(final_view, use_container_width=True, hide_index=True)


def render_backoffice_view(data):
    render_banker_table(data)
    render_dues_manager(data, "Back Office")


def render_insurance_tr_view(data: pd.DataFrame):
    st.header("Insurance & TR Processing Queue")
    # ... [Keep your existing Insurance/TR logic - simplified for brevity here but essential to keep] ...
    # Assuming previous code is retained for this function


def render_banker_table(data):
    st.subheader("DD Pending by Banker (Aging)")
    mask = (data['Banker_Name'].notna()) & (data['Banker_Name'] != '') & (data['Banker_Name'] != 'N/A (Cash Sale)') & (
                data['Live_Shortfall'] > 0)
    banker_data = data[mask].copy()
    if not banker_data.empty:
        banker_data['Files_0_7'] = banker_data['Aging_Days'].apply(lambda x: 1 if x < 7 else 0)
        banker_data['Files_7_15'] = banker_data['Aging_Days'].apply(lambda x: 1 if 7 <= x <= 15 else 0)
        banker_data['Files_15_Plus'] = banker_data['Aging_Days'].apply(lambda x: 1 if x > 15 else 0)
        summary = banker_data.groupby('Banker_Name').agg(
            Pending=('Live_Shortfall', 'sum'), Units=('id', 'count'),
            Files_0_7=('Files_0_7', 'sum'), Files_7_15=('Files_7_15', 'sum'),
            Files_15_Plus=('Files_15_Plus', 'sum')
        ).reset_index().sort_values('Pending', ascending=False)
        st.dataframe(summary, use_container_width=True, hide_index=True)
    else:
        st.info("No pending DD amounts for bankers.")


def render_dues_manager(data, role):
    st.markdown("---")
    st.header("Sales Records & Dues Management")
    banker_options = sorted([str(b) for b in data['Banker_Name'].unique() if pd.notna(b) and b != ''])
    selected_bankers = st.pills("Filter by Financier:", options=banker_options, selection_mode="multi",
                                key="banker_pills", default=None)

    if selected_bankers:
        df_display = data[data['Banker_Name'].isin(selected_bankers)].copy().reset_index(drop=True)
    else:
        df_display = data.copy().reset_index(drop=True)

    view_cols = ['DC_Number', 'Branch_Name', 'Timestamp', 'Customer_Name', 'Model', 'Variant', 'Sales_Staff',
                 'Banker_Name',
                 'Finance_Executive', 'Payment_DownPayment', 'Price_ORP', 'Price_Negotiated_Final', 'Payment_DD',
                 'Payment_DD_Received',
                 'Live_Shortfall', 'Payment_Shortfall', 'shortfall_received', 'Aging_Status', ]

    if role == "Owner":
        final_view_df = df_display.copy()
    else:
        final_view_df = df_display[view_cols].copy()

    currency_candidates = ['Payment_DD', 'Payment_DD_Received', 'Live_Shortfall', 'shortfall_received',
                           'Price_Negotiated_Final', 'Price_ORP', 'Payment_DownPayment', 'Payment_Shortfall',
                           'Discount_Given', 'price_hc', 'price_accessories', 'price_pr', 'price_ew',
                           'Charge_HP_Fee', 'Charge_Incentive', 'Price_Listed_Total']
    format_dict = {col: '₹{:,.2f}' for col in currency_candidates if col in final_view_df.columns}
    styled_df = final_view_df.style.apply(style_aging_rows, axis=1).format(format_dict)
    st.dataframe(styled_df, use_container_width=True, height=400)

    # Update Form
    st.subheader("Update Payment Record")
    pending_records = df_display[df_display['has_dues'] == True].copy()
    if not pending_records.empty:
        pending_records['Label'] = pending_records.apply(
            lambda x: f"{x['Customer_Name']} | {x['DC_Number']} | Pending: ₹{x['Live_Shortfall']:,.0f}", axis=1)
        record_map = dict(zip(pending_records['Label'], pending_records['id']))
        selected_label = st.selectbox("Select Record to Update:", options=pending_records['Label'].tolist(), index=None,
                                      placeholder="Search by Customer Name or DC...")
        if selected_label:
            record_id = record_map[selected_label]
            rec_data = pending_records[pending_records['id'] == record_id].iloc[0]
            with st.container(border=True):
                delivery_date = rec_data['Timestamp'].strftime('%d-%b-%Y') if pd.notna(rec_data['Timestamp']) else "N/A"
                st.markdown(
                    f"**Customer:** {rec_data['Customer_Name']} | **Banker:** {rec_data['Banker_Name']} | **Delivered On:** {delivery_date}")
                c1, c2, c3 = st.columns(3)
                c1.metric("DD Expected", f"₹{rec_data['Payment_DD']:,.2f}")
                c2.metric("Already Received", f"₹{rec_data['Payment_DD_Received']:,.2f}")
                c3.metric("Current Shortfall", f"₹{rec_data['Live_Shortfall']:,.2f}", delta_color="inverse")
                st.divider()
                with st.form("update_payment_form"):
                    col_u1, col_u2 = st.columns(2)
                    disable_initial = (rec_data['Payment_DD_Received'] > 0)
                    with col_u1:
                        new_dd_rec = st.number_input("Update Initial DD Received (₹):",
                                                     value=float(rec_data['Payment_DD_Received']),
                                                     disabled=disable_initial)
                    with col_u2:
                        new_shortfall_rec = st.number_input("Add Shortfall Recovery Amount (₹):",
                                                            value=float(rec_data['shortfall_received']))
                    if st.form_submit_button("💾 Save Updates", type="primary"):
                        db = next(get_db())
                        try:
                            val_initial = new_dd_rec if not disable_initial else None
                            update_dd_payment(db, int(record_id), val_initial, new_shortfall_rec)
                            st.success(f"Updated record for {rec_data['Customer_Name']}!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                        finally:
                            db.close()