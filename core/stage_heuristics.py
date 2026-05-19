"""
Heurísticas de economia e roll odds para TFT Set 17.

Calcula:
- Nível esperado por stage
- Ouro estimado com streaks (win/loss) e juros
- Probabilidade de roll para cada custo de campeão
- Pool de campeões restante baseado no que já saiu
"""

LEVEL_TABLE = {
    "1-1": 3, "1-2": 3, "1-3": 3, "1-4": 3,
    "2-1": 4, "2-2": 4, "2-3": 4, "2-4": 4, "2-5": 4, "2-6": 4, "2-7": 4,
    "3-1": 5, "3-2": 5, "3-3": 5, "3-4": 5, "3-5": 5, "3-6": 5, "3-7": 5,
    "4-1": 6, "4-2": 6, "4-3": 6, "4-4": 6, "4-5": 6, "4-6": 6, "4-7": 6,
    "5-1": 7, "5-2": 7, "5-3": 7, "5-4": 7, "5-5": 7, "5-6": 7, "5-7": 7,
    "6-1": 8, "6-2": 8, "6-3": 8, "6-4": 8, "6-5": 8, "6-6": 8, "6-7": 8,
    "7-1": 9, "7-2": 9, "7-3": 9, "7-4": 9, "7-5": 9, "7-6": 9, "7-7": 9,
}

# Ouro passivo por round (sem interest/streak)
ROUND_GOLD = {
    "1-1": 2, "1-2": 3, "1-3": 3, "1-4": 3,
    "2-1": 3, "2-2": 4, "2-3": 4, "2-4": 4, "2-5": 4, "2-6": 4, "2-7": 4,
    "3-1": 4, "3-2": 4, "3-3": 4, "3-4": 4, "3-5": 4, "3-6": 4, "3-7": 4,
    "4-1": 4, "4-2": 4, "4-3": 4, "4-4": 4, "4-5": 4, "4-6": 4, "4-7": 4,
    "5-1": 4, "5-2": 4, "5-3": 4, "5-4": 4, "5-5": 4, "5-6": 4, "5-7": 4,
    "6-1": 4, "6-2": 4, "6-3": 4, "6-4": 4, "6-5": 4, "6-6": 4, "6-7": 4,
    "7-1": 4, "7-2": 4, "7-3": 4, "7-4": 4, "7-5": 4, "7-6": 4, "7-7": 4,
}

# Round ganho por vitória (PvP)
PVP_WIN_GOLD = 1

