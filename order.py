# order.py

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import inch
from reportlab.lib.colors import red, black, green
import pandas as pd
from typing import Dict, Any, List, Tuple
from datetime import datetime
import pytz

# --- CONSTANTS ---
GST_RATE_DISPLAY = 18 
LINE_HEIGHT = 13
IST_TIMEZONE = pytz.timezone('Asia/Kolkata')


class SalesOrder:
    def __init__(self, customer_name, place, phone, vehicle_row: Dict[str, Any], final_cost_by_staff, 
                 sales_staff, financier_name, executive_name, vehicle_color_name, 
                 hp_fee_to_charge, incentive_earned, banker_name, dc_number,
                 branch_name, accessory_bills: List[Dict[str, Any]], branch_id, pr_fee_checkbox, ew_selection):
        
        # --- Metadata ---
        self.branch_id = branch_id
        self.branch_name = branch_name
        self.dc_number = dc_number
        self.timestamp = datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S IST')
        
        # --- Customer and Staff ---
        self.customer_name = customer_name
        self.place = place
        self.phone = phone
        self.sales_staff = sales_staff
        self.financier_name = financier_name
        self.executive_name = executive_name
        self.banker_name = banker_name
        
        # --- Vehicle Pricing Details ---
        self.vehicle = vehicle_row
        self.listed_price = self.vehicle["FINAL_PRICE"]
        self.orp_price = self.vehicle["ORP"] 
        self.tax_component = self.listed_price - self.orp_price

        # --- Negotiated Details ---
        self.final_cost = final_cost_by_staff
        self.discount = self.listed_price - self.final_cost
        self.vehicle_color_name = vehicle_color_name
        self.pr_fee_checkbox = pr_fee_checkbox # <-- NEW (Pass the boolean flag)
        self.ew_selection = ew_selection
        
        # --- Finance Details ---
        self.sale_type = "Cash"
        self.hp_fee = hp_fee_to_charge          
        self.incentive_earned = incentive_earned 
        self.dd_amount = 0.0
        self.down_payment = 0.0
        self.remaining_finance_amount = 0.0
        
        # --- Accessory Billing Data ---
        self.accessory_bills = accessory_bills
        self.accessory_package_id = self.vehicle["Model"]


    def set_finance_details(self, dd_amount, down_payment):
        """Sets the details for a financed vehicle."""
        self.sale_type = "Finance"
        self.dd_amount = dd_amount
        self.down_payment = down_payment
        
        total_customer_cost = self.final_cost + self.hp_fee + self.incentive_earned
        self.remaining_finance_amount = total_customer_cost - dd_amount - down_payment

    def get_data_for_export(self, dc_sequence_no, acc_inv_1_no, acc_inv_2_no) -> Dict[str, Any]:
        """Returns a flat dictionary matching the SalesRecord model."""
        data = {
            'Branch_ID': self.branch_id,
            'DC_Number': self.dc_number,
            'Timestamp': self.timestamp,
            'Customer_Name': self.customer_name,
            'Phone_Number': self.phone,
            'Place': self.place,
            'Sales_Staff': self.sales_staff,
            'Finance_Executive': self.executive_name,
            'Banker_Name': self.financier_name if self.financier_name else '',
            'Model': self.vehicle.get('Model'),
            'Variant': self.vehicle.get('Variant'),
            'Paint_Color': self.vehicle_color_name,
            'Price_ORP': self.orp_price,
            'Price_Listed_Total': self.listed_price,
            'Price_Negotiated_Final': self.final_cost,
            'Discount_Given': self.discount,
            'Charge_HP_Fee': self.hp_fee,
            'Charge_Incentive': self.incentive_earned,
            'Payment_DD': self.dd_amount,
            'Payment_DownPayment': self.down_payment,
            
            # --- Sequential Counters for Logging ---
            'DC_Sequence_No': dc_sequence_no, # This is popped off in data_manager
            'Acc_Inv_1_No': acc_inv_1_no, 
            'Acc_Inv_2_No': acc_inv_2_no,
            'pr_fee_checkbox' : self.pr_fee_checkbox,
            'ew_selection': self.ew_selection

        }
        return data

    def generate_pdf_challan(self, filename="Order_Bill_Combined.pdf"):
        """Generates the multi-page PDF (DC + Accessory Bills)."""
        
        c = canvas.Canvas(filename, pagesize=letter) 
        width_l, height_l = letter
        A4_W, A4_H = A4
        MARGIN = 50
        
        # =========================================================================
        # PAGE 1: PRIMARY DELIVERY CHALLAN (VEHICLE & FINANCE SUMMARY)
        # =========================================================================
        
        current_date = datetime.now(IST_TIMEZONE).strftime("%d-%m-%Y")
        c = canvas.Canvas(filename, pagesize=letter) 
        width_l, height_l = letter
        A4_W, A4_H = A4
        MARGIN = 50

        # =========================================================================
        # PAGE 1: PRIMARY DELIVERY CHALLAN (VEHICLE & FINANCE SUMMARY)
        # =========================================================================
        x_margin = inch
        x_center = width_l / 2.0
        x_col_split = x_margin + 3.5 * inch
        y_cursor = height_l - inch
        row_height = 0.2 * inch
        
        # --- Title and Header ---
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x_margin, y_cursor, f"DELIVERY CHALLAN - {self.branch_name}")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(width_l - x_margin - 2*inch , y_cursor, f"DATE: {current_date}")
        y_cursor -= 0.3 * inch
        c.line(x_margin, y_cursor, width_l - x_margin, y_cursor)
        y_cursor -= 0.3 * inch
        
        # --- 1. General & Vehicle Details (Merged Two-Column Block) ---
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y_cursor, "1. GENERAL & VEHICLE DETAILS")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(width_l - x_margin - 2*inch, y_cursor, f"DC NO: {self.dc_number}")
        
        # --- 1. General & Vehicle Details ---
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y_cursor, "1. GENERAL & VEHICLE DETAILS")
        y_cursor -= 0.25 * inch
        c.setFont("Helvetica", 10)
        
        y_col_start = y_cursor
        c.drawString(x_margin, y_cursor, f"Customer: {self.customer_name}")
        y_cursor -= row_height
        c.drawString(x_margin, y_cursor, f"Phone: {self.phone} (Place: {self.place})")
        y_cursor -= row_height
        c.drawString(x_margin, y_cursor, f"Sales Staff: {self.sales_staff}")
        
        y_cursor = y_col_start 
        c.drawString(x_col_split, y_cursor, f"Model: {self.vehicle.get('Model', 'N/A')}")
        y_cursor -= row_height
        c.drawString(x_col_split, y_cursor, f"Variant/Trim: {self.vehicle.get('Variant', 'N/A')}")
        y_cursor -= row_height
        c.drawString(x_col_split, y_cursor, f"Paint Color: {self.vehicle_color_name}")
        y_cursor -= 0.5 * inch 

        # --- 2. Pricing Breakdown ---
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y_cursor, "2. PRICING BREAKDOWN")
        y_cursor -= 0.2 * inch
        c.setFont("Helvetica", 10)
        
        x_price_col = x_margin + 3.5 * inch
        
        c.drawString(x_margin, y_cursor, "On-Road Price (ORP):")
        c.drawString(x_price_col, y_cursor, f"Rs.{self.orp_price:,.2f}")
        y_cursor -= row_height
        
        c.drawString(x_margin, y_cursor, "Others:")
        c.drawString(x_price_col, y_cursor, f"Rs.{self.tax_component:,.2f}")
        y_cursor -= row_height
        
        c.line(x_price_col, y_cursor + 0.05 * inch, x_price_col + 1.5 * inch, y_cursor + 0.05 * inch)
        y_cursor -= 0.1 * inch
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_margin, y_cursor, "LISTED TOTAL PRICE:")
        c.drawString(x_price_col, y_cursor, f"Rs.{self.listed_price:,.2f}")
        y_cursor -= 0.3 * inch

        c.setFillColor(red)
        c.drawString(x_margin, y_cursor, "Discount:")
        c.drawString(x_price_col, y_cursor, f"- Rs.{self.discount:,.2f}")
        c.setFillColor(black)
        y_cursor -= 0.3 * inch
        
        c.line(x_margin, y_cursor + 0.05 * inch, width_l - x_margin, y_cursor + 0.05 * inch) 
        y_cursor -= 0.1 * inch
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y_cursor, "FINAL VEHICLE COST:")
        c.drawString(x_price_col, y_cursor, f"Rs.{self.final_cost:,.2f}")
        y_cursor -= 0.5 * inch

        # --- 3. ADDITIONAL CHARGES & FINANCE BREAKDOWN ---
        total_additional_finance_charges = self.hp_fee + self.incentive_earned
        charge_index = 3 

        if total_additional_finance_charges > 0:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x_margin, y_cursor, f"{charge_index}. ADDITIONAL FINANCE PROCESSING CHARGES")
            y_cursor -= 0.2 * inch
            c.setFont("Helvetica", 10)
            c.drawString(x_margin, y_cursor, "Total Finance Processing Charges:")
            c.drawString(x_price_col, y_cursor, f"Rs.{total_additional_finance_charges:,.2f}")
            y_cursor -= 0.3 * inch
            charge_index += 1
        
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y_cursor, f"{charge_index}. PAYMENT & FINANCE BREAKDOWN")
        y_cursor -= 0.2 * inch
        c.setFont("Helvetica", 10)
        c.drawString(x_margin, y_cursor, f"Sale Type: {self.sale_type}")
        y_cursor -= row_height

        if self.sale_type == "Finance":
            c.drawString(x_margin, y_cursor, f"Financier Company: {self.financier_name}")
            if self.banker_name:
                c.drawString(x_col_split, y_cursor, f"Banker (Quote): {self.banker_name}")
            else:
                c.drawString(x_col_split, y_cursor, f"Finance Executive: {self.executive_name}")
            y_cursor -= row_height
            
            c.drawString(x_margin, y_cursor, f"DD / Booking Amount Paid:")
            c.drawString(x_price_col, y_cursor, f"Rs.{self.dd_amount:,.2f}")
            y_cursor -= row_height
            c.drawString(x_margin, y_cursor, f"Down Payment Amount Paid:")
            c.drawString(x_price_col, y_cursor, f"Rs.{self.down_payment:,.2f}")
            y_cursor -= 0.3 * inch
            
            c.line(x_price_col, y_cursor + 0.05 * inch, x_price_col + 1.5 * inch, y_cursor + 0.05 * inch)
            y_cursor -= 0.1 * inch
            
            
        else: # Cash Sale
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x_margin, y_cursor, f"Total Cash Payment Received:")
            c.drawString(x_price_col, y_cursor, f"Rs.{self.final_cost:,.2f}")
            y_cursor -= 0.3 * inch

        # --- Summary Block ---
        y_cursor = 4 * inch 
        c.line(x_margin, y_cursor, width_l - x_margin, y_cursor) 
        y_cursor -= 0.2 * inch
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin, y_cursor, "DELIVERY CHALLAN (CUSTOMER COPY)")
        y_cursor -= 0.2 * inch
        c.setFont("Helvetica", 12)
        c.drawString(x_margin, y_cursor, f"Customer Name: {self.customer_name}")
        y_cursor -= row_height
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_margin, y_cursor, f"DC No.: {self.dc_number}")
        y_cursor -= row_height
        c.drawString(x_margin, y_cursor, f"Model/Color: {self.vehicle.get('Model')} {self.vehicle.get('Variant')} ({self.vehicle_color_name})")
        y_cursor -= row_height
        c.drawString(x_margin, y_cursor, f"PR: {self.pr_fee_checkbox}")
        y_cursor -= row_height
        c.drawString(x_margin, y_cursor, f"EW: {self.ew_selection}")
        
        # Right Column (Payment Summary)
        summary_y_cursor = 3.6 * inch 
        c.setFont("Helvetica", 10)
        c.drawString(x_col_split, summary_y_cursor, f"Sale Type: {self.sale_type}")
        summary_y_cursor -= row_height
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_col_split, summary_y_cursor, f"Finance name: Rs.{self.financier_name}")
        summary_y_cursor -= row_height
        
        # --- Footer Signatures ---
        y_cursor = 2 * inch 
        c.line(x_margin, y_cursor, x_margin + 2 * inch, y_cursor)
        c.drawCentredString(x_margin + inch, y_cursor - 0.2 * inch, "Customer Signature")
        c.line(width_l - x_margin - 2 * inch, y_cursor, width_l - x_margin, y_cursor)
        c.drawCentredString(width_l - x_margin - inch, y_cursor - 0.2 * inch, "Staff Signature")

        # =========================================================================
        # PAGE 2 onwards: ACCESSORY BILLS (DUAL COPIES)
        # =========================================================================
        
        for bill in self.accessory_bills:
            c.showPage() 
            c.setPageSize(A4) 
            
            invoice_data = {
                'Invoice_No': bill['Invoice_No'], # Use the prefixed number
                'Date': self.timestamp.split(' ')[0], # Use main timestamp date
                'Customer_Name': self.customer_name,
                'Customer_Phone': self.phone, 
                'Model_ID': self.accessory_package_id,
                'Accessories': bill['accessories'],
                'Grand_Total': bill['grand_total'],
            }

            draw_bill_content(c, invoice_data, bill['firm_details'], A4_H - MARGIN, "ORIGINAL (Customer Copy)")
            draw_bill_content(c, invoice_data, bill['firm_details'], (A4_H / 2) - 30, "DUPLICATE (Office Copy)")
            
            c.setStrokeColorRGB(0.5, 0.5, 0.5)
            c.setDash(3, 3) 
            c.line(MARGIN, A4_H / 2, A4_W - MARGIN, A4_H / 2)

        c.save()
        return filename

