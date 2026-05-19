"""
Engine de Sinergia/Anti-Sinergia de Augments.

Detecta augments redundantes, sem escala, ou que quebram power spikes.
Cruza itens/augments atuais vs oferta. Score -1.0 a 1.0.
Badge ✅/⚖️/❌ na HUD.

Tags de augments:
- anti_heal: Counter heal
- omnivamp: Life steal
- flat_stats: Stats imediatos
- scaling: Escalabilidade
- economy: Economia
- combat: Força em combate
"""
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SynergyScore(Enum):
    """Score de sinergia."""
    GOOD = "good"      # ✅ Sinergia boa
    NEUTRAL = "neutral"  # ⚖️ Neutro/ok
    BAD = "bad"       # ❌ Problema


# Tags para cada augment do Set 17
AUGMENT_TAGS = {
    "TraitTree": ["flat_stats", "scaling"],
    "MayTheFoursBeWithYou": ["combat", "scaling"],
    "HoldTheLine": ["combat", "flat_stats"],
    "BoxingLessons": ["combat", "flat_stats"],
    "Lineup": ["flat_stats", "scaling"],
    "SpreadTheLove": ["flat_stats", "scaling"],
    "TwoTanky": ["combat", "flat_stats"],
    "MakeshiftArmor": ["combat", "flat_stats"],
    "TreatedS2": ["economy", "scaling"],
    "SpreadingRoots": ["combat"],
    "UrfsGambit": ["combat", "scaling"],
}

# Augments questackam bem juntos (sinergia positiva)
SYNERGY_PAIRS = [
    {"TraitTree", "MakeshiftArmor"},  # Stats + defense
    {"HoldTheLine", "BoxingLessons"},  # Combat + combat
    {"MayTheFoursBeWithYou", "TreatedS2"},  # Scaling + economy
    {"TwoTanky", "Lineup"},  # Tank + stats
    {"SpreadTheLove", "TraitTree"},  # Stats + scaling
]

# Augments que nãostackam bem (sinergia negativa)
ANTI_SYNERGY_PAIRS = [
    {"TreatedS2", "MayTheFoursBeWithYou"},  # Ambos scaling - pode ser demais de economy
    {"TwoTanky", "HoldTheLine"},  # Ambos combat - redundancy
    {"BoxingLessons", "TwoTanky"},  # Ambos combat
]

# Regras de anti-sinergia com itens
AUGMENT_ITEM_CONFLICTS = {
    "UrfsGambit": ["Bloodthirster", "WarmogsArmor", "RabadonsDeathcap"],  # Não funciona bem com sustain/AP
    "TreatedS2": [],  # Não tem conflicts
    "MakeshiftArmor": [],  # Funciona bem com tudo
    "TwoTanky": [],  # Funciona bem com tanks
}

# Augments que precisam de escala (não usar em early)
SCALING_AUGMENTS = {"MayTheFoursBeWithYou", "TreatedS2", "TraitTree", "SpreadTheLove", "SpreadingRoots"}

# Augments de combat imediato (bom early)
COMBAT_AUGMENTS = {"HoldTheLine", "BoxingLessons", "TwoTanky", "UrfsGambit"}


@dataclass
class AugmentAnalysis:
    """Análise de um augment."""
    name: str
    tags: List[str]
    score: SynergyScore
    score_value: float
    reason: str
    suggestions: List[str]


@dataclass
class OverallAnalysis:
    """Análise geral dos augments."""
    score: SynergyScore
    overall_value: float
    augment_analysis: List[AugmentAnalysis]
    conflicts: List[Tuple[str, str]]
    suggestions: List[str]


def _get_tags(augment: str) -> List[str]:
    """Retorna tags de um augment."""
    return AUGMENT_TAGS.get(augment, [])


