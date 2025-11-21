# akashkatakam/vehicle_sales_system/vehicle_sales_system-a25fe511bb8837d2b7b2d191078cc15650e0c6e0/charts.py

import altair as alt
import streamlit as st

alt.theme.active = "streamlit"
# Define a custom color palette based on Streamlit's primary color and secondary background
PRIMARY_COLOR = '#FF4B4B'
SECONDARY_COLOR = '#F1F2D6'
COLOR_SCALE_MOV = alt.Scale(domain=['Slow Moving', 'Fast Moving', 'N/A'], range=['#CCCCCC', PRIMARY_COLOR, '#B00000'])
COLOR_SCALE_TYPE = alt.Scale(domain=['MC', 'SC', 'Other'], range=[PRIMARY_COLOR, '#FF8C8C', '#B0B0B0'])


# --- NEW CHART FUNCTION ---
def plot_sales_by_banker_and_staff(data):
    """
    Plots a stacked bar chart showing units sold by Financier (Banker Name), 
    segmented by the responsible Sales Staff.
    """
    # Filter out cash sales for this finance-focused chart
    banker_data = data[data['Banker_Name'] != 'N/A (Cash Sale)'].copy()
    
    # Calculate totals per banker to sort the Y-axis
    banker_summary = banker_data.groupby('Banker_Name').size().reset_index(name='TotalUnits')
    banker_names_sorted = banker_summary.sort_values('TotalUnits', ascending=False)['Banker_Name'].tolist()

    chart = alt.Chart(banker_data).mark_bar().encode(
        y=alt.Y('Banker_Name', title='Financier/Banker Name', sort=banker_names_sorted),
        x=alt.X('count()', title='Units Sold'),
        color=alt.Color('Sales_Staff', title='Sales Staff'),
        tooltip=[
            'Banker_Name', 
            'Sales_Staff', 
            alt.Tooltip('count()', title='Units Sold by Staff')
        ]
    ).properties(
        title="Units Sold by Financier (Segmented by Sales Staff)"
    ).interactive()

    st.altair_chart(chart, use_container_width=True)
# --- END NEW CHART FUNCTION ---

def plot_vehicle_drilldown(data):
    """
    Creates a stacked bar chart of Models by Variant,
    which filters a chart of Colors stacked by Movement Category.
    """
    # 1. Create the selection
    model_selection = alt.selection_point(fields=['Model'], empty=True, name="ModelSelect")

    # 2. Top Chart: Models Stacked by Variant
    chart_model = alt.Chart(data).mark_bar().encode(
        x=alt.X('Model', title='Vehicle Model', sort='-y'),
        y=alt.Y('count()', title='Total Units Sold'),
        color=alt.Color('Variant', title='Variant'),
        opacity=alt.condition(model_selection, alt.value(1.0), alt.value(0.3)),
        tooltip=['Model', 'Variant', alt.Tooltip('count()', title='Units')]
    ).add_params(
        model_selection
    ).properties(
        title="Sales by Model & Variant (Click Model to filter below)",
        height=300
    ).interactive()

    # 3. Bottom Chart: Colors Stacked by Movement Category
    chart_color_movement = alt.Chart(data).mark_bar().encode(
        x=alt.X('Paint_Color', title='Paint Color', sort='-y'),
        y=alt.Y('count()', title='Units Sold'),
        
        # --- UPDATED STACK ---
        color=alt.Color('Movement_Category', title='Movement', scale=COLOR_SCALE_MOV),
        
        tooltip=['Model', 'Paint_Color', 'Movement_Category', alt.Tooltip('count()', title='Units')]
    ).transform_filter(
        model_selection # Filtered by the top chart
    ).properties(
        title="Sales by Color and Stock Movement",
        height=300
    )

    # 4. Return combined chart
    st.altair_chart((chart_model & chart_color_movement).resolve_scale(color='independent'), use_container_width=True)

def plot_top_staff(data):
    """Plots a horizontal bar chart for top sales staff by units sold."""
    staff_data = data.groupby('Sales_Staff')['id'].count().reset_index(name='Units')
    staff_data = staff_data.sort_values('Units', ascending=False).head(10) # Top 10 only
    
    chart = alt.Chart(staff_data).mark_bar(color=PRIMARY_COLOR).encode(
        x=alt.X('Units', title='Units Sold', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('Sales_Staff', title='Sales Staff', sort='-x'),
        tooltip=['Sales_Staff', 'Units']
    ).properties(
        title="Top 10 Sales Staff by Units"
    ).interactive()
    st.altair_chart(chart, use_container_width=True)

def plot_sales_by_type(data):
    """Plots a donut chart for MC vs SC."""
    type_summary = data.groupby('Vehicle_Type')['id'].count().reset_index(name='Count')
    
    base = alt.Chart(type_summary).encode(
        theta=alt.Theta("Count", stack=True),
        color=alt.Color("Vehicle_Type", title="Vehicle Class", scale=COLOR_SCALE_TYPE),
        tooltip=[alt.Tooltip("Vehicle_Type", title="Class"), alt.Tooltip("Count", format=".0f")]
    )
    
    pie = base.mark_arc(outerRadius=120, innerRadius=80, stroke=SECONDARY_COLOR).properties(title="Sales Split by Vehicle Type")
    text = base.mark_text(radius=150).encode(
        text=alt.Text("Count", format=".0f"),
        order=alt.Order("Vehicle_Type", sort="descending"),
        color=alt.value("black")
    )
    
    st.altair_chart(pie + text, use_container_width=True)