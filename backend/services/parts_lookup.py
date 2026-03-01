# services/parts_lookup.py
# Pure Python — finds relevant parts from inventory based on fault codes.
# No AI. Direct lookup + filter from parts_inventory.json.

from services.data_loader import get_all_parts, get_fault_code

# Map fault code → relevant part numbers
# In production this would be a proper parts-fault mapping table in the DB.
# For the prototype it's a hardcoded map derived from X15 service knowledge.
FAULT_TO_PARTS = {
    '3714': ['CUM-4309047', 'CUM-5579406'],          # DEF level sensor, DEF injector
    '3712': [],                                        # induced derate — parts depend on root cause
    '3719': ['CUM-5303870', 'CUM-4965315'],           # DPF diff pressure sensor, DPF
    '2791': ['CUM-3689260'],                           # EGR valve
    '157':  ['CUM-5579552', 'CUM-4936082', 'CUM-4928594', 'CUM-4928420'],  # fuel filters, lift pump, injector
    '110':  ['CUM-3803702', 'CUM-3319034', 'CUM-3957754'],  # thermostat, water pump, coolant sensor
    '100':  ['CUM-4089916', 'CUM-3102765'],           # oil pressure sensor, oil filter
    '102':  ['CUM-4089174'],                           # VGT turbo actuator
    '651':  ['CUM-4928420', 'CUM-4089321'],           # fuel injector, wiring harness
    '4334': [],                                        # DEF quality — fluid replacement, no part
    '3936': ['CUM-5303870', 'CUM-4965315'],           # DPF diff pressure sensor, DPF
    '132':  ['CUM-4940715'],                           # MAF sensor
    '111':  ['CUM-3957754', 'CUM-3803702'],           # coolant level sensor, thermostat
    '2789': ['CUM-4089268'],                           # EGR cooler
    '1347': ['CUM-5579552', 'CUM-4936082', 'CUM-4928594'],  # fuel filters, lift pump
    '1127': ['CUM-5268878', 'CUM-4089174'],           # CAC, VGT actuator
    '3258': ['CUM-3883438'],                           # SCR catalyst
    '559':  ['CUM-5579552', 'CUM-4936082'],           # fuel filters
}

def lookup_parts(active_fault_codes: list) -> dict:
    """
    Find parts relevant to the active fault codes.

    Args:
        active_fault_codes: list of active fault code strings

    Returns:
        dict with relevant_parts list, total_estimated_cost, approval_required flag
    """
    all_parts = {p['part_number']: p for p in get_all_parts()}

    seen_part_numbers = set()
    relevant_parts    = []
    total_cost        = 0.0
    approval_required = False

    for code in active_fault_codes:
        part_numbers = FAULT_TO_PARTS.get(str(code), [])
        for pn in part_numbers:
            if pn in seen_part_numbers:
                continue
            seen_part_numbers.add(pn)

            part = all_parts.get(pn)
            if not part:
                continue

            relevant_parts.append({
                'part_number':        part['part_number'],
                'description':        part['description'],
                'cost_usd':           part['cost_usd'],
                'in_stock':           part['in_stock'],
                'warehouse_location': part['warehouse_location'],
                'approval_required':  part['approval_required'],
                'related_fault_code': code,
            })

            total_cost += part['cost_usd']
            if part['approval_required']:
                approval_required = True

    # Sort: in-stock first, then by cost ascending
    relevant_parts.sort(key=lambda p: (not p['in_stock'], p['cost_usd']))

    return {
        'relevant_parts':       relevant_parts,
        'total_estimated_cost': round(total_cost, 2),
        'approval_required':    approval_required,
        'parts_count':          len(relevant_parts),
        'all_in_stock':         all(p['in_stock'] for p in relevant_parts) if relevant_parts else True,
    }
