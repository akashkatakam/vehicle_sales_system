# vehicle_config.py

# --- 1. Vehicle Class (MC/SC) Mapping ---
# Maps the start of a model name to its class.
VEHICLE_CLASS = {
    'ACTIVA': 'SC',
    'ACTIVA 125': 'SC',
    'DIO': 'SC',
    'DIO 125': 'SC',
    'UNICORN': 'MC',
    'SHINE 125':'MC',
    'SHINE 100 STD': 'MC',
    'SHINE 100 DLX': 'MC',
    'SP 125': 'MC',
    'SP 160': 'MC',
    'LIVO': 'MC',
    'CB HORNET': 'MC',
    'CB HORNET 125': 'MC',
    'CB 200': 'MC',
    'NX200': 'MC'
}

# --- 2. Movement Category Mapping ---

# Rules for SLOW-moving models/colors.
# 'ALL' means the entire model is slow.
SLOW_MOVING_RULES = {
    'ACTIVA': ['DECENT BLUE', 'BLACK', 'WHITE'],
    'ACTIVA 125': ['GRAY', 'BLACK', 'WHITE', ],
    'DIO': ['ALL'],
    'DIO 125': ['ALL'],
    'UNICORN': ['RED','GREY'],
    'SHINE 125':['BLUE METALLIC', 'MAT GRAY'],
    'SHINE 100 STD': ['ALL'],
    'SHINE 100 DLX': ['GENY GRAY', 'BLACK', 'BLUE METALLIC', 'RED METALLIC'],
    'SP 125': ['BLUE METALLIC', 'BLACK', 'SIREN BLUE','RED','MAT GRAY'],
    'SP 160': ['ALL'],
    'LIVO': ['ALL'],
    'CB HORNET': ['ALL'],
    'CB HORNET 125': ['ALL'],
    'CB 200': ['ALL'],
    'NX200': ['ALL']
}

# Rules for FAST-moving models/colors.
FAST_MOVING_RULES = {
    'UNICORN': ['BLACK'],
    'SHINE 125': ['BLACK', 'RED'],
    'ACTIVA': ['MAT GRAY', 'SIREN BLUE', 'RED'],
    'ACTIVA 125': ['SIREN BLUE', 'GROUND GREY', 'RED'],
    'SHINE 125':['GENY GRAY', 'BLACK', 'SIREN BLUE', 'RED'],
    'SHINE 100 DLX': ['BLACK','RED METALLIC'],
    'SP 125': ['BLUE METALLIC', 'BLACK', 'SIREN BLUE','RED','MAT GRAY'],
}

# --- 3. Helper Functions to Apply Rules ---

def get_vehicle_type(model_name: str) -> str:
    """Assigns MC or SC based on the model name."""
    if not model_name:
        return 'Unknown'
    
    for key, value in VEHICLE_CLASS.items():
        if model_name.startswith(key):
            return value
    return 'Other' # Default if no match

def get_movement_category(model: str, color: str) -> str:
    """
    Applies the fast/slow moving logic.
    - Logic for DIO: Always 'Slow'
    - Logic for ACTIVA: Black/White are 'Slow', others are 'Fast'
    - Logic for UNICORN/SHINE 125: Black/Red are 'Fast', others are 'Slow'
    """
    
    # 1. Check Slow-Moving Rules
    if model in SLOW_MOVING_RULES:
        rules = SLOW_MOVING_RULES[model]
        if 'ALL' in rules:
            return 'Slow Moving'
        if color.upper() in rules:
            return 'Slow Moving'
        
        # If a model is in the SLOW rules but the color doesn't match,
        # its default is 'Fast' (e.g., A red Activa)
        return 'Fast Moving'

    # 2. Check Fast-Moving Rules
    if model in FAST_MOVING_RULES:
        rules = FAST_MOVING_RULES[model]
        if color.upper() in rules:
            return 'Fast Moving'
        
        # If a model is in the FAST rules but the color doesn't match,
        # its default is 'Slow' (e.g., A blue Unicorn)
        return 'Slow Moving'

    # 3. Default for all other models
    return 'N/A'