# services/data_loader.py
# Loads all JSON reference data into memory at startup.
# Everything is a plain dict/list — no DB connection needed for the prototype.

import json
import os

_BASE = os.path.join(os.path.dirname(__file__), '..', 'data')

def _load(filename: str):
    path = os.path.join(_BASE, filename)
    if not os.path.exists(path):
        print(f"[DataLoader] WARNING: {filename} not found at {path}")
        return {}
    with open(path, 'r') as f:
        return json.load(f)

# Load everything once at import time
FAULT_CODES        = _load('fault_codes.json')        # dict  keyed by code string
PRODUCT_CONFIG     = _load('product_config.json')      # list
WARRANTY_RECORDS   = _load('warranty_records.json')    # list
PARTS_INVENTORY    = _load('parts_inventory.json')     # list
ECM_SNAPSHOTS      = _load('ecm_snapshots.json')       # list
ACTIVE_TICKETS     = _load('active_tickets.json')      # list
HISTORICAL_TICKETS = _load('historical_tickets.json')  # list

# Build fast lookup indexes
_product_by_serial  = {p['serial_number']: p  for p in PRODUCT_CONFIG}
_warranty_by_serial = {w['serial_number']: w  for w in WARRANTY_RECORDS}
_ecm_by_ticket      = {e['ticket_id']: e      for e in ECM_SNAPSHOTS}
_ecm_by_serial      = {e['serial_number']: e  for e in ECM_SNAPSHOTS}

def get_fault_code(code: str) -> dict:
    return FAULT_CODES.get(str(code), {
        'fault_code': code,
        'description': 'Unknown fault code',
        'severity_level': 'P3',
        'triggers_derate': False,
        'triggers_shutdown': False,
        'common_causes': [],
        'default_sla_hours': 8,
        'system': 'Unknown'
    })

def get_product_config(serial_number: str) -> dict:
    return _product_by_serial.get(serial_number, {})

def get_warranty(serial_number: str) -> dict:
    return _warranty_by_serial.get(serial_number, {})

def get_ecm_snapshot_by_ticket(ticket_id: str) -> dict:
    return _ecm_by_ticket.get(ticket_id, {})

def get_ecm_snapshot_by_serial(serial_number: str) -> dict:
    return _ecm_by_serial.get(serial_number, {})

def get_all_historical_tickets() -> list:
    return HISTORICAL_TICKETS

def get_all_parts() -> list:
    return PARTS_INVENTORY

print(f"[DataLoader] Loaded: "
      f"{len(FAULT_CODES)} fault codes, "
      f"{len(PRODUCT_CONFIG)} products, "
      f"{len(WARRANTY_RECORDS)} warranty records, "
      f"{len(PARTS_INVENTORY)} parts, "
      f"{len(HISTORICAL_TICKETS)} historical tickets")