def _check_pair_synergy(aug1: str, aug2: str) -> float:
    """
    Retorna score de sinergia entre dois augments (-1 a 1).
    1.0 = boa sinergia
    0.0 = neutro
    -1.0 = anti-sinergia
    """
    tags1 = set(_get_tags(aug1))
    tags2 = set(_get_tags(aug2))

    # Verificar sinergia positiva
    for pair in SYNERGY_PAIRS:
        if tags1 & pair and tags2 & pair:
            return 0.8

    # Verificar anti-sinergia
    for pair in ANTI_SYNERGY_PAIRS:
        if tags1 & pair and tags2 & pair:
            return -0.6

    # Se ambos são scaling, verificar se não demais
    if tags1 & {"scaling"} and tags2 & {"scaling"}:
        return -0.3  # Pouco demais de scaling

    return 0.0  # Neutro


def _check_stage_compatibility(augment: str, stage: str) -> float:
    """
    Retorna score de compatibilidade com o stage (-1 a 1).
    1.0 = muito compatível
    -1.0 = incompatível
    """
    # Early stages (1-1 a 2-7)
    if stage < "3-1":
        if augment in COMBAT_AUGMENTS:
            return 1.0  # Bom para early
        if augment in SCALING_AUGMENTS:
            return -0.3  # Não escala bem ainda
        return 0.0

    # Mid stages (3-1 a 4-7)
    if stage < "5-1":
        if augment in SCALING_AUGMENTS:
            return 0.8  # Agora escala bem
        return 0.2

    # Late stages
    if augment in SCALING_AUGMENTS:
        return 1.0
    return 0.5


def analyze_augment(augment: str, stage: str, current_items: List[str],
                    current_comps: List[str]) -> AugmentAnalysis:
    """Analisa um augment isolado."""
    tags = _get_tags(augment)

    # Score inicial
    score_value = 0.5  # Base neutro
    reasons = []

    # 1. Compatibilidade com stage
    stage_score = _check_stage_compatibility(augment, stage)
    score_value += stage_score * 0.2

    if stage_score > 0.5:
        reasons.append(f"Bom para stage {stage}")
    elif stage_score < -0.1:
        reasons.append(f"Pode não funcionar bem em {stage}")

    # 2. Check com itens atuais
    conflicts = AUGMENT_ITEM_CONFLICTS.get(augment, [])
    conflict_items = [item for item in conflicts if item in current_items]
    if conflict_items:
        score_value -= 0.3
        reasons.append(f"Conflito com: {', '.join(conflict_items)}")

    # 3. Se tem scaling, verificar se tem items de suporte
    if "scaling" in tags:
        ap_items = ["JeweledGauntlet", "RabadonsDeathcap", "BlueBuff"]
        ad_items = ["InfinityEdge", "RapidFireCannon", "GuinsoosRageblade"]
        has_ap = any(i in current_items for i in ap_items)
        has_ad = any(i in current_items for i in ad_items)
        if not has_ap and not has_ad:
            score_value -= 0.2
            reasons.append("Sem itens de suporte para scaling")

    # Determinar score final
    if score_value >= 0.5:
        score = SynergyScore.GOOD
    elif score_value >= 0.2:
        score = SynergyScore.NEUTRAL
    else:
        score = SynergyScore.BAD

    return AugmentAnalysis(
        name=augment,
        tags=tags,
        score=score,
        score_value=round(score_value, 2),
        reason="; ".join(reasons) if reasons else "Ok",
        suggestions=[]
    )


