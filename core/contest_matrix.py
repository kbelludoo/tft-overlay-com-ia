"""
Matriz de Conteste & Alertas de Pivot.

Calcula o peso estratégico de cada unidade contestada pelos oponentes.
Carry C4/C5 contestado = penalidade alta. Tank C1 = impacto baixo.

Funcões:
- calc_contest_score() — retorna score ponderado + detalhes
- get_pivot_suggestion() — sugere comp alternativa com zero sobreposição
"""
from core.data import pt
from core.stage_heuristics import CHAMPION_COST

# Pesos por custo (maior custo = mais difícil de encontrar cópias)
COST_WEIGHT = {1: 1.0, 2: 1.5, 3: 2.0, 4: 3.0, 5: 4.0}

# Pesos por função (carry = crítico, tank = moderado, suporte = baixo)
ROLE_WEIGHT = {"carry": 3.0, "tank": 1.5, "support": 1.0}

# Fator de depleção do pool (2+ oponentes = depleção severa)
POOL_DEPLETION = {1: 1.0, 2: 1.8, 3: 2.5}


def _get_champ_cost(champion_name: str) -> int:
    return CHAMPION_COST.get(champion_name, 1)


def _get_role(champion_name: str, tanks: list, core_items: dict) -> str:
    if champion_name in tanks:
        return "tank"
    if champion_name in core_items:
        return "carry"
    return "support"


def calc_contest_score(suggested_units: list, opponent_boards: list,
                       tanks: list = None, core_items: dict = None) -> dict:
    """
    Calcula o score de conteste ponderado.
    
    Args:
        suggested_units: Lista de nomes dos campeões da comp sugerida
        opponent_boards: Lista de listas dos campeões nos boards dos oponentes
        tanks: Lista de tanks da comp
        core_items: Dict de items por champion (champions com core_items = carries)
    
    Returns:
        Dict com score_total, nivel (BAIXO/MEDIO/ALTO), detalhes por unidade
    """
    tanks = tanks or []
    core_items = core_items or {}
    
    unit_details = []
    total_score = 0
    
    for champ in suggested_units:
        cost = _get_champ_cost(champ)
        role = _get_role(champ, tanks, core_items)
        cost_weight = COST_WEIGHT.get(cost, 1.0)
        role_weight = ROLE_WEIGHT.get(role, 1.0)
        
        copies_by_opponents = 0
        opponent_names = []
        for i, opp_board in enumerate(opponent_boards):
            if isinstance(opp_board, list) and champ in opp_board:
                copies_by_opponents += 1
                opponent_names.append(f"Oponente {i+1}")
        
        if copies_by_opponents == 0:
            unit_score = 0
        else:
            depletion = POOL_DEPLETION.get(copies_by_opponents, 3.0)
            unit_score = cost_weight * role_weight * depletion
        
        total_score += unit_score
        
        unit_details.append({
            "champion": champ,
            "cost": cost,
            "role": role,
            "copies_contested": copies_by_opponents,
            "opponents_using": opponent_names,
            "cost_weight": cost_weight,
            "role_weight": role_weight,
            "unit_score": round(unit_score, 2),
        })
    
    # Nível baseado no score
    if total_score >= 15:
        nivel = "CRITICO"
        cor = "red"
        acao = "PIVOTE IMEDIATO — troque a comp"
    elif total_score >= 8:
        nivel = "ALTO"
        cor = "yellow"
        acao = "Considere pivotar ou ajuste itens"
    elif total_score >= 3:
        nivel = "MEDIO"
        cor = "orange"
        acao = "Atenção — pode ter dificuldade nas cópias"
    else:
        nivel = "BAIXO"
        cor = "green"
        acao = "Comp livre — sem conteste significativo"
    
    return {
        "score_total": round(total_score, 2),
        "nivel": nivel,
        "cor": cor,
        "acao": acao,
        "units": unit_details,
        "contested_count": sum(1 for u in unit_details if u["copies_contested"] > 0),
        "total_units": len(unit_details),
    }


def get_carry_contest_summary(contest_data: dict) -> str:
    """Retorna resumo focado nos carries contestados"""
    carries = [u for u in contest_data.get("units", []) if u["role"] == "carry"]
    if not carries:
        return "Nenhum carry contestado"
    
    contested_carries = [c for c in carries if c["copies_contested"] > 0]
    if not contested_carries:
        return "Carries livres"
    
    parts = []
    for c in contested_carries:
        parts.append(f"{c['champion']} ({c['cost']}C) — {c['copies_contested']}x")
    return "Carries contestados: " + ", ".join(parts)
