# services/safety_rules.py
# Rule-based safety warnings derived from fault codes and freeze frame data.
# No AI. These are deterministic rules — safety cannot be left to LLM guesswork.

# System-level safety rules
SYSTEM_SAFETY_RULES = {
    'Cooling':        ['Allow engine to cool for at least 30 minutes before opening coolant system',
                       'Use caution — coolant system may be pressurized'],
    'Lubrication':    ['Do not run engine if oil pressure is critically low — risk of engine seizure',
                       'Check oil level before any restart attempt'],
    'Fuel System':    ['No open flames or sparks near fuel system components',
                       'Relieve fuel system pressure before disconnecting lines'],
    'Aftertreatment': ['DPF/SCR components may be extremely hot — allow 60 min cool-down',
                       'DEF fluid is corrosive — wear gloves and eye protection'],
    'EGR':            ['EGR components may be hot and contain carbon deposits',
                       'Wear eye protection when cleaning EGR components'],
    'Turbocharger':   ['Turbo components remain hot long after shutdown — allow 45 min cool-down',
                       'Do not run engine with suspected turbo damage'],
    'Engine Protection': ['Do not attempt restart if shutdown protection triggered — diagnose root cause first'],
}

# Freeze frame threshold warnings
def _freeze_frame_warnings(freeze_frame: dict) -> list:
    warnings = []
    ff = freeze_frame or {}

    coolant = ff.get('coolant_temp_f', 0)
    oil_psi = ff.get('oil_pressure_psi', 99)
    def_lvl = ff.get('def_level_pct', 100)

    if coolant >= 230:
        warnings.append(f'CRITICAL: Coolant temperature was {coolant}°F at fault — severe overheating risk')
    elif coolant >= 215:
        warnings.append(f'WARNING: Elevated coolant temperature ({coolant}°F) — monitor closely')

    if oil_psi <= 15:
        warnings.append(f'CRITICAL: Oil pressure was {oil_psi} psi at fault — do not restart without investigation')
    elif oil_psi <= 25:
        warnings.append(f'WARNING: Low oil pressure reading ({oil_psi} psi) — check oil level immediately')

    if def_lvl <= 10:
        warnings.append(f'DEF level critically low ({def_lvl}%) — refill required before operation')

    return warnings


def derive_safety_warnings(fault_info: dict, ecm_snapshot: dict) -> dict:
    """
    Derive safety warnings from fault codes and ECM freeze frame data.

    Args:
        fault_info:    output from fault_lookup.lookup_fault_codes()
        ecm_snapshot:  raw ECM snapshot dict

    Returns:
        dict with warnings list and general precautions
    """
    warnings    = []
    precautions = [
        'Disconnect battery before working on electrical components',
        'Wear appropriate PPE — safety glasses and gloves minimum',
        'Secure machine and apply wheel chocks before any service work',
    ]

    # System-level warnings from active fault codes
    seen_systems = set()
    for code_info in fault_info.get('active_codes', []):
        system = code_info.get('system', '')
        if system and system not in seen_systems:
            seen_systems.add(system)
            system_warns = SYSTEM_SAFETY_RULES.get(system, [])
            warnings.extend(system_warns)

    # Freeze frame threshold warnings
    freeze_frame = ecm_snapshot.get('freeze_frame', {})
    warnings.extend(_freeze_frame_warnings(freeze_frame))

    # Shutdown warning
    if ecm_snapshot.get('shutdown_active'):
        warnings.insert(0, 'CRITICAL: Engine protection shutdown was triggered — do not force restart')

    return {
        'warnings':    warnings,
        'precautions': precautions,
        'critical':    any('CRITICAL' in w for w in warnings),
    }
