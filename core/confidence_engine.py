"""
Score de Confiança da IA (0-100).

Fórmula ponderada baseada em:
- Dados de oponentes disponíveis (30%)
- Estágio do jogo (25%)
- Compatibilidade com augments (25%)
- Contest score (20%)

UI Mapping:
  ≥75 🟢 Siga a sugestão
  45-74 🟡 Adapte ao contexto
  <45 🔴 Use julgamento próprio
"""


def calc_confidence(opponent_count: int, stage: str, registered_augments: list,
                    suggested_augments: list, contest_score: float,
                    has_board_data: bool = True) -> dict:
    """
    Calcula score de confiança (0-100) para a sugestão da IA.

    Returns:
        Dict com score, nivel, cor, detalhes por fator
    """
    factors = {}

    # 1. Dados de oponentes (30%)
    if opponent_count >= 5:
        opp_score = 30
    elif opponent_count >= 3:
        opp_score = 22
    elif opponent_count >= 1:
        opp_score = 12
    else:
        opp_score = 0
    factors["oponentes"] = {"score": opp_score, "max": 30, "detail": f"{opponent_count} oponentes analisados"}

    # 2. Estágio do jogo (25%)
    stage_num = _parse_stage(stage)
    if stage_num >= 4.0:
        stage_score = 25
    elif stage_num >= 3.0:
        stage_score = 20
    elif stage_num >= 2.0:
        stage_score = 12
    else:
        stage_score = 5
    factors["estagio"] = {"score": stage_score, "max": 25, "detail": f"Stage {stage}"}

    # 3. Compatibilidade com augments (25%)
    if registered_augments and suggested_augments:
        reg_set = set(a.lower() for a in registered_augments)
        sug_set = set(a.lower() for a in suggested_augments)
        overlap = len(reg_set & sug_set)
        if overlap >= 2:
            aug_score = 25
        elif overlap == 1:
            aug_score = 18
        else:
            aug_score = 5
    elif not registered_augments:
        aug_score = 15
    else:
        aug_score = 8
    factors["augments"] = {"score": aug_score, "max": 25, "detail": f"{overlap if registered_augments else 0} augments match"}

    # 4. Contest score (20%)
    if contest_score <= 3:
        contest_factor = 20
    elif contest_score <= 8:
        contest_factor = 12
    elif contest_score <= 15:
        contest_factor = 5
    else:
        contest_factor = 0
    factors["conteste"] = {"score": contest_factor, "max": 20, "detail": f"Contest: {contest_score:.1f}"}

    total = sum(f["score"] for f in factors.values())

    if total >= 75:
        nivel = "ALTA"
        cor = "green"
        icone = "🟢"
        acao = "Siga a sugestão"
    elif total >= 45:
        nivel = "MEDIA"
        cor = "yellow"
        icone = "🟡"
        acao = "Adapte ao contexto"
    else:
        nivel = "BAIXA"
        cor = "red"
        icone = "🔴"
        acao = "Use julgamento próprio"

    return {
        "score": total,
        "nivel": nivel,
        "cor": cor,
        "icone": icone,
        "acao": acao,
        "factors": factors,
    }


def _parse_stage(stage: str) -> float:
    """Converte '4-2' para 4.2"""
    try:
        parts = stage.split("-")
        return float(parts[0]) + float(parts[1]) / 10
    except (ValueError, IndexError):
        return 2.0
