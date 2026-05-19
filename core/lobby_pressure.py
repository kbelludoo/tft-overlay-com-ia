"""LobbyPressureIndex: Termometro de pressao do lobby (0-100)."""
import logging
from typing import Dict, List

def calc_lobby_pressure(
    stage: str,
    opponent_boards: List[Dict],
    spike_status: List[Dict],
    contest_score: float
) -> Dict:
    try:
        stage_num = float(stage.split("-")[0]) if "-" in stage else 3.0
        stage_factor = max(1.0, stage_num / 4.0)

        avg_board = 0.0
        if opponent_boards:
            strengths = [len(o.get("board", [])) * 1.2 for o in opponent_boards]
            avg_board = sum(strengths) / len(strengths)

        spike_count = len([s for s in spike_status if s.get("severity") in ("CRITICAL", "MODERATE")])
        contest_norm = min(contest_score / 10.0, 1.0) * 30

        raw = (avg_board * 8) + (spike_count * 10) + contest_norm
        score = min(100, max(0, raw * stage_factor))

        if score >= 70:
            return {"score": round(score), "tier": "ALTA", "label": "Lobby Fechado", "color": "red"}
        if score >= 40:
            return {"score": round(score), "tier": "MEDIA", "label": "Pressao Moderada", "color": "yellow"}
        return {"score": round(score), "tier": "BAIXA", "label": "Lobby Aberto", "color": "green"}
    except Exception as e:
        logging.debug(f"LobbyPressure error: {e}")
        return {"score": 0, "tier": "BAIXA", "label": "Lobby Aberto", "color": "green"}
