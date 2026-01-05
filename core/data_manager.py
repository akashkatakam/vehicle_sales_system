from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text, or_
from core import models
from core.models import CashierTransaction
from utils import IST_TIMEZONE
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from datetime import date, datetime
import streamlit as st


# --- SHARED ACCESS LOGIC (MOVED HERE) ---
def get_user_accessible_branches(db: Session, access_list: List[str]) -> List[models.Branch]:
    """Returns Branch objects based on user access permissions."""
    if not access_list:
        return []
    if "ALL" in access_list:
        return db.query(models.Branch).filter(models.Branch.dc_gen_enabled == True).all()
    else:
        return db.query(models.Branch).filter(models.Branch.Branch_ID.in_(access_list)).all()


# --- EXISTING FUNCTIONS ---

def get_all_branches(db: Session) -> List[models.Branch]:
    return db.query(models.Branch).all()


def get_config_lists_by_branch(db: Session, branch_id: str) -> Dict[str, Any]:
    executives_db = db.query(models.Executive).filter(models.Executive.Branch_ID == branch_id).all()
    financiers_db = db.query(models.Financier).all()

    staff_names = [p.Name for p in executives_db if p.Role == models.ExecutiveRole.SALES]
    executive_names = [p.Name for p in executives_db if p.Role == models.ExecutiveRole.FINANCE]

    financier_names = [f.Company_Name for f in financiers_db]
    incentive_rules = {
        f.Company_Name: {'type': f.Incentive_Type, 'value': f.Incentive_Value}
        for f in financiers_db if f.Incentive_Type
    }
    return {
        'staff_names': staff_names,
        'executive_names': executive_names,
        'financier_names': financier_names,
        'incentive_rules': incentive_rules,
    }


def get_universal_data(db: Session) -> Dict[str, pd.DataFrame]:
    vehicles_db = db.query(models.VehiclePrice).all()
    firm_db = db.query(models.FirmMaster).all()

    def to_dataframe(data):
        if not data: return pd.DataFrame()
        df = pd.DataFrame([item.__dict__ for item in data])
        if '_sa_instance_state' in df.columns:
            df.drop(columns=['_sa_instance_state'], inplace=True)
        return df

    return {
        'vehicles': to_dataframe(vehicles_db),
        'firm_master': to_dataframe(firm_db),
    }


def get_accessory_package_for_model(db: Session, model_name: str) -> List[Dict[str, Any]]:
    package = db.query(models.AccessoryPackage).filter(models.AccessoryPackage.Model == model_name).first()
    if not package: return []

    accessory_list = []
    for i in range(1, 11):
        acc_id = getattr(package, f"Acc_Master_ID_{i}", None)
        if acc_id:
            item = db.query(models.AccessoryMaster).filter(models.AccessoryMaster.id == acc_id).first()
            if item:
                accessory_list.append({
                    'name': item.Item_Name,
                    'price': item.price if item.price else 0.0,
                    'firm_slot': 1 if i <= 4 else 2
                })
    return accessory_list


def get_branch_sequencing_data(db: Session, branch_id: str, lock: bool = False) -> Optional[models.Branch]:
    query = db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id)
    if lock:
        return query.with_for_update().first()
    return query.first()


def get_all_sales_records_for_dashboard(db: Session, branch_id_filter: str = None) -> pd.DataFrame:
    query = (
        db.query(models.SalesRecord)
        .options(joinedload(models.SalesRecord.branch))
        .order_by(models.SalesRecord.Timestamp.desc())
    )
    if branch_id_filter:
        query = query.filter(models.SalesRecord.Branch_ID == branch_id_filter)

    df = pd.read_sql(query.statement, db.get_bind())

    branches = {b.Branch_ID: b.Branch_Name for b in get_all_branches(db)}
    df['Branch_Name'] = df['Branch_ID'].map(branches)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df


