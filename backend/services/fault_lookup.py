# services/fault_lookup.py
# Pure Python — looks up what each fault code means from the reference data.
# No AI involved. This is the data engineering layer.

from services.data_loader import get_fault_code


def lookup_fault_codes(active_codes: list, inactive_codes: list, fault_counts: dict) -> dict:
    """
    Look up all fault codes from the ECM snapshot.

    Returns a structured summary of what each code means,
    which systems are affected, and derate/shutdown flags.

    Args:
        active_codes:   codes currently active on the ECM
        inactive_codes: codes that have fired historically but are not active now
        fault_counts:   how many times each code has triggered

    Returns:
        dict with enriched fault code info, affected systems, and flags
    """
    enriched_active   = []
    enriched_inactive = []
    affected_systems  = set()
    any_derate        = False
    any_shutdown      = False
    highest_severity  = 'P4'

    severity_rank = {'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4}

    for code in active_codes:
        info = get_fault_code(code)
        count = fault_counts.get(code, 1)
        enriched_active.append({
            'code': code,
            'description': info.get('description', 'Unknown'),
            'system': info.get('system', 'Unknown'),
            'severity_level': info.get('severity_level', 'P3'),
            'triggers_derate': info.get('triggers_derate', False),
            'triggers_shutdown': info.get('triggers_shutdown', False),
            'common_causes': info.get('common_causes', []),
            'default_sla_hours': info.get('default_sla_hours', 8),
            'occurrence_count': count,
            'recurring': count >= 3  # flag if it keeps coming back
        })
        affected_systems.add(info.get('system', 'Unknown'))
        if info.get('triggers_derate'):
            any_derate = True
        if info.get('triggers_shutdown'):
            any_shutdown = True
        sev = info.get('severity_level', 'P4')
        if severity_rank.get(sev, 4) < severity_rank.get(highest_severity, 4):
            highest_severity = sev

    for code in inactive_codes:
        if code in active_codes:
            continue  # already in active list
        info = get_fault_code(code)
        count = fault_counts.get(code, 1)
        enriched_inactive.append({
            'code': code,
            'description': info.get('description', 'Unknown'),
            'system': info.get('system', 'Unknown'),
            'occurrence_count': count,
            'recurring': count >= 3
        })

    # Multi-system flag — if more than one system affected, bump concern level
    multi_system = len(affected_systems) > 1

    return {
        'active_codes':        enriched_active,
        'inactive_codes':      enriched_inactive,
        'affected_systems':    list(affected_systems),
        'any_derate_trigger':  any_derate,
        'any_shutdown_trigger': any_shutdown,
        'highest_code_severity': highest_severity,
        'multi_system_affected': multi_system,
        'total_active_count':  len(active_codes),
    }
