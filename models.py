# models.py

from typing import final
from sqlalchemy import Boolean, Column, Enum, Integer, String, Float, ForeignKey, DateTime,UniqueConstraint, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, UniqueConstraint
import hashlib # <--- IMPORT THIS
import os

from order import IST_TIMEZONE #


@final
class ExecutiveRole:
    SALES = "SALES"
    FINANCE = "FINANCE"
    
# Allowed incentive types for the Financier table
@final
class IncentiveType:
    PERCENTAGE_DD = "percentage_dd"
    FIXED_FILE = "fixed_file"

class TransactionType:
    INWARD_OEM = "HMSI"       # Stock arriving from manufacturer (+ Stock)
    INWARD_TRANSFER = "INWARD" # Stock arriving from another branch (+ Stock)
    OUTWARD_TRANSFER = "OUTWARD" # Stock leaving for another branch (- Stock)
    SALE = "Sale"
    
# --- 1. CORE CONFIGURATION & SEQUENCING ---

class Branch(Base):
    """Stores master list of branches, sequencing bases, and pricing variance."""
    __tablename__ = "branches"
    
    Branch_ID = Column(String(10), primary_key=True, index=True)
    Branch_Name = Column(String(100), nullable=False)
    
    # SEQUENCE TRACKING PER BRANCH
    DC_Last_Number = Column(Integer, default=0, nullable=False)        
    Acc_Inv_1_Last_Number = Column(Integer, default=0, nullable=False) 
    Acc_Inv_2_Last_Number = Column(Integer, default=0, nullable=False) 
    
    # Pricing Variance
    Pricing_Adjustment = Column(Float, default=0.0)
    Firm_ID_1 = Column(Integer, ForeignKey("firm_master.Firm_ID")) 
    # Maps Slot 2 (accessories 5-10) to a Firm_ID
    Firm_ID_2 = Column(Integer, ForeignKey("firm_master.Firm_ID"), nullable=True)
    dc_gen_enabled =Column(Boolean, nullable=True)
    
    # Relationships
    executives = relationship("Executive", back_populates="branch")

    sales = relationship("SalesRecord", back_populates="branch")
    users = relationship("User", back_populates="branch")


class Executive(Base):
    """Stores Sales and Finance Staff."""
    __tablename__ = "executives" 
    
    id = Column(Integer, primary_key=True, index=True)
    Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), index=True)
    Role = Column(Enum(ExecutiveRole.SALES, ExecutiveRole.FINANCE), nullable=False) 
    Name = Column(String(100), nullable=False)
    branch = relationship("Branch", back_populates="executives")


class Financier(Base):
    """Stores external finance companies and their universal incentive rules."""
    __tablename__ = "financiers"
    
    id = Column(Integer, primary_key=True, index=True)
    Company_Name = Column(String(100), nullable=False, unique=True)
    # --- ENUM IMPLEMENTATION 2: Incentive Type ---
    Incentive_Type = Column(Enum(IncentiveType.PERCENTAGE_DD, IncentiveType.FIXED_FILE))
    Incentive_Value = Column(Float)


# --- 2. UNIVERSAL VEHICLE & ACCESSORY DATA ---

class VehiclePrice(Base):
    """
    Stores the full list of pricing components from the CSV.
    NOTE: Column names match your headers exactly for simple ingestion.
    """
    __tablename__ = "vehicle_prices"
    
    id = Column(Integer, primary_key=True, index=True)
    Model = Column(String(100), index=True)
    Variant = Column(String(100))
    
    # --- FULL PRICING COLUMNS ---
    EX_SHOWROOM = Column(Float)
    LIFE_TAX = Column(Float)
    INSURANCE_1_4 = Column(Float)
    ORP = Column(Float)
    ACCESSORIES = Column(Float)   # NEW
    EW_3_1 = Column(Float)        # Renamed to Python-friendly format
    HC = Column(Float)            # NEW
    PR_CHARGES = Column(Float)    # NEW
    FINAL_PRICE = Column(Float) 
    # --- END FULL PRICING COLUMNS ---
    
    Color_List = Column(String(500)) 


