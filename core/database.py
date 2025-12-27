from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import streamlit as st 
from typing import Generator
from contextlib import contextmanager

# --- 1. SECURE CONFIGURATION ---
# Safely get secrets with defaults to avoid KeyErrors
db_secrets = st.secrets.get("aurora_db", {})
DB_USER = db_secrets.get("DB_USER")
DB_PASS = db_secrets.get("DB_PASS")
DB_HOST = db_secrets.get("DB_HOST")
DB_PORT = db_secrets.get("DB_PORT")
DB_NAME = db_secrets.get("DB_NAME")

# --- 2. DATABASE URL ---
if DB_HOST and DB_USER and DB_PASS and DB_NAME:
    SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
else:
    # Fallback for local testing
    SQLALCHEMY_DATABASE_URL = "sqlite:///./sales_data_dev.db" 

# --- 3. CREATE ENGINE ---
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=False 
)

# --- 4. SESSION AND BASE ---
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency for legacy support
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- NEW: Context Manager ---
@contextmanager
def db_session():
    """Context manager for cleaner database transactions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()