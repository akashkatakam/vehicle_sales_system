from typing import final
from sqlalchemy import (
    Boolean, Column, Enum, Integer, String, Float,
    ForeignKey, DateTime, UniqueConstraint, Date, Index, Numeric
)
from sqlalchemy.orm import relationship
from datetime import datetime
import hashlib
import os
from utils import IST_TIMEZONE # Updated import
from core.database import Base # Updated import


# --- ENUMS (Centralized) ---

@final
class ExecutiveRole:
    SALES = "SALES"
    FINANCE = "FINANCE"


@final
class IncentiveType:
    PERCENTAGE_DD = "percentage_dd"
    FIXED_FILE = "fixed_file"


@final
class TransactionType:
    INWARD_OEM = "HMSI"  # Stock arriving from manufacturer (+ Stock)
    INWARD_TRANSFER = "INWARD"  # Stock arriving from another branch (+ Stock)
    OUTWARD_TRANSFER = "OUTWARD"  # Stock leaving for another branch (- Stock)
    SALE = "Sale"


# --- 1. CORE CONFIGURATION & SEQUENCING ---

class Branch(Base):
    """
    Stores master list of branches, sequencing, and all relationships.
    This is the SINGLE Branch table definition.
    """
    __tablename__ = "branches"

    Branch_ID = Column(String(10), primary_key=True, index=True)
    Branch_Name = Column(String(100), nullable=False)

    # --- From vehicle_sales_system ---
    DC_Last_Number = Column(Integer, default=0, nullable=False)
    Acc_Inv_1_Last_Number = Column(Integer, default=0, nullable=False)
    Acc_Inv_2_Last_Number = Column(Integer, default=0, nullable=False)

    # Counters
    Receipt_Last_Number = Column(Integer, default=0, nullable=False)
    Voucher_Last_Number = Column(Integer, default=0, nullable=False)
    Branch_Receipt_Last_Number = Column(Integer, default=0, nullable=False)
    Job_Card_Last_Number = Column(Integer, default=0, nullable=False)
    Out_Bill_Last_Number = Column(Integer, default=0, nullable=False)

    Pricing_Adjustment = Column(Float, default=0.0)
    Firm_ID_1 = Column(Integer, ForeignKey("firm_master.Firm_ID"))
    Firm_ID_2 = Column(Integer, ForeignKey("firm_master.Firm_ID"), nullable=True)
    dc_gen_enabled = Column(Boolean, nullable=True)

    # --- Relationships ---
    executives = relationship("Executive", back_populates="branch")
    sales = relationship("SalesRecord", back_populates="branch")
    vehicles = relationship("VehicleMaster", back_populates="current_branch")


class BranchHierarchy(Base):
    __tablename__ = "branch_hierarchy"
    Sub_Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), primary_key=True)
    Parent_Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=False)
    sub_branch = relationship("Branch", foreign_keys=[Sub_Branch_ID])
    parent_branch = relationship("Branch", foreign_keys=[Parent_Branch_ID])


class Executive(Base):
    __tablename__ = "executives"
    id = Column(Integer, primary_key=True, index=True)
    Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), index=True)
    Role = Column(Enum(ExecutiveRole.SALES, ExecutiveRole.FINANCE), nullable=False)
    Name = Column(String(100), nullable=False)
    branch = relationship("Branch", back_populates="executives")


class Financier(Base):
    __tablename__ = "financiers"
    id = Column(Integer, primary_key=True, index=True)
    Company_Name = Column(String(100), nullable=False, unique=True)
    Incentive_Type = Column(Enum(IncentiveType.PERCENTAGE_DD, IncentiveType.FIXED_FILE))
    Incentive_Value = Column(Float)


# --- 2. UNIVERSAL VEHICLE & ACCESSORY DATA ---

class VehiclePrice(Base):
    __tablename__ = "vehicle_prices"
    id = Column(Integer, primary_key=True, index=True)
    Model = Column(String(100), index=True)
    Variant = Column(String(100))
    EX_SHOWROOM = Column(Float)
    LIFE_TAX = Column(Float)
    INSURANCE_1_4 = Column(Float)
    ORP = Column(Float)
    ACCESSORIES = Column(Float)
    EW_3_1 = Column(Float)
    HC = Column(Float)
    PR_CHARGES = Column(Float)
    FINAL_PRICE = Column(Float)
    Color_List = Column(String(500))


class AccessoryMaster(Base):
    __tablename__ = "accessory_master"
    id = Column(String(50), primary_key=True, index=True, unique=True)
    Item_Name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)


class AccessoryPackage(Base):
    __tablename__ = "accessory_packages"
    id = Column(Integer, primary_key=True, index=True)
    Model = Column(String(50), index=True, nullable=False)
    Acc_Master_ID_1 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_2 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_3 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_4 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_5 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_6 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_7 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_8 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_9 = Column(String(50), ForeignKey("accessory_master.id"))
    Acc_Master_ID_10 = Column(String(50), ForeignKey("accessory_master.id"))


class FirmMaster(Base):
    __tablename__ = "firm_master"
    Firm_ID = Column(Integer, primary_key=True)
    Firm_Name = Column(String(100))
    Invoice_Prefix = Column(String(20))
    Gst_No = Column(String(200))


# --- 3. TRANSACTION LEDGERS ---