def analyze_augment_set(augments: List[str], stage: str,
                       current_items: List[str] = None,
                       current_comps: List[str] = None) -> OverallAnalysis:
    """
    Analisa o conjunto de augments selecionados.

    Args:
        augments: Lista de augments já selecionados
        stage: Stage atual
        current_items: Itens atuais
        current_comps: Composições atuais

    Returns:
        OverallAnalysis com score e sugestões
    """
    current_items = current_items or []
    current_comps = current_comps or []

    # Analisar cada augment
    analysis_list = []
    for aug in augments:
        analysis = analyze_augment(aug, stage, current_items, current_comps)
        analysis_list.append(analysis)

    # Verificar conflicts entre augments
    conflicts = []
    for i, aug1 in enumerate(augments):
        for aug2 in augments[i+1:]:
            pair_score = _check_pair_synergy(aug1, aug2)
            if pair_score < -0.3:
                conflicts.append((aug1, aug2))

    # Calcular score geral
    if not analysis_list:
        return OverallAnalysis(
            score=SynergyScore.NEUTRAL,
            overall_value=0.5,
            augment_analysis=[],
            conflicts=[],
            suggestions=[]
        )

    avg_value = sum(a.score_value for a in analysis_list) / len(analysis_list)

    # Penalizar conflicts
    if conflicts:
        avg_value -= len(conflicts) * 0.15

    # Ajustar para stage
    # Se tem muitos scaling e stage early, penalizar
    early_scaling = [a for a in analysis_list
                    if "scaling" in a.tags and stage < "3-1"]
    if early_scaling:
        avg_value -= len(early_scaling) * 0.1

    # Definir score final
    if avg_value >= 0.5:
        final_score = SynergyScore.GOOD
    elif avg_value >= 0.2:
        final_score = SynergyScore.NEUTRAL
    else:
        final_score = SynergyScore.BAD

    # Gerar sugestões
    suggestions = []
    if conflicts:
        suggestions.append(f"Considere trocar um dos: {conflicts[0][0]} ou {conflicts[0][1]}")

    early_scaling_issues = [a for a in analysis_list
                            if "scaling" in a.tags and stage < "3-1"]
    if early_scaling_issues:
        suggestions.append(f"Augments {early_scaling_issues[0].name} podem não ajudar agora")

    return OverallAnalysis(
        score=final_score,
        overall_value=round(avg_value, 2),
        augment_analysis=analysis_list,
        conflicts=conflicts,
        suggestions=suggestions
    )


def analyze_offered_augment(augment: str, current_augments: List[str],
                           stage: str, items: List[str]) -> Dict:
    """
    Analisa um augment sendo oferecido na seleção.

    Returns:
        Dict com badge, score, reason
    """
    all_augs = current_augments + [augment]
    analysis = analyze_augment_set(all_augs, stage, items, [])

    # Encontrar a análise do augment específico
    aug_analysis = next((a for a in analysis.augment_analysis if a.name == augment),
                       None)

    if not aug_analysis:
        return {
            "badge": "⚪",
            "score": "unknown",
            "reason": "Não foi possível analisar"
        }

    badge_map = {
        SynergyScore.GOOD: "✅",
        SynergyScore.NEUTRAL: "⚖️",
        SynergyScore.BAD: "❌"
    }

    return {
        "badge": badge_map.get(aug_analysis.score, "⚪"),
        "score": aug_analysis.score.value,
        "score_value": aug_analysis.score_value,
        "reason": aug_analysis.reason,
        "tags": aug_analysis.tags
    }


def format_analysis_display(analysis: OverallAnalysis) -> Dict:
    """Formata análise para display na HUD."""
    icons = {
        SynergyScore.GOOD: "✅",
        SynergyScore.NEUTRAL: "⚖️",
        SynergyScore.BAD: "❌"
    }

    return {
        "overall_badge": icons.get(analysis.score, "⚪"),
        "overall_score": f"{analysis.overall_value*100:.0f}%",
        "augments": [
            {
                "name": a.name,
                "badge": icons.get(a.score, "⚪"),
                "tags": ", ".join(a.tags),
                "reason": a.reason
            }
            for a in analysis.augment_analysis
        ],
        "conflicts": [f"{c[0]} + {c[1]}" for c in analysis.conflicts],
        "suggestions": analysis.suggestions
    }


# Função de conveniência para integrar no prompt
def inject_augment_analysis(augments: List[str], stage: str,
                            items: List[str] = None) -> str:
    """Gera texto de análise de augments para injetar no prompt."""
    if not augments:
        return ""

    analysis = analyze_augment_set(augments, stage, items or [])
    display = format_analysis_display(analysis)

    text = "\n[SINERGIA DE AUGMENTS]\n"
    text += f"Score geral: {display['overall_badge']} {display['overall_score']}\n"

    for a in display["augments"]:
        text += f"- {a['badge']} {a['name']}: {a['reason']}\n"

    if display["conflicts"]:
        text += f"Conflitos: {', '.join(display['conflicts'])}\n"

    return text