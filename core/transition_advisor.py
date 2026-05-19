"""
Advisor de Transição Early/Mid - Item Holders.

Sugere " Holders sinérgicos" até 4-2 para estabilizar sem comprometer late.
Dicionário de regras por trait/custo. Limita a 2 sugestões.

Regras:
- Se tem componentes, sugerir build sinérgico
- Priorizar itens que funcionam para múltiplas comps
- Não "slamar" itens que comprometem late game
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ItemTier(Enum):
    """Tier de prioridade do item."""
    HIGH = "high"          # Slamar agora
    MEDIUM = "medium"      # Considerar
    HOLD = "hold"          # Guardar para late


# Componentes de item
COMPONENTS = {
    "BFSword": "Espada BF",
    "NeedlesslyLargeRod": "Rod",
    "TearOfTheGoddess": "Lágrima",
    "RecurveBow": "Arco",
    "CloakOfAgility": "Manto",
    "ChainVest": "Colete",
    "GiantsBelt": "Cinturão",
    "NegatronCloak": "Manto Neg"
}

# Itens completos
COMPLETE_ITEMS = {
    "InfinityEdge": {"type": "AD", "carries": ["Jhin", "Samira", "Riven"]},
    "RapidFireCannon": {"type": "AD", "carries": ["Jhin"]},
    "LastWhisper": {"type": "AD", "carries": ["Jhin", "Samira", "Kai'Sa"]},
    "GuinsoosRageblade": {"type": "AD/AP", "carries": ["Kai'Sa"]},
    "Bloodthirster": {"type": "AD", "carries": ["Riven", "Samira"]},
    "GiantSlayer": {"type": "AD", "carries": ["Samira", "Kai'Sa"]},
    "BlueBuff": {"type": "AP", "carries": ["Karma", "Corki", "Aurelion Sol"]},
    "JeweledGauntlet": {"type": "AP", "carries": ["Karma", "Corki", "Veigar"]},
    "RabadonsDeathcap": {"type": "AP", "carries": ["Aurelion Sol", "Kai'Sa"]},
    "ArchangelsStaff": {"type": "AP", "carries": ["Karma", "Veigar"]},
    "WarmogsArmor": {"type": "Tank", "tanks": ["Mordekaiser", "The Mighty Mech", "Tahm Kench"]},
    "DragonClaw": {"type": "Tank", "tanks": ["Mordekaiser", "The Mighty Mech"]},
    "GargoyleStoneplate": {"type": "Tank", "tanks": ["Poppy", "Nunu"]},
    "LocketOfTheIronSolari": {"type": "Tank", "tanks": ["Poppy", "Nunu", "Morgana"]},
    "FrozenHeart": {"type": "Tank", "tanks": ["Mordekaiser", "Poppy"]},
    "HandOfJustice": {"type": "Hybrid", "carries": []},
    "SteraksGage": {"type": "Tank", "tanks": ["Mordekaiser", "Riven"]},
}


# Mapa de componentes -> itens completos possíveis
COMP_TO_ITEMS = {
    "BFSword": ["InfinityEdge", "Bloodthirster", "SteraksGage", "Deathblade", "GuardianAngel"],
    "NeedlesslyLargeRod": ["JeweledGauntlet", "RabadonsDeathcap", "ArchangelsStaff", "SpearOfShojin"],
    "TearOfTheGoddess": ["BlueBuff", "ArchangelsStaff", "HandOfJustice", "StatikkShiv"],
    "RecurveBow": ["RapidFireCannon", "GuinsoosRageblade", "GiantSlayer", "StatikkShiv"],
    "CloakOfAgility": ["RapidFireCannon", "LastWhisper", "HandOfJustice"],
    "ChainVest": ["GargoyleStoneplate", "FrozenHeart", "SunfireCape", "LocketOfTheIronSolari"],
    "GiantsBelt": ["WarmogsArmor", "LocketOfTheIronSolari", "Redemption"],
    "NegatronCloak": ["DragonClaw", "HandOfJustice", "RunaansHurricane"],
}

# Traits do Set 17 (exemplo - completar conforme necessário)
TRAIT_UNITS = {
    "Sniper": ["Jhin", "Miss Fortune"],
    "Vanguard": ["Mordekaiser", "Poppy", "Nunu", "Tahm Kench"],
    "Sorcerer": ["Karma", "Kai'Sa", "Morgana", "Veigar"],
    "Duelist": ["Samira", "Jinx", "Xayah"],
    "Archer": ["Kai'Sa", "Jhin"],
    "Rapidfire": ["Jhin", "Corki"],
    "Shadow": ["LeBlanc", "Kaisa", "Zed"],
    "Multicaster": ["Kaisa", "Karma"],
}


@dataclass
class ItemHolderSuggestion:
    """Sugestão de item holder."""
    item: str
    holder: str  # Unidade que segura o item
    reason: str
    tier: ItemTier
    late_game_item: str  # O que esse holder vira no late


# Regras de transição por estágio
STAGE_THRESHOLDS = {
    "1-1": {"can_slam": [], "hold": ["RabadonsDeathcap"]},
    "1-2": {"can_slam": [], "hold": ["RabadonsDeathcap", "InfinityEdge"]},
    "2-1": {"can_slam": ["BlueBuff", "Warmogs"], "hold": ["RabadonsDeathcap"]},
    "2-2": {"can_slam": ["BlueBuff", "Warmogs", "Gargoyle"], "hold": ["RabadonsDeathcap"]},
    "3-1": {"can_slam": ["BlueBuff", "Warmogs", "Gargoyle", "JeweledGauntlet"], "hold": ["RabadonsDeathcap"]},
    "3-2": {"can_slam": ["BlueBuff", "Warmogs", "Gargoyle", "JeweledGauntlet", "InfinityEdge"], "hold": ["RabadonsDeathcap"]},
    "4-1": {"can_slam": "all", "hold": []},
    "4-2": {"can_slam": "all", "hold": []},  # Late game começa aqui
}


def _get_stage_threshold(stage: str) -> Dict:
    """Retorna thresholds para o stage."""
    # Encontrar o threshold mais próximo
    threshold = {"can_slam": [], "hold": []}
    for s in STAGE_THRESHOLDS:
        if stage <= s:
            threshold = STAGE_THRESHOLDS[s]
            break
    return threshold


def analyze_components(components: List[str], current_comp: str,
                       current_traits: List[str]) -> List[ItemHolderSuggestion]:
    """
    Analisa componentes e sugere holders.

    Args:
        components: Lista de componentes na mão (ex: ["BFSword", "NeedlesslyLargeRod"])
        current_comp: Composição atual/planejada
        current_traits: Traits ativos

    Returns:
        Lista de até 2 sugestões de holders
    """
    suggestions = []

    # 1. Verificar se há itens completos na mão
    complete_items = [c for c in components if c in COMPLETE_ITEMS]
    for item in complete_items:
        item_info = COMPLETE_ITEMS.get(item, {})

        # Verificar se é slamável no stage atual (verificado em chamada externa)
        # Por agora, sempre sugere

        holder = _find_best_holder(item, current_comp, current_traits)
        if holder:
            suggestions.append(ItemHolderSuggestion(
                item=item,
                holder=holder,
                reason=f"{item} funciona bem com {current_comp or 'suas units'}",
                tier=ItemTier.MEDIUM if item in ["RabadonsDeathcap", "InfinityEdge"] else ItemTier.HIGH,
                late_game_item=""
            ))

    # 2. Verificar combinações de componentes
    if len(components) >= 2:
        # Tentar fazer item completo
        # BF + Rod = Deathcap (não slam agora)
        # BF + Bow = InfinityEdge (slam se AD carry)
        # Rod + Tear = Archangel (slam)
        # Tear + Cloak = Stattik (slam)
        # Vest + Belt = Sunfire (slam)

        for i, comp1 in enumerate(components):
            for comp2 in components[i+1:]:
                possible = _get_item_from_components(comp1, comp2)
                if possible:
                    holder = _find_best_holder(possible, current_comp, current_traits)
                    tier = _get_slam_tier(possible)

                    if holder and tier in [ItemTier.HIGH, ItemTier.MEDIUM]:
                        suggestions.append(ItemHolderSuggestion(
                            item=possible,
                            holder=holder,
                            reason=f"Componentes {COMPONENTS.get(comp1, comp1)} + {COMPONENTS.get(comp2, comp2)}",
                            tier=tier,
                            late_game_item=possible
                        ))

    # 3. Limitar a 2 sugestões
    # Priorizar HIGH > MEDIUM
    suggestions.sort(key=lambda x: {"HIGH": 0, "MEDIUM": 1, "HOLD": 2}[x.tier.value])

    return suggestions[:2]


def _get_item_from_components(comp1: str, comb2: str) -> Optional[str]:
    """Retorna item completo possível de dois componentes."""
    # Combinações comuns que fazem itens úteis
    combinations = {
        ("BFSword", "RecurveBow"): "InfinityEdge",
        ("RecurveBow", "BFSword"): "InfinityEdge",
        ("NeedlesslyLargeRod", "TearOfTheGoddess"): "ArchangelsStaff",
        ("TearOfTheGoddess", "NeedlesslyLargeRod"): "ArchangelsStaff",
        ("ChainVest", "GiantsBelt"): "SunfireCape",
        ("GiantsBelt", "ChainVest"): "SunfireCape",
        ("NeedlesslyLargeRod", "ChainVest"): "RabadonsDeathcap",
        ("ChainVest", "NeedlesslyLargeRod"): "RabadonsDeathcap",
    }

    return combinations.get((comp1, comb2))


def _find_best_holder(item: str, current_comp: str, current_traits: List[str]) -> Optional[str]:
    """Encontra melhor holder para o item."""
    item_info = COMPLETE_ITEMS.get(item, {})

    # 1. Se tem carries definidos, procurar no board
    if item_info.get("carries"):
        # Retorna o primeiro carry possível (simplificado)
        return item_info["carries"][0] if item_info["carries"] else None

    # 2. Se tem tanks definidos
    if item_info.get("tanks"):
        return item_info["tanks"][0] if item_info["tanks"] else None

    # 3. Por tipo de item
    item_type = item_info.get("type", "")
    if item_type == "AP":
        return "Karma"
    elif item_type == "AD":
        return "Jhin"
    elif item_type == "Tank":
        return "Poppy"

    return None


def _get_slam_tier(item: str) -> ItemTier:
    """Retorna tier de prioridade para slam do item."""
    slam_tier = {
        # HIGH - Slamar sempre
        "BlueBuff": ItemTier.HIGH,
        "WarmogsArmor": ItemTier.HIGH,
        "GargoyleStoneplate": ItemTier.HIGH,
        "InfinityEdge": ItemTier.HIGH,
        "JeweledGauntlet": ItemTier.HIGH,
        # MEDIUM - Considerar
        "Bloodthirster": ItemTier.MEDIUM,
        "RapidFireCannon": ItemTier.MEDIUM,
        "LocketOfTheIronSolari": ItemTier.MEDIUM,
        # HOLD - Guardar para late
        "RabadonsDeathcap": ItemTier.HOLD,
        "ArchangelsStaff": ItemTier.HOLD,
        "GuinsoosRageblade": ItemTier.HOLD,
    }
    return slam_tier.get(item, ItemTier.MEDIUM)


def get_slam_recommendation(stage: str, items_in_hand: List[str],
                           board_units: List[str]) -> Dict:
    """
    Retorna recomendação de slam para o stage atual.

    Args:
        stage: Stage atual (ex: "3-1")
        items_in_hand: Itens/componentes na mão
        board_units: Units no board

    Returns:
        Dict com recommendation, items_to_slam, items_to_hold
    """
    threshold = _get_stage_threshold(stage)
    can_slam = threshold.get("can_slam", [])
    hold = threshold.get("hold", [])

    items_to_slam = []
    items_to_hold = []

    for item in items_in_hand:
        if can_slam == "all":
            items_to_slam.append(item)
        elif item in can_slam:
            items_to_slam.append(item)
        elif item in hold:
            items_to_hold.append(item)

    if items_to_slam:
        recommendation = f"SLAM: {', '.join(items_to_slam)}"
    elif items_to_hold:
        recommendation = f"AGUARDE: {', '.join(items_to_hold)}"
    else:
        recommendation = "Nenhuma ação necessária"

    return {
        "stage": stage,
        "recommendation": recommendation,
        "items_to_slam": items_to_slam,
        "items_to_hold": items_to_hold,
        "threshold": threshold
    }


def format_holders_display(suggestions: List[ItemHolderSuggestion]) -> List[Dict]:
    """Formata sugestões para display na HUD."""
    result = []
    for s in suggestions:
        tier_icons = {
            ItemTier.HIGH: "🟢",
            ItemTier.MEDIUM: "🟡",
            ItemTier.HOLD: "🔴"
        }
        result.append({
            "icon": tier_icons.get(s.tier, "⚪"),
            "item": s.item,
            "holder": s.holder,
            "reason": s.reason
        })
    return result


# Função de conveniência para integrar no prompt_builder
def add_holders_to_context(stage: str, components: List[str],
                           current_comp: str, traits: List[str]) -> str:
    """Gera texto de holders para injetar no prompt."""
    if stage >= "4-2":
        return ""  # Late game - não precisa de holders

    suggestions = analyze_components(components, current_comp, traits)

    if not suggestions:
        return ""

    text = "\n[HOLDERS - TRANSITION EARLY/MID]\n"
    for s in format_holders_display(suggestions):
        text += f"- {s['icon']} {s['item']} → {s['holder']}: {s['reason']}\n"

    return text