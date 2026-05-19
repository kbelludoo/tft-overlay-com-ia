"""ZoneRiskMap: Badges de risco posicional baseados em traits/unidades inimigas."""
import logging
import re
from typing import Dict, List

ZONE_THREATS = {
    "Assassin": {"zone": "BACKLINE", "icon": "", "reason": "Assassinos pulam na backline"},
    "Blitzcrank": {"zone": "CORNER", "icon": "", "reason": "Hook mira cantos"},
    "Zephyr": {"zone": "CORNER", "icon": "", "reason": "Zephyr mira cantos opostos"},
    "AOE_Mage": {"zone": "CENTER", "icon": "", "reason": "Magos AOE punem centro agrupado"},
    "Shroud": {"zone": "FRONTLINE", "icon": "", "reason": "Shroud reduz mana da frontline"},
}

def _token_match(text: str, keyword: str) -> bool:
    """Token-based matching: 'AssassinSpirit' nao dispara falso 'assassin'."""
    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
    return bool(re.search(pattern, text.lower()))

def calc_zone_risks(ghost_pool: List[Dict], opponent_boards: List[Dict]) -> List[Dict]:
    try:
        threats = set()
        for opp in ghost_pool + opponent_boards:
            threats.update(opp.get("board", []))
            threats.update(opp.get("traits", []))

        scored = {}
        for t in threats:
            for key, rule in ZONE_THREATS.items():
                if _token_match(t, key):
                    zone = rule["zone"]
                    if zone not in scored:
                        scored[zone] = {"icon": rule["icon"], "zone": zone, "reason": rule["reason"], "count": 0}
                    scored[zone]["count"] += 1

        risks = sorted(scored.values(), key=lambda x: x["count"], reverse=True)
        for r in risks:
            del r["count"]
        return risks[:3]
    except Exception as e:
        logging.debug(f"ZoneRisk error: {e}")
        return []
