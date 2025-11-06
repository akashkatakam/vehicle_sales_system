import altair as alt
import streamlit as st

alt.theme.active = "streamlit"
def plot_revenue_trend(data):
    time_sales = data.set_index('Timestamp').resample('D')['Price_Negotiated_Final'].sum().reset_index()
    chart = alt.Chart(time_sales).mark_line(point=True).encode(
        x=alt.X('Timestamp', title='Date'),
        y=alt.Y('Price_Negotiated_Final', title='Total Revenue (₹)'),
        tooltip=[alt.Tooltip('Timestamp', format='%Y-%m-%d'), alt.Tooltip('Price_Negotiated_Final', format=',.0f')]
    ).interactive()
    st.altair_chart(chart, use_container_width=True)

def plot_vehicle_drilldown(data):
    # --- 1. Create Selection ---
    # We select based on the 'Model' field. 
    # 'empty=True' means nothing is highlighted initially (all full opacity).
    variant_selection = alt.selection_point(fields=['Variant'], empty=True)

    # --- 2. Top Chart: Models Stacked by Variant ---
    chart_model = alt.Chart(data).mark_bar().encode(
        x=alt.X('Model', title='Vehicle Model', sort='-y'),
        y=alt.Y('count()', title='Total Units Sold'),
        # Stack by Variant
        color=alt.Color('Variant', title='Variant Breakdown'),
        # Use opacity to highlight selection instead of color
        opacity=alt.condition(variant_selection, alt.value(1.0), alt.value(0.3)),
        tooltip=['Model', 'Variant', 'count()']
    ).add_params(
        variant_selection
    ).properties(
        title="Sales by Model (Stacked by Variant - Click to filter below)",
        height=300
    )

    # --- 3. Bottom Chart: Sales by Color ---
    chart_color = alt.Chart(data).mark_bar().encode(
        x=alt.X('Paint_Color', title='Paint Color', sort='-y'),
        y=alt.Y('count()', title='Units Sold'),
        tooltip=['Model', 'Paint_Color', 'count()'],
        color=alt.value('#FF4B4B') # Single color for clarity
    ).transform_filter(
        variant_selection # Filter based on the top chart's selection
    ).properties(
        title="Sales by Paint Color (Filtered by Model)",
        height=300
    )

    # 4. Return combined chart
    return (chart_model & chart_color).resolve_scale(color='independent')

def plot_top_staff(data):
    staff_data = data.groupby('Sales_Staff')['id'].count().reset_index(name='Units')
    staff_data = staff_data.sort_values('Units', ascending=False)
    
    chart = alt.Chart(staff_data).mark_bar().encode(
        x=alt.X('Units', title='Units Sold'),
        y=alt.Y('Sales_Staff', title='Sales Staff', sort='-x'),
        tooltip=['Sales_Staff', 'Units']
    ).interactive()
    st.altair_chart(chart, use_container_width=True)