"""Top4PressureScore: Expectativa heuristica de Top 4."""
import logging
from typing import Dict

def calc_top4_pressure(hp: int, gold: int, level: int, stage: str,
                       lobby_pressure_score: float, streak: int = 0) -> Dict:
    try:
        stage_num = float(stage.split("-")[0]) if "-" in stage else 3.0
        hp_f = min(100, max(0, hp * 1.2))
        econ_f = min(30, gold / 2) + (5 if gold >= 50 else 0)
        lvl_f = min(25, (level - 5) * 5) if level > 5 else 0
        streak_b = min(15, abs(streak) * 3) if streak != 0 else 0
        pressure_pen = lobby_pressure_score * 0.4

        raw = (hp_f * 0.4) + (econ_f * 0.2) + (lvl_f * 0.2) + streak_b - pressure_pen
        score = min(100, max(0, raw + (stage_num * 2)))

        if score >= 70:
            return {"score": round(score), "tier": "ALTA", "label": ">70% Top 4", "color": "green"}
        if score >= 40:
            return {"score": round(score), "tier": "MEDIA", "label": "40-70% Top 4", "color": "yellow"}
        return {"score": round(score), "tier": "BAIXA", "label": "<40% Top 4", "color": "red"}
    except Exception as e:
        logging.debug(f"Top4Score error: {e}")
        return {"score": 0, "tier": "BAIXA", "label": "<40% Top 4", "color": "red"}