class AccessoryMaster(Base):
    """Master list of accessories used to build packages."""
    __tablename__ = "accessory_master"
    
    id = Column(String(50), primary_key=True, index=True, unique=True)
    Item_Name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    
    
class AccessoryPackage(Base):
    """Defines which accessories belong to a vehicle model (universal packages)."""
    __tablename__ = "accessory_packages"
    
    id = Column(Integer, primary_key=True, index=True)
    Model = Column(String(50), index=True, nullable=False)
    
    # Links to AccessoryMaster table for the specific accessory name
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
    """Details of the two billing firms (universal names and prefixes)."""
    __tablename__ = "firm_master"
    
    Firm_ID = Column(Integer, primary_key=True)
    Firm_Name = Column(String(100))
    Invoice_Prefix = Column(String(20))
    Gst_No = Column(String(200))


# --- 3. TRANSACTION LEDGER ---

class SalesRecord(Base):
    """The central transaction ledger."""
    __tablename__ = "sales_records"
    
    __table_args__ = (
        # Ensures Branch_ID and DC_Number are unique as a pair
        UniqueConstraint('Branch_ID', 'DC_Number', name='uq_branch_dc_number'), 
    )
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Metadata and Branch Tracking
    Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=False) 
    DC_Number = Column(String(15), index=True, nullable=False)
    Timestamp = Column(DateTime, default=datetime.utcnow)

    # Customer and Personnel Data
    Customer_Name = Column(String(100))
    Phone_Number = Column(String(20))
    Place = Column(String(100))
    Sales_Staff = Column(String(100))
    Finance_Executive = Column(String(100))
    Banker_Name = Column(String(100))
    
    # Vehicle and Accessory Data
    Model = Column(String(100))
    Variant = Column(String(100))
    Paint_Color = Column(String(100))
    Price_ORP= Column(Float)
    Price_Listed_Total = Column(Float)

    # Financials and Fees
    Price_Negotiated_Final = Column(Float)
    Discount_Given = Column(Float)
    Charge_HP_Fee = Column(Float)
    Charge_Incentive = Column(Float)
    Payment_DD = Column(Float)
    Payment_DownPayment = Column(Float)

    Payment_DD_Received = Column(Float, default=0.0) # The actual amount received
    Payment_Shortfall = Column(Float, default=0.0)
    
    # Accessory Invoice Tracking (Logs the *final* sequential number used)
    Acc_Inv_1_No = Column(Integer, default=0) 
    Acc_Inv_2_No = Column(Integer, default=0)
    pr_fee_checkbox= Column(Boolean) 
    ew_selection =  Column(String(50))
    
    # Relationships
    branch = relationship("Branch", back_populates="sales")

class User(Base):
    """Stores user logins and roles for the dashboard."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    
    # We will store the salt and the hash
    hashed_password = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False) # Store the salt
    
    role = Column(Enum("Owner", "Back Office"), nullable=False)

    Branch_ID = Column(String(10), ForeignKey("branches.Branch_ID"), nullable=True)
    
    # --- NEW RELATIONSHIP ---
    branch = relationship("Branch", back_populates="users")
    
    def verify_password(self, plain_password: str) -> bool:
        """Checks if the plain password matches the hash."""
        
        # --- CRITICAL FIX ---
        # 1. Convert the stored hex salt back into raw bytes
        salt_bytes = bytes.fromhex(self.salt)
        
        # 2. Hash the provided password with the retrieved salt
        check_hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt_bytes, # Use the raw bytes
            100000
        )
        
        # 3. Compare the new hash (in hex) with the stored hash (in hex)
        return check_hash_bytes.hex() == self.hashed_password
        # --- END FIX ---

    @staticmethod
    def hash_password(plain_password: str) -> tuple:
        """Hashes a new password for storage, returning the hash and salt."""
        salt_bytes = os.urandom(32) # Generate 32 raw bytes
        
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt_bytes, # Use raw bytes
            100000
        )
        
        # Return the hex versions of the hash and salt for database storage
        return hash_bytes.hex(), salt_bytes.hex()
    
class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    Timestamp = Column(DateTime, default=datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S IST'))
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
