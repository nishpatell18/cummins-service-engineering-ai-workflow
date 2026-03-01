# services/severity_calculator.py
# Pure rule-based logic. No AI.
# In production this would be a configurable rules engine owned by data engineering.
# For the prototype it's hardcoded rules that simulate that layer.

def calculate_severity(fault_info: dict, ecm_snapshot: dict, equipment_hours: int) -> dict:
    """
    Calculate severity, priority, and SLA based on rules — not AI.

    Rule priority order (highest wins):
      1. Shutdown active           → always P1
      2. Any shutdown-trigger code → P1
      3. Derate active + P1 code   → P1
      4. Derate active             → P2 minimum
      5. Multiple systems affected → bump up one level
      6. High equipment hours      → bump up one level
      7. Recurring fault           → bump up one level
      8. Base = highest code severity

    Args:
        fault_info:      output from fault_lookup.lookup_fault_codes()
        ecm_snapshot:    the raw ECM snapshot dict
        equipment_hours: from freeze frame

    Returns:
        dict with priority, sla_hours, impact, bump_reasons
    """
    priority     = fault_info['highest_code_severity']
    bump_reasons = []

    severity_rank = {'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4}

    def bump(current, reason):
        rank = severity_rank.get(current, 4)
        if rank > 1:
            new_priority = {1: 'P1', 2: 'P1', 3: 'P2', 4: 'P3'}[rank]
            bump_reasons.append(reason)
            return new_priority
        bump_reasons.append(f"{reason} (already P1)")
        return current

    # Rule 1: Shutdown active — hard P1
    if ecm_snapshot.get('shutdown_active'):
        priority = 'P1'
        bump_reasons.append('Engine shutdown is active')

    # Rule 2: Any code triggers shutdown
    elif fault_info.get('any_shutdown_trigger'):
        priority = 'P1'
        bump_reasons.append('Active fault code can trigger engine shutdown')

    else:
        # Rule 3+: progressive bumps
        if ecm_snapshot.get('derate_active') and priority == 'P1':
            bump_reasons.append('Derate active with P1 code')

        elif ecm_snapshot.get('derate_active'):
            priority = bump(priority, 'Power derate is active')

        if fault_info.get('multi_system_affected'):
            priority = bump(priority, 'Multiple engine systems affected')

        if equipment_hours and equipment_hours > 15000:
            priority = bump(priority, f'High equipment hours ({equipment_hours:,}hrs)')

        # Check if any active code is recurring (fired 3+ times)
        recurring_codes = [
            c['code'] for c in fault_info['active_codes'] if c.get('recurring')
        ]
        if recurring_codes:
            priority = bump(
                priority,
                f"Recurring fault(s): {', '.join(recurring_codes)} — indicates persistent issue"
            )

    # SLA based on final priority
    sla_map = {'P1': 2, 'P2': 4, 'P3': 8, 'P4': 24}
    sla_hours = sla_map.get(priority, 8)

    # Impact statement
    impact_map = {
        'P1': 'Critical — engine shutdown risk or active shutdown. Immediate response required.',
        'P2': 'High — power derate active or significant performance degradation.',
        'P3': 'Medium — reduced efficiency, no immediate safety risk.',
        'P4': 'Low — informational, monitor and schedule maintenance.'
    }

    return {
        'priority':     priority,
        'sla_hours':    sla_hours,
        'impact':       impact_map[priority],
        'bump_reasons': bump_reasons,
        'derate_active': ecm_snapshot.get('derate_active', False),
        'shutdown_active': ecm_snapshot.get('shutdown_active', False),
    }
