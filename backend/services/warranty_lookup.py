# services/warranty_lookup.py
# Pure Python — checks warranty status for a given serial number.
# No AI. Direct lookup from warranty_records.json.

from services.data_loader import get_warranty, get_product_config


def lookup_warranty(serial_number: str) -> dict:
    """
    Look up warranty status and billing info for a serial number.

    Args:
        serial_number: engine serial number from the ticket

    Returns:
        dict with warranty status, billing, and product config info
    """
    warranty = get_warranty(serial_number)
    product  = get_product_config(serial_number)

    if not warranty:
        return {
            'found': False,
            'warranty_active': False,
            'billable_to': 'Customer (warranty record not found)',
            'authorization_required': True,
            'coverage_type': 'Unknown',
            'expiry_date': None,
            'engine_model': product.get('engine_model', 'Unknown'),
            'cm_version': product.get('cm_version', 'Unknown'),
            'customer_owner': product.get('customer_owner', 'Unknown'),
            'note': 'No warranty record found for this serial number.'
        }

    return {
        'found': True,
        'warranty_active':        warranty.get('warranty_active', False),
        'billable_to':            warranty.get('billable_to', 'Unknown'),
        'authorization_required': warranty.get('authorization_required', True),
        'coverage_type':          warranty.get('coverage_type', 'Unknown'),
        'expiry_date':            warranty.get('expiry_date'),
        'engine_model':           product.get('engine_model', 'Unknown'),
        'cm_version':             product.get('cm_version', 'Unknown'),
        'customer_owner':         product.get('customer_owner', 'Unknown'),
        'ecm_calibration_id':     product.get('ecm_calibration_id', 'Unknown'),
    }
