# finance_logic.py

import pandas as pd
from typing import Dict, Any, List, Tuple
import streamlit as st
from datetime import datetime
from sqlalchemy.orm import Session
import data_manager, models

# --- CONSTANTS ---
HP_FEE_DEFAULT = 2000.00
HP_FEE_BANK_QUOTATION = 500.00
GST_RATE_CALC = 0.00 
GST_RATE_DISPLAY = 18
INVOICE_PREFIXES = {} # This will be populated from FirmMaster

# --- SEQUENCING ---

def get_next_dc_number(db: Session, branch_id: str) -> Tuple[str, int]:
    """Generates the next sequential DC number for the specified branch."""
    
    branch = data_manager.get_branch_sequencing_data(db, branch_id)
    if not branch:
        raise ValueError(f"Branch ID '{branch_id}' not found.")
    
    # The next number is the LAST USED number + 1
    next_number = branch.DC_Last_Number + 1
    formatted_dc = f"DC-{next_number:04d}"
    
    return formatted_dc, next_number

def generate_accessory_invoice_number(db: Session, firm_id: int, branch_id: str) -> Tuple[str, int]:
    """Generates the next sequential accessory invoice number for a specific firm and branch."""
    
    global INVOICE_PREFIXES
    if not INVOICE_PREFIXES:
         firms = db.query(models.FirmMaster).all()
         INVOICE_PREFIXES = {f.Firm_ID: f.Invoice_Prefix for f in firms}

    prefix = INVOICE_PREFIXES.get(firm_id, "UNK") 
    
    branch = data_manager.get_branch_sequencing_data(db, branch_id)
    if not branch:
        raise ValueError(f"Branch ID '{branch_id}' not found.")

    # Determine which counter field to use
    if firm_id == 1:
        last_used = branch.Acc_Inv_1_Last_Number
        start_seq = 1000 
    elif firm_id == 2:
        last_used = branch.Acc_Inv_2_Last_Number
        start_seq = 2000
    else:
        return f"ERR-FIRM{firm_id}", 0

    if last_used < start_seq:
        last_used = start_seq - 1 

    sequential_part = last_used + 1
    formatted_invoice_no = f"{prefix}-{sequential_part}"
    
    return formatted_invoice_no, sequential_part

# --- FINANCIAL CALCULATION ---

def calculate_finance_fees(financier_name: str, dd_amount: float, out_finance_flag: bool, incentive_rules: Dict[str, Any]) -> Tuple[float, float]:
    """Calculates the Hypothecation fee and incentive collected from the customer."""
    
    hp_fee_to_charge = 0.0
    incentive_earned = 0.0

    if out_finance_flag:
        hp_fee_to_charge = HP_FEE_DEFAULT
    elif financier_name == 'Bank':
        hp_fee_to_charge = HP_FEE_BANK_QUOTATION
    else:
        hp_fee_to_charge = HP_FEE_DEFAULT
        if financier_name in incentive_rules:
            rule = incentive_rules[financier_name]
            if rule['type'] == 'percentage_dd':
                incentive_earned = dd_amount * rule['value']
            elif rule['type'] == 'fixed_file':
                incentive_earned = rule['value']
    
    return hp_fee_to_charge, incentive_earned

# --- ACCESSORY BILLING LOGIC ---

def process_accessories_and_split(model_id: str, accessory_list: List[Dict[str, Any]], firm_master_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Splits the pre-fetched accessory list into two bills based on firm_slot.
    """
    
    accessories_list_firm_1 = [] 
    accessories_list_firm_2 = [] 
    subtotal_firm_1 = 0.0
    subtotal_firm_2 = 0.0

    for item in accessory_list:
        acc_price = item.get('price', 0.0)
        
        if acc_price > 0:
            accessory_data = {'name': item['name'], 'qty': 1, 'price': acc_price, 'total': acc_price}

            if item['firm_slot'] == 1:
                accessories_list_firm_1.append(accessory_data)
                subtotal_firm_1 += acc_price
            else: 
                accessories_list_firm_2.append(accessory_data)
                subtotal_firm_2 += acc_price

    # CALCULATE TAXES AND TOTALS
    grand_total_1 = subtotal_firm_1 + (subtotal_firm_1 * GST_RATE_CALC)
    grand_total_2 = subtotal_firm_2 + (subtotal_firm_2 * GST_RATE_CALC)
    
    bills_to_print = []

    # Prepare Firm 1 Bill
    if grand_total_1 > 0:
        firm_1_details = firm_master_df[firm_master_df['Firm_ID'] == 1].iloc[0].to_dict()
        bills_to_print.append({
            'firm_id': 1,
            'firm_details': firm_1_details,
            'accessories': accessories_list_firm_1,
            'subtotal': subtotal_firm_1,
            'grand_total': grand_total_1
        })
    
    # Prepare Firm 2 Bill
    if grand_total_2 > 0:
        firm_2_details = firm_master_df[firm_master_df['Firm_ID'] == 2].iloc[0].to_dict()
        bills_to_print.append({
            'firm_id': 2,
            'firm_details': firm_2_details,
            'accessories': accessories_list_firm_2,
            'subtotal': subtotal_firm_2,
            'grand_total': grand_total_2
        })

    return bills_to_print