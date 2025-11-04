# data_manager.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text
import models
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from datetime import datetime
import streamlit as st

# --- CONFIGURATION READS ---

#@st.cache_data(ttl=3600)
def get_all_branches(db: Session) -> List[models.Branch]:
    """Retrieves all Branch objects for the initial selector."""
    return db.query(models.Branch).all()

#@st.cache_data(ttl=3600)
def get_config_lists_by_branch(db: Session, branch_id: str) -> Dict[str, Any]:
    """Retrieves all personnel and financiers for a specific branch."""
    
    executives_db = db.query(models.Executive).filter(models.Executive.Branch_ID == branch_id).all()
    financiers_db = db.query(models.Financier).all() # Incentives are universal
    
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

#@st.cache_data(ttl=3600)
def get_universal_data(db: Session) -> Dict[str, pd.DataFrame]:
    """Retrieves universal data (Pricing, Firms) as Pandas DataFrames."""
    
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

#@st.cache_data(ttl=3600)
def get_accessory_package_for_model(db: Session, model_name: str) -> List[Dict[str, Any]]:
    """Fetches and joins the specific accessory package for a given model."""
    package = db.query(models.AccessoryPackage).filter(models.AccessoryPackage.Model == model_name).first()
    
    if not package:
        return []

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

def get_branch_sequencing_data(db: Session, branch_id: str) -> Optional[models.Branch]:
    """Retrieves the branch record (with counters) using a fresh, non-cached read."""
    return db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id).first()

#@st.cache_data(ttl=600) # Cache data for 10 minutes
def get_all_sales_records_for_dashboard(db: Session) -> pd.DataFrame:
    """
    Fetches all sales records and joins with the Branch table
    to get branch names. Returns a clean Pandas DataFrame.
    """
    
    # 1. Query to join SalesRecord with Branch
    # We use joinedload to efficiently grab the related branch object
    query = (
        db.query(models.SalesRecord)
        .options(joinedload(models.SalesRecord.branch))
        .order_by(models.SalesRecord.Timestamp.desc())
    )
    
    # 2. Read directly into Pandas for easier analytics
    df = pd.read_sql(query.statement, db.get_bind())
    
    # 3. Map Branch_ID to Branch_Name for the charts
    # We get all branches (this will be cached from the main app)
    branches = {b.Branch_ID: b.Branch_Name for b in get_all_branches(db)}
    df['Branch_Name'] = df['Branch_ID'].map(branches)
    
    # 4. Convert timestamp to datetime object for filtering
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    return df

def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    """Retrieves a single user by their username."""
    return db.query(models.User).filter(models.User.username == username).first()

# --- TRANSACTION WRITE FUNCTIONS ---

def update_branch_sequences(db: Session, branch_id: str, new_dc_seq: int, new_acc1_seq: int, new_acc2_seq: int):
    """
    Atomically updates the branch's sequence counters in the 'branches' table.
    """
    try:
        branch = db.query(models.Branch).filter(models.Branch.Branch_ID == branch_id).with_for_update().one()
        
        branch.DC_Last_Number = new_dc_seq
        
        # Only update the counter if a bill was actually generated for that slot
        if new_acc1_seq > 0:
            branch.Acc_Inv_1_Last_Number = new_acc1_seq
        if new_acc2_seq > 0:
            branch.Acc_Inv_2_Last_Number = new_acc2_seq
            
        # db.commit() will be handled by the create_sales_record function
        
    except Exception as e:
        db.rollback()
        raise Exception(f"Atomic sequence update failed: {e}")

def create_sales_record(db: Session, record_data: Dict[str, Any]):
    """Creates a new sales record entry and commits the transaction."""
    try:
        # 1. Separate sequence data
        branch_id = record_data['Branch_ID']
        new_dc_seq = record_data.pop('DC_Sequence_No')
        new_acc1_seq = record_data['Acc_Inv_1_No']
        new_acc2_seq = record_data['Acc_Inv_2_No']
        
        # 2. Create the SalesRecord
        db_record = models.SalesRecord(**record_data)
        db.add(db_record)
        
        # 3. Update all counters atomically
        update_branch_sequences(
            db, branch_id, new_dc_seq, 
            new_acc1_seq, new_acc2_seq
        )
        
        db.commit()
        db.refresh(db_record)
        return db_record
        
    except Exception as e:
        db.rollback()
        raise Exception(f"Transaction failed: {e}")