def get_unlinked_booking_receipts(db: Session, branch_id: str) -> List[models.CashierTransaction]:
    """
    Fetches 'Booking Receipt' transactions for the branch that are not yet linked to a DC.
    """
    return db.query(models.CashierTransaction).filter(
        models.CashierTransaction.branch_id == branch_id,
        models.CashierTransaction.category == "Booking Receipt",
        models.CashierTransaction.transaction_type == "Receipt",
        or_(
            models.CashierTransaction.dc_number.is_(None),
            models.CashierTransaction.dc_number == ""
        )
    ).order_by(models.CashierTransaction.date.desc()).all()


def link_booking_receipts(db: Session, dc_number: str, receipt_ids: List[int]):
    """
    Updates specific cashier transactions to link them to a generated DC Number.
    """
    if not receipt_ids:
        return

    try:
        # Bulk update the dc_number for the selected receipt IDs
        db.query(models.CashierTransaction).filter(
            models.CashierTransaction.id.in_(receipt_ids)
        ).update({models.CashierTransaction.dc_number: dc_number}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise e

def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def get_recent_records_for_reprint(db: Session, branch_id: str, limit: int = 10):
    return db.query(models.SalesRecord.id, models.SalesRecord.DC_Number, models.SalesRecord.Customer_Name) \
        .filter(models.SalesRecord.Branch_ID == branch_id) \
        .order_by(models.SalesRecord.Timestamp.desc()) \
        .limit(limit) \
        .all()


def update_branch_sequences(db: Session, branch_id: str, new_dc_seq: int, new_acc1_seq: int, new_acc2_seq: int):
    try:
        branch = db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id).with_for_update().one()
        branch.DC_Last_Number = new_dc_seq
        if new_acc1_seq > 0: branch.Acc_Inv_1_Last_Number = new_acc1_seq
        if new_acc2_seq > 0: branch.Acc_Inv_2_Last_Number = new_acc2_seq
    except Exception as e:
        db.rollback()
        raise Exception(f"Atomic sequence update failed: {e}")


def create_sales_record(db: Session, record_data: Dict[str, Any]):
    try:
        branch_id = record_data['Branch_ID']
        new_dc_seq = record_data.pop('DC_Sequence_No')
        new_acc1_seq = record_data['Acc_Inv_1_No']
        new_acc2_seq = record_data['Acc_Inv_2_No']

        db_record = models.SalesRecord(**record_data)
        db.add(db_record)

        update_branch_sequences(db, branch_id, new_dc_seq, new_acc1_seq, new_acc2_seq)

        db.commit()
        db.refresh(db_record)
        return db_record
    except Exception as e:
        db.rollback()
        raise Exception(f"Transaction failed: {e}")


def update_dd_payment(db: Session, record_id: int, new_initial_dd: float = None, new_shortfall_rec: float = None):
    try:
        record = db.query(models.SalesRecord).filter(models.SalesRecord.id == record_id).first()
        if not record: return

        if new_initial_dd is not None:
            record.Payment_DD_Received = new_initial_dd
        if new_shortfall_rec is not None:
            record.shortfall_received = new_shortfall_rec

        initial = record.Payment_DD_Received or 0.0
        recovery = record.shortfall_received or 0.0
        total_received = initial + recovery
        expected = record.Payment_DD or 0.0
        new_shortfall = expected - total_received

        record.Payment_Shortfall = new_shortfall
        record.has_dues = True if new_shortfall > 0 else False
        db.commit()
    except Exception as e:
        db.rollback()
        st.error(f"Error updating record {record_id}: {e}")


def log_sale(db: Session, branch_id: str, model: str, var: str, color: str, qty: int, dt: date, rem: str):
    db.add(models.InventoryTransaction(
        Date=dt, Transaction_Type=models.TransactionType.SALE,
        Current_Branch_ID=branch_id,
        Model=model, Variant=var, Color=color, Quantity=qty,
        Remarks=rem
    ))
    db.commit()


def update_insurance_tr_status(db: Session, record_id: int, updates: Dict[str, Any]):
    try:
        record = db.query(models.SalesRecord).filter(models.SalesRecord.id == record_id).first()
        if not record: return

        ignore_keys = ['has_dues']
        for key, value in updates.items():
            if key not in ignore_keys and hasattr(record, key):
                setattr(record, key, value)
        db.commit()
    except Exception as e:
        db.rollback()
        st.error(f"Error updating record {record_id}: {e}")