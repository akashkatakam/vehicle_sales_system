import pytz
from datetime import datetime

# --- CONSTANTS ---
CASH_SALE_TAG = "N/A (Cash Sale)"
IST_TIMEZONE = pytz.timezone('Asia/Kolkata')

# --- FORMATTING ---
def format_currency(value: float, symbol: str = "₹") -> str:
    """Standardizes currency formatting across the app."""
    if value is None:
        return f"{symbol}0.00"
    return f"{symbol}{value:,.2f}"

def get_current_ist_time():
    """Returns current time in IST."""
    return datetime.now(IST_TIMEZONE)

def get_current_ist_str():
    """Returns current time string for DB logging."""
    return get_current_ist_time().strftime('%Y-%m-%d %H:%M:%S IST')