"""
Calculadora de EV (Expected Value) - Roll vs Level.

Decisão "rolo ou subo?" definida matematicamente.
EV = (rolls * prob_hit * unit_value) - gold_cost

Se EV_level > EV_roll ou HP < 20 → tag acionável.

Fórmula:
- EV_Roll = (num_shops * prob_find * unit_value) - gold_spent
- EV_Level = extra_dmg_from_odds + extra_items + win_streak_value
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from core.stage_heuristics import (
    ROLL_ODDS, POOL_SIZE, CHAMPION_COST, calc_roll_odds, calc_champ_odds
)
from core.contest_matrix import calc_contest_score

logger = logging.getLogger(__name__)


class Decision(Enum):
    """Decisão recomendada."""
    ROLL = "roll"
    LEVEL_UP = "level_up"
    SAVE = "save"
    UNCERTAIN = "uncertain"


@dataclass
class EVResult:
    """Resultado do cálculo de EV."""
    decision: Decision
    ev_roll: float
    ev_level: float
    confidence: float
    reasoning: str
    recommendation: str
    hp_adjusted: bool
    gold_needed_for_level: Optional[int]


# Valor estimado de cada custo de unidade (em termos de placement gain)
UNIT_VALUE = {
    1: 0.3,   # 1-cost: ~0.3 placement gain por cópia
    2: 0.5,   # 2-cost: ~0.5
    3: 0.8,   # 3-cost: ~0.8
    4: 1.5,   # 4-cost: ~1.5
    5: 2.5,   # 5-cost: ~2.5
}

# Custo de XP por nível
XP_COST = {
    4: 4,   # 3→4
    5: 6,   # 4→5
    6: 8,   # 5→6
    7: 10,  # 6→7
    8: 12,  # 7→8
    9: 14,  # 8→9
}


def _estimate_level_value(current_level: int, gold: int, stage: str,
                         current_odds: Dict) -> Tuple[float, Dict]:
    """
    Estima o valor de subir de nível.
    Leva em conta: odds melhores + economia de XP.
    """
    current_odds_pct = current_odds.get(f"{current_level}cost", 0) / 100

    if current_level >= 9:
        return 0.0, {"reason": "Nível máximo"}

    next_level = current_level + 1
    next_odds = ROLL_ODDS.get(next_level, ROLL_ODDS[5])
    next_odds_pct = next_odds.get(f"{next_level}cost", 0) / 100

    # Ganho de odds (em %)
    odds_gain = next_odds_pct - current_odds_pct

    # Valor do ganho de odds
    # Ex: 3% mais chance de 4-cost = ~0.045 cópias por shop = 0.0675 value
    avg_cost_current = sum(i * (current_odds.get(f"{i}cost", 0) / 100) for i in range(1, 6))
    avg_cost_next = sum(i * (next_odds.get(f"{i}cost", 0) / 100) for i in range(1, 6))

    odds_value = (avg_cost_next - avg_cost_current) * UNIT_VALUE[4] * 10  # 10 shops

    # Valor da economia de XP (se não subir agora, vai pagar mais depois)
    # Assumindo que vai subir eventualmente, o custo é menor agora
    xp_cost_current = XP_COST.get(current_level, 0)
    xp_cost_future = XP_COST.get(current_level, 0) + 2  # +2 extra se esperar

    xp_value = (xp_cost_future - xp_cost_current) * 0.1  # ~0.1 por gold economizado

    total_value = odds_value + xp_value

    return total_value, {
        "current_odds_4cost": f"{current_odds_pct*100:.1f}%",
        "next_odds_4cost": f"{next_odds_pct*100:.1f}%",
        "odds_value": round(odds_value, 2),
        "xp_value": round(xp_value, 2)
    }


def calculate_ev_decision(current_level: int, gold: int, hp: Optional[int] = None,
                          stage: str = "1-1", board: List[str] = None,
                          suggested_comp_units: List[str] = None,
                          opponent_boards: List[List[str]] = None,
                          target_units: List[Tuple[str, int]] = None) -> EVResult:
    """
    Calcula a decisão Roll vs Level vs Save.

    Args:
        current_level: Nível atual (1-9)
        gold: Ouro atual
        hp: HP atual (pode ser None)
        stage: Stage atual (ex: "4-2")
        board: Unidades no board atual
        suggested_comp_units: Units da comp sugerida
        opponent_boards: Boards dos oponentes
        target_units: [(unit_name, copies_needed), ...] - unidades que quer encontrar

    Returns:
        EVResult com decisão e justificativa
    """
    # Fallback para hp=None
    if hp is None:
        hp = 100  # Default HP

    # Fallback para params opcionais
    if board is None:
        board = []
    if suggested_comp_units is None:
        suggested_comp_units = []
    if opponent_boards is None:
        opponent_boards = []
    # === 1. Calcular odds de roll ===
    odds = ROLL_ODDS.get(current_level, ROLL_ODDS[5])
    roll_result = calc_roll_odds(current_level, board, opponent_boards)

    # === 2. Calcular contest score ===
    contest_result = calc_contest_score(
        suggested_comp_units,
        opponent_boards,
        tanks=[],
        core_items={}
    )
    contest_score = contest_result.get("score_total", 0)

    # === 3. Calcular EV do Roll ===
    num_shops = gold // 2  # Cada shop custa 2 gold

    # Se há targets específicos, usar prob de encontrar eles
    if target_units:
        ev_roll = 0
        details = []
        for unit_name, copies_needed in target_units:
            champ_result = calc_champ_odds(unit_name, current_level, board, opponent_boards, copies_needed)
            prob = champ_result.get("probability_5_rolls", 0) / 100
            cost = CHAMPION_COST.get(unit_name, 1)
            unit_val = UNIT_VALUE.get(cost, 0.5)
            ev_roll += prob * unit_val * copies_needed * 5  # 5 shops

        total_roll_value = ev_roll * 5  # Multiplicador de impacto

        # Penalizar se contestado
        if contest_score >= 8:
            total_roll_value *= 0.6  # -40% se altamente contestado
        elif contest_score >= 3:
            total_roll_value *= 0.8  # -20% se moderadamente contestado

    else:
        # Calcular baseado nas odds gerais
        # Probabilidade de melhorar o board em 5 shops
        avg_cost_on_board = sum(CHAMPION_COST.get(u, 1) for u in board) / max(1, len(board))
        prob_improve = sum(odds.get(f"{i}cost", 0) for i in range(4, 6)) / 100

        # Valor esperado de melhoria
        total_roll_value = num_shops * prob_improve * 2.0 * (1 - contest_score/20)

    # Custo do roll
    roll_cost = gold - (gold % 2)  # Gold que será usado
    ev_roll = total_roll_value - roll_cost

    # === 4. Calcular EV do Level Up ===
    xp_cost = XP_COST.get(current_level, 0)
    level_value, level_details = _estimate_level_value(current_level, gold, stage, odds)
    ev_level = level_value - xp_cost

    # === 5. Ajustar por HP ===
    hp_adjusted = False
    if hp < 20:
        # Emergência: priorizar roll mesmo que EV menor
        ev_roll *= 1.5
        ev_level *= 0.5
        hp_adjusted = True
    elif hp < 30:
        ev_roll *= 1.2
        ev_level *= 0.8
        hp_adjusted = True

    # === 6. Determinar decisão ===
    confidence = 0.5  # Base

    # Aumentar confiança se EV é muito diferente
    ev_diff = abs(ev_roll - ev_level)
    if ev_diff > 2:
        confidence = min(0.95, 0.5 + ev_diff * 0.1)

    # Ajustar confiança por contest
    if contest_score >= 15:
        confidence *= 0.7
    elif contest_score >= 8:
        confidence *= 0.85

    if ev_roll > ev_level + 1:
        decision = Decision.ROLL
        recommendation = f"ROLE ({num_shops} shops): EV Roll {ev_roll:.1f} > EV Level {ev_level:.1f}"
        if hp_adjusted:
            recommendation += " (HP crítico ajustou)"
    elif ev_level > ev_roll + 0.5:
        decision = Decision.LEVEL_UP
        gold_needed = xp_cost - gold
        if gold_needed > 0:
            recommendation = f"SUBA ({gold_needed}g necessário): EV Level {ev_level:.1f} > EV Roll {ev_roll:.1f}"
        else:
            recommendation = f"SUBA AGORA: EV Level {ev_level:.1f} > EV Roll {ev_roll:.1f}"
    elif gold < 10:
        decision = Decision.SAVE
        recommendation = "Pouco ouro - Economize"
    else:
        decision = Decision.UNCERTAIN
        recommendation = f"Incerto: Roll={ev_roll:.1f}, Level={ev_level:.1f} (diff={abs(ev_roll-ev_level):.1f})"

    reasoning = (
        f"Ouro: {gold} ({num_shops} shops). "
        f"Contest score: {contest_score:.1f}. "
        f"Level {current_level}→{current_level+1} odds 4-cost: {odds.get(f'{current_level}cost', 0)}%→{ROLL_ODDS.get(current_level+1, {}).get(f'{current_level+1}cost', 0)}%. "
        f"{level_details.get('reason', '')}"
    )

    return EVResult(
        decision=decision,
        ev_roll=round(ev_roll, 2),
        ev_level=round(ev_level, 2),
        confidence=round(confidence, 2),
        reasoning=reasoning,
        recommendation=recommendation,
        hp_adjusted=hp_adjusted,
        gold_needed_for_level=xp_cost - gold if decision == Decision.LEVEL_UP else None
    )


def get_quick_tag(level: int, gold: int, hp: Optional[int] = None) -> str:
    """Tag rápido para display na HUD (sem cálculo completo)."""
    # Fallback para hp=None
    if hp is None:
        hp = 100

    if hp < 20:
        return "EMERGENCIA"

    if gold < 10:
        return "ECONOMIZE"

    xp_cost = XP_COST.get(level, 0)
    if gold >= xp_cost:
        return "🟢 PODE SUBIR"

    if gold >= 20:
        return "🟡 CONSIDERE ROLLAR"

    return "⚪ AGUARDE"


def format_ev_display(result: EVResult) -> Dict:
    """Formata resultado para display na HUD."""
    icons = {
        Decision.ROLL: "🎲",
        Decision.LEVEL_UP: "⬆️",
        Decision.SAVE: "💰",
        Decision.UNCERTAIN: "❓"
    }

    return {
        "tag": f"{icons.get(result.decision, '')} {result.decision.value.upper()}",
        "ev_roll": f"+{result.ev_roll:.1f}" if result.ev_roll > 0 else f"{result.ev_roll:.1f}",
        "ev_level": f"+{result.ev_level:.1f}" if result.ev_level > 0 else f"{result.ev_level:.1f}",
        "confidence": f"{result.confidence*100:.0f}%",
        "recommendation": result.recommendation,
        "hp_warning": "⚠️ HP Baixo!" if result.hp_adjusted else ""
    }


# Função de conveniência
def quick_ev_check(level: int, gold: int, hp: int) -> str:
    """Versão rápida apenas com tag."""
    return get_quick_tag(level, gold, hp)