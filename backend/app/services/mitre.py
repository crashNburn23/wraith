"""
Minimal MITRE ATT&CK lookup — returns tactic name for a technique ID.
Uses a hardcoded mapping of common techniques to avoid an external API dependency.
For a full mapping, replace with the mitreattack-python library.
"""

TECHNIQUE_TACTIC_MAP: dict[str, str] = {
    "T1059": "Execution",
    "T1566": "Initial Access",
    "T1078": "Persistence",
    "T1055": "Defense Evasion",
    "T1027": "Defense Evasion",
    "T1036": "Defense Evasion",
    "T1083": "Discovery",
    "T1082": "Discovery",
    "T1057": "Discovery",
    "T1016": "Discovery",
    "T1041": "Exfiltration",
    "T1071": "Command and Control",
    "T1105": "Command and Control",
    "T1021": "Lateral Movement",
    "T1098": "Persistence",
    "T1190": "Initial Access",
    "T1133": "Initial Access",
    "T1110": "Credential Access",
    "T1003": "Credential Access",
    "T1486": "Impact",
    "T1489": "Impact",
    "T1485": "Impact",
    "T1490": "Impact",
}


def get_tactic(technique_id: str) -> str | None:
    base = technique_id.split(".")[0]  # strip sub-technique
    return TECHNIQUE_TACTIC_MAP.get(base)