# --- UTILITY FUNCTION FOR PDF DRAWING (Accessory Bill) ---
def draw_bill_content(c, invoice_data, firm_details, y_start, copy_text, LINE_HEIGHT=13):
    """Draws the entire bill content relative to the y_start position."""
    width, height = A4
    MARGIN = 50
    y_pos = y_start

    # 0. COPY LABEL
    c.setFont("Helvetica-Bold", 10)
    c.drawString(width - 150, y_pos, copy_text)
    y_pos -= LINE_HEIGHT

    # 1. FIRM HEADER
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, y_pos, firm_details.get('Firm_Name', 'N/A'))
    y_pos -= LINE_HEIGHT
    
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN, y_pos, f"GSTIN: {firm_details.get('Gst_No', 'N/A')}")
    y_pos -= LINE_HEIGHT

    # 2. INVOICE HEADER 
    c.setFont("Helvetica-Bold", 10)
    c.drawString(width - 150, y_pos + (2 * LINE_HEIGHT), "TAX INVOICE")
    c.drawString(width - 150, y_pos + LINE_HEIGHT, f"INVOICE NO: {invoice_data['Invoice_No']}")
    c.drawString(width - 150, y_pos, f"DATE: {invoice_data['Date']}")
    
    # 3. Customer Info 
    y_pos -= (3 * LINE_HEIGHT)
    c.setFont("Helvetica", 10)
    c.drawString(MARGIN, y_pos, f"Customer Name: {invoice_data['Customer_Name']}")
    y_pos -= LINE_HEIGHT
    c.drawString(MARGIN, y_pos, f"Customer Phone: {invoice_data['Customer_Phone']}")
    y_pos -= LINE_HEIGHT
    c.drawString(MARGIN, y_pos, f"Vehicle Model: {invoice_data['Model_ID']}")
    
    # 4. ITEM TABLE HEADER
    y_pos -= (2 * LINE_HEIGHT)
    c.setFont("Helvetica-Bold", 10)
    col_x = [MARGIN, MARGIN + 50, MARGIN + 300, MARGIN + 400, width - 100]
    c.drawString(col_x[0], y_pos, "S.No.")
    c.drawString(col_x[1], y_pos, "ACCESSORY NAME")
    c.drawString(col_x[3], y_pos, "QTY") 
    c.drawString(col_x[4], y_pos, "PRICE")

    # Draw a line below header
    c.line(MARGIN, y_pos - 3, width - MARGIN, y_pos - 3)

    # 5. ITEM LIST
    c.setFont("Helvetica", 9)
    y_pos -= (1.5 * LINE_HEIGHT)
    
    for i, item in enumerate(invoice_data['Accessories']):
        if not item.get('name') or item.get('price', 0) == 0:
            continue
            
        c.drawString(col_x[0], y_pos, str(i + 1))
        c.drawString(col_x[1], y_pos, str(item['name']))
        c.drawString(col_x[3], y_pos, f"1")
        c.drawString(col_x[4], y_pos, f"Rs.{item['price']:.2f}")
        y_pos -= LINE_HEIGHT

    # 6. SUMMARY & SIGNATURE BLOCK
    y_summary_start = y_start - 300 
    
    # GRAND TOTAL
    c.setFont("Helvetica-Bold", 12)
    c.drawString(width - 200, y_summary_start - LINE_HEIGHT, "GRAND TOTAL:")
    c.drawString(width - 100, y_summary_start - LINE_HEIGHT, f"Rs.{invoice_data['Grand_Total']:.2f}")

    # GST TEXT 
    c.setFont("Helvetica", 8)
    c.drawString(width - 200, y_summary_start - (2.5 * LINE_HEIGHT), f"GST @ {GST_RATE_DISPLAY}% is included in the price.")