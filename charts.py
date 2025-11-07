import altair as alt
import streamlit as st

alt.theme.active = "streamlit"
COLOR_SCALE = alt.Scale(domain=['Variant 1', 'Variant 2', 'Variant 3'], range=['#FF4B4B', '#FF8C8C', '#FFB3B3'])
def plot_revenue_trend(data):
    time_sales = data.set_index('Timestamp').resample('D')['Price_Negotiated_Final'].sum().reset_index()
    chart = alt.Chart(time_sales).mark_line(point=True).encode(
        x=alt.X('Timestamp', title='Date'),
        y=alt.Y('Price_Negotiated_Final', title='Total Revenue (₹)'),
        tooltip=[alt.Tooltip('Timestamp', format='%Y-%m-%d'), alt.Tooltip('Price_Negotiated_Final', format=',.0f')]
    ).interactive()
    st.altair_chart(chart, use_container_width=True)

def plot_vehicle_drilldown(data):
    """
    Creates a stacked bar chart of Models by Variant,
    which filters a chart of Colors stacked by Movement Category.
    """
    # 1. Create the selection
    model_selection = alt.selection_point(fields=['Model'], empty=True)

    # 2. Top Chart: Models Stacked by Variant
    chart_model = alt.Chart(data).mark_bar().encode(
        x=alt.X('Model', title='Vehicle Model', sort='-y'),
        y=alt.Y('count()', title='Total Units Sold'),
        color=alt.Color('Variant', title='Variant'),
        opacity=alt.condition(model_selection, alt.value(1.0), alt.value(0.3)),
        tooltip=['Model', 'Variant', 'count()']
    ).add_params(
        model_selection
    ).properties(
        title="Sales by Model & Variant (Click to filter below)",
        height=300
    ).interactive()

    # 3. Bottom Chart: Colors Stacked by Movement Category
    chart_color_movement = alt.Chart(data).mark_bar().encode(
        x=alt.X('Paint_Color', title='Paint Color', sort='-y'),
        y=alt.Y('count()', title='Units Sold'),
        
        # --- UPDATED STACK ---
        color=alt.Color('Movement_Category', title='Movement'),
        
        tooltip=['Model', 'Paint_Color', 'Movement_Category', 'count()']
    ).transform_filter(
        model_selection # Filtered by the top chart
    ).properties(
        title="Sales by Color (Filtered by Model, Stacked by Movement)",
        height=300
    )

    # 4. Return combined chart
    st.altair_chart((chart_model & chart_color_movement).resolve_scale(color='independent'))

def plot_top_staff(data):
    staff_data = data.groupby('Sales_Staff')['id'].count().reset_index(name='Units')
    staff_data = staff_data.sort_values('Units', ascending=False)
    
    chart = alt.Chart(staff_data).mark_bar().encode(
        x=alt.X('Units', title='Units Sold'),
        y=alt.Y('Sales_Staff', title='Sales Staff', sort='-x'),
        tooltip=['Sales_Staff', 'Units']
    ).interactive()
    st.altair_chart(chart,width='stretch',theme='streamlit')

def plot_sales_by_type(data):
    """Plots a donut chart for MC vs SC."""
    type_summary = data.groupby('Vehicle_Type')['id'].count().reset_index(name='Count')
    
    base = alt.Chart(type_summary).encode(
        theta=alt.Theta("Count", stack=True),
        color=alt.Color("Vehicle_Type", title="Vehicle Class"),
        tooltip=["Vehicle_Type", "Count"]
    )
    
    pie = base.mark_arc(outerRadius=120)
    text = base.mark_text(radius=140).encode(
        text=alt.Text("Count", format=".0f"),
        order=alt.Order("Vehicle_Type"),
        color=alt.value("black")
    )
    
    st.altair_chart(pie + text, use_container_width=True)