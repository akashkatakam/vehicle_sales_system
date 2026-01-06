import pandas as pd
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from core import data_manager, models  # Updated Import
from features.sales.order import SalesOrder  # Updated Import
from features.sales.config import (
    HP_FEE_DEFAULT, HP_FEE_BANK_QUOTATION, GST_RATE_CALC
)


def reconstruct_sales_order(db: Session, record_id: int):
    """Reconstructs SalesOrder object for re-printing."""
    record = db.query(models.SalesRecord).get(record_id)
    if not record: return None

    branch = db.query(models.Branch).get(record.Branch_ID)

    vehicle_row = {
        'Model': record.Model,
        'Variant': record.Variant,
        'FINAL_PRICE': record.Price_Listed_Total,
        'ORP': record.Price_ORP
    }

    acc_list = data_manager.get_accessory_package_for_model(db, record.Model)
    firm_df = data_manager.get_universal_data(db)['firm_master']

    acc_bills_data = process_accessories_and_split(record.Model, acc_list, firm_df, branch)

    for bill in acc_bills_data:
        slot = bill['accessory_slot']
        seq_no = record.Acc_Inv_1_No if slot == 1 else record.Acc_Inv_2_No
        firm_obj = db.query(models.FirmMaster).filter(models.FirmMaster.Firm_ID == bill['firm_id']).first()
        prefix = firm_obj.Invoice_Prefix if firm_obj else "ERR"
        bill['Invoice_No'] = f"{prefix}-{seq_no}"
        bill['Acc_Inv_Seq'] = seq_no

    banker_name_arg = ""
    if record.Banker_Name and record.Banker_Name != "N/A (Cash Sale)":
        if record.Finance_Executive == "N/A (Cash Sale)":
            banker_name_arg = record.Banker_Name

    order = SalesOrder(
        customer_name=record.Customer_Name,
        place=record.Place,
        phone=record.Phone_Number,
        vehicle_row=vehicle_row,
        final_cost_by_staff=record.Price_Negotiated_Final,
        sales_staff=record.Sales_Staff,
        financier_name=record.Banker_Name,
        executive_name=record.Finance_Executive,
        vehicle_color_name=record.Paint_Color,
        hp_fee_to_charge=record.Charge_HP_Fee,
        incentive_earned=record.Charge_Incentive,
        banker_name=banker_name_arg,
        dc_number=record.DC_Number,
        branch_name=branch.Branch_Name,
        accessory_bills=[b for b in acc_bills_data if b['grand_total'] > 0],
        branch_id=record.Branch_ID,
        pr_fee_checkbox=record.pr_fee_checkbox,
        ew_selection=record.ew_selection,
        price_accessories=getattr(record, 'price_accessories', 0.0),
        price_ew=getattr(record, 'price_ew', 0.0),
        price_pr=getattr(record, 'price_pr', 0.0),
        price_hc=getattr(record, 'price_hc', 0.0),
        has_double_tax=getattr(record, 'has_double_tax', False),
    )

    if record.Banker_Name != "N/A (Cash Sale)":
        order.set_finance_details(record.Payment_DD, record.Payment_DownPayment)

    return order


def get_next_dc_number(db: Session, branch_id: str) -> Tuple[str, int]:
    branch = data_manager.get_branch_sequencing_data(db, branch_id, lock=True)
    if not branch: raise ValueError(f"Branch ID '{branch_id}' not found.")
    next_number = branch.DC_Last_Number + 1
    return f"DC-{next_number:04d}", next_number


def calculate_finance_fees(financier_name: str, dd_amount: float, out_finance_flag: bool,
                           incentive_rules: Dict[str, Any]) -> Tuple[float, float]:
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


def generate_accessory_invoice_number(db: Session, branch: models.Branch, firm_id: int, accessory_slot: int) -> Tuple[
    str, int]:
    firm_master = db.query(models.FirmMaster).filter(models.FirmMaster.Firm_ID == firm_id).first()
    if not firm_master: return f"ERR-FIRM{firm_id}", 0
    prefix = firm_master.Invoice_Prefix

    if accessory_slot == 1:
        last_used = branch.Acc_Inv_1_Last_Number
        start_seq = 1000
    elif accessory_slot == 2:
        last_used = branch.Acc_Inv_2_Last_Number
        start_seq = 2000
    else:
        return f"ERR-SLOT", 0

    if last_used < start_seq: last_used = start_seq - 1
    sequential_part = last_used + 1
    return f"{prefix}-{sequential_part}", sequential_part


def process_accessories_and_split(model_id: str, accessory_list: List[Dict[str, Any]], firm_master_df: pd.DataFrame,
                                  branch: models.Branch) -> List[Dict[str, Any]]:
    accessories_list_firm_1 = []
    accessories_list_firm_2 = []
    subtotal_firm_1 = 0.0
    subtotal_firm_2 = 0.0

    firm_1_id = branch.Firm_ID_1
    firm_2_id = branch.Firm_ID_2

    for item in accessory_list:
        acc_price = item.get('price', 0.0)
        if acc_price > 0:
            data = {'name': item['name'], 'qty': 1, 'price': acc_price, 'total': acc_price}
            if item['firm_slot'] == 1 and firm_1_id:
                accessories_list_firm_1.append(data)
                subtotal_firm_1 += acc_price
            elif item['firm_slot'] == 2 and firm_2_id:
                accessories_list_firm_2.append(data)
                subtotal_firm_2 += acc_price

    grand_total_1 = subtotal_firm_1 + (subtotal_firm_1 * GST_RATE_CALC)
    grand_total_2 = subtotal_firm_2 + (subtotal_firm_2 * GST_RATE_CALC)

    bills_to_print = []
    if grand_total_1 > 0 and firm_1_id:
        firm_1_row = firm_master_df[firm_master_df['Firm_ID'] == firm_1_id]
        if not firm_1_row.empty:
            bills_to_print.append({
                'firm_id': firm_1_id, 'accessory_slot': 1,
                'firm_details': firm_1_row.iloc[0].to_dict(),
                'accessories': accessories_list_firm_1, 'subtotal': subtotal_firm_1, 'grand_total': grand_total_1
            })

    if grand_total_2 > 0 and firm_2_id:
        firm_2_row = firm_master_df[firm_master_df['Firm_ID'] == firm_2_id]
        if not firm_2_row.empty:
            bills_to_print.append({
                'firm_id': firm_2_id, 'accessory_slot': 2,
                'firm_details': firm_2_row.iloc[0].to_dict(),
                'accessories': accessories_list_firm_2, 'subtotal': subtotal_firm_2, 'grand_total': grand_total_2
            })

    return bills_to_print