class SalesRecord(Base):
    __tablename__ = "sales_records"
    __table_args__ = (
        UniqueConstraint('Branch_ID', 'DC_Number', name='uq_branch_dc_number'),
        Index('idx_fulfillment_status', 'fulfillment_status'),
        Index('idx_pdi_assigned_to', 'pdi_assigned_to'),
    )
    id = Column(Integer, primary_key=True, index=True)
    Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=False)
    DC_Number = Column(String(15), index=True, nullable=False)
    Timestamp = Column(DateTime, default=datetime.utcnow)
    Customer_Name = Column(String(100))
    Phone_Number = Column(String(20))
    Place = Column(String(100))
    Sales_Staff = Column(String(100))
    Finance_Executive = Column(String(100))
    Banker_Name = Column(String(100))
    Model = Column(String(100))
    Variant = Column(String(100))
    Paint_Color = Column(String(100))
    Price_ORP = Column(Float)
    Price_Listed_Total = Column(Float)
    Price_Negotiated_Final = Column(Float)
    Discount_Given = Column(Float)
    Charge_HP_Fee = Column(Float)
    Charge_Incentive = Column(Float)
    Payment_DD = Column(Float)
    Payment_DownPayment = Column(Float)
    Payment_DD_Received = Column(Float, default=0.0)
    Payment_Shortfall = Column(Float, default=0.0)
    shortfall_received = Column(Float, default=0.0)
    Acc_Inv_1_No = Column(Integer, default=0)
    Acc_Inv_2_No = Column(Integer, default=0)
    pr_fee_checkbox = Column(Boolean)
    ew_selection = Column(String(50))
    fulfillment_status = Column(String(50), default='PDI Pending', nullable=False)
    engine_no = Column(String(100), nullable=True, index=True)
    chassis_no = Column(String(100), nullable=True, index=True)
    pdi_assigned_to = Column(String(100), nullable=True, index=True)
    pdi_completion_date = Column(DateTime, nullable=True)
    is_insurance_done = Column(Boolean, default=False, nullable=False)
    is_tr_done = Column(Boolean, default=False, nullable=False)
    has_double_tax = Column(Boolean, default=False, nullable=False)
    has_dues = Column(Boolean, default=False, nullable=False)
    plates_received = Column(Boolean, default=False, nullable=False)
    price_accessories = Column(Float, default=0.0)
    price_ew = Column(Float, default=0.0)
    price_pr = Column(Float, default=0.0)
    price_hc = Column(Float, default=0.0)
    branch = relationship("Branch", back_populates="sales")
    vehicle = relationship("VehicleMaster", back_populates="sale_record", uselist=False)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id = Column(Integer, primary_key=True, index=True)
    Timestamp = Column(DateTime, default=lambda: datetime.now(IST_TIMEZONE))
    Date = Column(Date, nullable=False)
    Transaction_Type = Column(String(20), nullable=False)
    Source_External = Column(String(50), nullable=True)
    From_Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=True)
    Current_Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=False)
    To_Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=True)
    Model = Column(String(100), nullable=False)
    Variant = Column(String(100), nullable=False)
    Color = Column(String(50), nullable=False)
    Quantity = Column(Integer, nullable=False, default=1)
    Load_Number = Column(String(50))
    Remarks = Column(String(255))


# --- 4. VEHICLE MASTER TABLE ---

class VehicleMaster(Base):
    __tablename__ = "vehicle_master"
    id = Column(Integer, primary_key=True)
    chassis_no = Column(String(100), unique=True, nullable=False, index=True)
    engine_no = Column(String(100), nullable=True, index=True)
    load_reference_number = Column(String(100), nullable=True)
    model = Column(String(100))
    variant = Column(String(100))
    color = Column(String(100))
    status = Column(String(50), default='In Stock', index=True)
    date_received = Column(DateTime, default=datetime.now(IST_TIMEZONE))
    current_branch_id = Column(String(10), ForeignKey("branches.Branch_ID"), index=True)
    sale_id = Column(Integer, ForeignKey("sales_records.id"), nullable=True, index=True)
    dc_number = Column(String(15), nullable=True, index=True)
    current_branch = relationship("Branch", back_populates="vehicles")
    sale_record = relationship("SalesRecord", back_populates="vehicle")


class CashierTransaction(Base):
    __tablename__ = "cashier_log"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    transaction_type = Column(String(20), nullable=False)  # 'Receipt', 'Voucher'
    category = Column(String(50), nullable=False)
    payment_mode = Column(String(20), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String(255))

    branch_id = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=False)
    party_name = Column(String(100), nullable=True)

    dc_number = Column(String(15), ForeignKey("sales_records.DC_Number"), nullable=True)

    # Tracking Numbers
    receipt_number = Column(Integer, nullable=True)
    voucher_number = Column(Integer, nullable=True)

    imported_from_id = Column(Integer, nullable=True)

    is_expense = Column(Boolean, default=True, nullable=False)

    branch = relationship("Branch")
    sale_record = relationship("SalesRecord")


# --- 5. USER AUTHENTICATION ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    role = Column(String(255), nullable=False, default="Back Office")
    Branch_ID = Column(String(255), nullable=True)

    def verify_password(self, plain_password: str) -> bool:
        try:
            salt_bytes = bytes.fromhex(self.salt)
            check_hash_bytes = hashlib.pbkdf2_hmac(
                'sha256', plain_password.encode('utf-8'), salt_bytes, 100000
            )
            return check_hash_bytes.hex() == self.hashed_password
        except Exception:
            return False

    @staticmethod
    def hash_password(plain_password: str) -> tuple:
        salt_bytes = os.urandom(32)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256', plain_password.encode('utf-8'), salt_bytes, 100000
        )
        return hash_bytes.hex(), salt_bytes.hex()