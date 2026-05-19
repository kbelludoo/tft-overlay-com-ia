"""Compressor de historico: transforma 5 partidas brutas em resumo de ~150 tokens"""
import logging
from typing import List, Dict

def compress_history(recent_matches: List[Dict]) -> str:
    """Comprime historico recente em resumo estruturado"""
    if not recent_matches:
        return "Sem historico recente."
    
    total = len(recent_matches)
    wins = sum(1 for m in recent_matches if m.get("won", False))
    losses = total - wins
    
    placements = [m.get("placement", 8) for m in recent_matches]
    avg_placement = sum(placements) / len(placements) if placements else 8
    
    # Traits que apareceram em vitorias
    win_traits = {}
    for m in recent_matches:
        if m.get("won"):
            traits = m.get("traits", [])
            for t in traits:
                win_traits[t] = win_traits.get(t, 0) + 1
    
    # Comps que funcionaram (top 2 por vitorias)
    comp_wins = {}
    for m in recent_matches:
        if m.get("won"):
            comp = m.get("comp", "Desconhecida")
            comp_wins[comp] = comp_wins.get(comp, 0) + 1
    
    # Comps que falharam (bottom 2)
    comp_failures = {}
    for m in recent_matches:
        if m.get("placement", 8) >= 6:
            comp = m.get("comp", "Desconhecida")
            comp_failures[comp] = comp_failures.get(comp, 0) + 1
    
    # Monta resumo
    parts = []
    
    # Record
    parts.append(f"Record recente: {total} jogos ({wins}V/{losses}D)")
    parts.append(f"Colocacao media: {avg_placement:.1f}")
    
    # Traits de sucesso
    if win_traits:
        top_traits = sorted(win_traits.items(), key=lambda x: x[1], reverse=True)[:3]
        traits_str = ", ".join(f"{t} ({c}x)" for t, c in top_traits)
        parts.append(f"Traits fortes: {traits_str}")
    
    # Comps funcionais
    if comp_wins:
        top_comps = sorted(comp_wins.items(), key=lambda x: x[1], reverse=True)[:2]
        comps_str = ", ".join(f"{c} ({w}V)" for c, w in top_comps)
        parts.append(f"Comps que funcionam: {comps_str}")
    
    # Comps a evitar
    if comp_failures:
        fail_comps = sorted(comp_failures.items(), key=lambda x: x[1], reverse=True)[:2]
        fail_str = ", ".join(f"{c} ({f}x)" for c, f in fail_comps)
        parts.append(f"Evitar: {fail_str}")
    
    return " | ".join(parts)


def compress_opponents(opponent_analysis: dict, max_chars: int = 600) -> str:
    if not opponent_analysis:
        return "Sem dados de oponentes."
    
    parts = []
    for name, data in sorted(opponent_analysis.items(), key=lambda x: x[1].get("avg_placement", 8)):
        avg = data.get("avg_placement", "?")
        rank = data.get("rank", "?")
        traits = data.get("traits", [])
        recent_comps = data.get("recent_comps", [])
        
        opp_parts = [f"{name}"]
        if rank != "?":
            opp_parts.append(f"[{rank}]")
        opp_parts.append(f"avg:{avg}")
        
        if traits:
            top_traits = ", ".join(f"{t[0]}({t[1]}x)" for t in traits[:3])
            opp_parts.append(f"traits:{top_traits}")
        
        if recent_comps:
            comps_str = ", ".join(f"{c[0]}({c[1]}x)" for c in recent_comps[:3])
            opp_parts.append(f"comps:{comps_str}")
        
        parts.append(" | ".join(opp_parts))
    
    result = " ; ".join(parts)
    return result[:max_chars] if len(result) > max_chars else result
