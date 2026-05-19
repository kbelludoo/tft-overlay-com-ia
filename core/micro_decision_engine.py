"""MicroDecisionEngine: Orquestrador deterministico de acoes imediatas."""
import logging
from typing import Dict, Optional

def decide_micro_action(ev_result: Optional[Dict], slam_rec: Optional[Dict],
                        augment_analysis: Optional[Dict], contest_score: float,
                        stage: str, hp: int) -> Dict:
    try:
        stage_num = float(stage.split("-")[0]) if "-" in stage else 3.0
        if hp < 20:
            return {"action": "ROLL DOWN", "priority": "CRITICAL",
                    "reason": "HP critico: estabilize agora"}
        if contest_score >= 8 and stage_num >= 4.0:
            return {"action": "PIVOTAR", "priority": "HIGH",
                    "reason": "Conteste alto: mude de rota"}

        if ev_result and ev_result.get("decision"):
            dec = ev_result["decision"]
            if dec == "ROLL":
                return {"action": "ROLL DOWN", "priority": "HIGH",
                        "reason": ev_result.get("recommendation", "EV favorece roll")}
            if dec == "LEVEL_UP":
                return {"action": "PUSH LEVEL", "priority": "HIGH",
                        "reason": ev_result.get("recommendation", "EV favorece level")}

        if slam_rec and slam_rec.get("items_to_slam") and stage_num < 4.0:
            return {"action": "SLAM ITENS", "priority": "MEDIUM",
                    "reason": "Slam holders para estancar HP"}

        return {"action": "ECONOMIZAR", "priority": "LOW",
                "reason": "Jogo estavel: mantenha interest"}
    except Exception as e:
        logging.debug(f"MicroDecision error: {e}")
        return {"action": "AGUARDAR", "priority": "LOW",
                "reason": "Dados insuficientes"}