# Juros: 1 gold por 10 saved (max 5)
def calc_interest(current_gold: int) -> int:
    return min(5, current_gold // 10)

# Streak bonus
def calc_streak_bonus(streak: int) -> int:
    """streak > 0 = win streak, < 0 = loss streak"""
    abs_streak = abs(streak)
    if abs_streak >= 5:
        return 3
    elif abs_streak >= 3:
        return 2
    elif abs_streak >= 2:
        return 1
    return 0

def estimate_level(stage: str) -> int:
    return LEVEL_TABLE.get(stage, 5)

def estimate_gold(stage: str, current_gold: int = 0, streak: int = 0) -> int:
    """Calcula ouro total estimado: passivo acumulado + interest + streak"""
    passive = 0
    for s, gold in ROUND_GOLD.items():
        if s <= stage:
            passive += gold
    interest = calc_interest(current_gold)
    streak_bonus = calc_streak_bonus(streak)
    return passive + interest + streak_bonus

def get_interest_info(current_gold: int) -> dict:
    """Retorna detalhes do cálculo de juros"""
    interest = calc_interest(current_gold)
    next_break = (interest + 1) * 10
    gold_to_next = max(0, next_break - current_gold)
    return {
        "current_gold": current_gold,
        "interest": interest,
        "max_interest": 5,
        "next_break": next_break if interest < 5 else None,
        "gold_to_next": gold_to_next if interest < 5 else 0,
    }

def get_streak_info(streak: int) -> dict:
    """Retorna detalhes do streak"""
    is_win = streak > 0
    abs_streak = abs(streak)
    bonus = calc_streak_bonus(streak)
    if abs_streak >= 5:
        tier = "max"
    elif abs_streak >= 3:
        tier = "medium"
    elif abs_streak >= 2:
        tier = "low"
    else:
        tier = "none"
    return {
        "streak": streak,
        "type": "win" if is_win else ("loss" if streak < 0 else "none"),
        "abs_streak": abs_streak,
        "bonus": bonus,
        "tier": tier,
    }


# ═══ Roll Odds ═══

# Chances de aparecer cada custo de campeão por nível
ROLL_ODDS = {
    1: {"1cost": 100, "2cost": 0, "3cost": 0, "4cost": 0, "5cost": 0},
    2: {"1cost": 100, "2cost": 0, "3cost": 0, "4cost": 0, "5cost": 0},
    3: {"1cost": 75, "2cost": 25, "3cost": 0, "4cost": 0, "5cost": 0},
    4: {"1cost": 55, "2cost": 30, "3cost": 15, "4cost": 0, "5cost": 0},
    5: {"1cost": 45, "2cost": 33, "3cost": 20, "4cost": 2, "5cost": 0},
    6: {"1cost": 30, "2cost": 40, "3cost": 25, "4cost": 5, "5cost": 0},
    7: {"1cost": 19, "2cost": 30, "3cost": 35, "4cost": 15, "5cost": 1},
    8: {"1cost": 18, "2cost": 25, "3cost": 32, "4cost": 22, "5cost": 3},
    9: {"1cost": 10, "2cost": 20, "3cost": 25, "4cost": 35, "5cost": 10},
}

# Tamanho do pool por custo
POOL_SIZE = {
    "1cost": 29,
    "2cost": 22,
    "3cost": 18,
    "4cost": 12,
    "5cost": 10,
}

# Quantidade de cópias por custo no pool
COPIES_PER_COST = {
    "1cost": 29,
    "2cost": 22,
    "3cost": 18,
    "4cost": 12,
    "5cost": 10,
}

# Mapeamento de champion -> custo (TFT Set 17)
CHAMPION_COST = {
    "Aatrox": 1, "Akali": 1, "Blitzcrank": 1, "Caitlyn": 1, "Fiora": 1,
    "Gragas": 1, "Maokai": 1, "Nami": 1, "Poppy": 1, "Sona": 1, "Teemo": 1,
    "Aurelion Sol": 2, "Bel'Veth": 2, "Diana": 2, "Ezreal": 2, "Fizz": 2,
    "Gnar": 2, "Illaoi": 2, "Jax": 2, "Leona": 2, "Lulu": 2, "Milio": 2,
    "Mordekaiser": 2, "Nasus": 2, "Pantheon": 2, "Pyke": 2, "Rammus": 2,
    "Riven": 2, "Shen": 2, "Twisted Fate": 2,
    "Bard": 3, "Corki": 3, "Gwen": 3, "Jhin": 3, "Karma": 3, "Kindred": 3,
    "Lissandra": 3, "Miss Fortune": 3, "Morgana": 3, "Nunu & Willump": 3,
    "Ornn": 3, "Samira": 3, "Tahm Kench": 3, "Talon": 3, "Xayah": 3,
    "Aurora": 4, "Jinx": 4, "LeBlanc": 4, "Rhaast": 4, "Senna": 4,
    "The Mighty Mech": 4, "Veigar": 4, "Vex": 4, "Viktor": 4,
    "Cho'Gath": 5, "Heimerdinger": 5, "Kai'Sa": 5, "Rek'Sai": 5, "Urgot": 5, "Zed": 5, "Zoe": 5,
}

def get_cost_tier(cost: int) -> str:
    return {1: "1cost", 2: "2cost", 3: "3cost", 4: "4cost", 5: "5cost"}.get(cost, "1cost")

def calc_roll_odds(level: int, board_champions: list, opponent_boards: list = None) -> dict:
    """
    Calcula probabilidade de encontrar cada campeão no próximo roll.
    
    Args:
        level: Nível atual do jogador
        board_champions: Lista de nomes dos campeões no board do jogador
        opponent_boards: Lista de listas dos campeões nos boards dos oponentes
    
    Returns:
        Dict com odds por campeão e estatísticas gerais
    """
    level = max(1, min(9, level))
    odds = ROLL_ODDS.get(level, ROLL_ODDS[5])
    
    # Conta quantas cópias de cada custo já estão no jogo
    taken = {}
    for champ in board_champions:
        cost = CHAMPION_COST.get(champ, 1)
        tier = get_cost_tier(cost)
        taken[tier] = taken.get(tier, 0) + 1
    
    if opponent_boards:
        for opp_board in opponent_boards:
            if isinstance(opp_board, list):
                for champ in opp_board:
                    cost = CHAMPION_COST.get(champ, 1)
                    tier = get_cost_tier(cost)
                    taken[tier] = taken.get(tier, 0) + 1
    
    # Calcula pool restante
    pool_remaining = {}
    for tier in ["1cost", "2cost", "3cost", "4cost", "5cost"]:
        total = COPIES_PER_COST[tier]
        taken_count = taken.get(tier, 0)
        pool_remaining[tier] = max(0, total - taken_count)
    
    # Calcula total de shops possíveis (5 slots)
    total_pool = sum(pool_remaining.values())
    if total_pool == 0:
        total_pool = 1
    
    # Para cada custo, calcula a chance de aparecer em 1 shop
    chance_per_cost = {}
    for tier in ["1cost", "2cost", "3cost", "4cost", "5cost"]:
        if total_pool > 0:
            chance_per_cost[tier] = (pool_remaining[tier] / total_pool) * (odds[tier] / 100)
        else:
            chance_per_cost[tier] = 0
    
    return {
        "level": level,
        "odds_percent": odds,
        "pool_remaining": pool_remaining,
        "total_pool": total_pool,
        "chance_per_shop": {k: round(v * 100, 2) for k, v in chance_per_cost.items()},
    }

def calc_champ_odds(champion_name: str, level: int, board_champions: list,
                    opponent_boards: list = None, copies_needed: int = 1) -> dict:
    """
    Calcula probabilidade de encontrar um campeão específico.
    
    Args:
        champion_name: Nome do campeão
        level: Nível atual
        board_champions: Campeões no board do jogador
        opponent_boards: Boards dos oponentes
        copies_needed: Quantas cópias faltam
    
    Returns:
        Probabilidade de encontrar pelo menos 1 cópia em N rolls
    """
    cost = CHAMPION_COST.get(champion_name, 1)
    tier = get_cost_tier(cost)
    odds = ROLL_ODDS.get(level, ROLL_ODDS[5]).get(tier, 0) / 100
    
    # Conta quantas cópias já existem
    copies_in_game = 0
    for champ in board_champions:
        if champ == champion_name:
            copies_in_game += 1
    
    if opponent_boards:
        for opp_board in opponent_boards:
            if isinstance(opp_board, list):
                for champ in opp_board:
                    if champ == champion_name:
                        copies_in_game += 1
    
    total_pool = COPIES_PER_COST[tier]
    copies_in_pool = max(0, total_pool - copies_in_game)
    
    if copies_in_pool == 0 or odds == 0:
        return {
            "champion": champion_name,
            "cost": cost,
            "copies_in_pool": 0,
            "copies_needed": copies_needed,
            "probability_1_roll": 0,
            "probability_5_rolls": 0,
            "probability_10_rolls": 0,
            "expected_rolls": float('inf'),
        }
    
    # Probabilidade de encontrar 1 cópia em 1 roll (5 slots)
    p_per_slot = odds * (copies_in_pool / total_pool)
    p_per_roll = 1 - (1 - p_per_slot) ** 5
    
    # Probabilidade de encontrar pelo menos copies_needed em N rolls
    def prob_at_least_n(n_rolls, n_needed):
        # Aproximação usando distribuição binomial
        p_total = 0
        for k in range(n_needed, n_rolls * 5 + 1):
            # Simplificação: probabilidade acumulativa
            p_total = 1 - (1 - p_per_roll) ** n_rolls
        return min(1.0, p_total)
    
    p_1 = prob_at_least_n(1, copies_needed)
    p_5 = prob_at_least_n(5, copies_needed)
    p_10 = prob_at_least_n(10, copies_needed)
    
    # Rolls esperados para encontrar
    if p_per_roll > 0:
        expected = copies_needed / p_per_roll
    else:
        expected = float('inf')
    
    return {
        "champion": champion_name,
        "cost": cost,
        "tier": tier,
        "copies_in_pool": copies_in_pool,
        "total_pool": total_pool,
        "copies_needed": copies_needed,
        "odds_percent": round(odds * 100, 1),
        "probability_1_roll": round(p_1 * 100, 1),
        "probability_5_rolls": round(p_5 * 100, 1),
        "probability_10_rolls": round(p_10 * 100, 1),
        "expected_rolls": round(expected, 1) if expected != float('inf') else "impossivel",
    }


def enrich_state(state):
    """Enriquece o GameState com estimativas de economia"""
    if getattr(state, 'level', 1) <= 0:
        state.level = estimate_level(state.stage)
    if state.gold <= 0:
        state.gold = estimate_gold(state.stage)
    return state
