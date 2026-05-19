#!/usr/bin/env python3
"""
update_meta.py - Atualiza meta_db.json usando a API da Riot
Analisa matches recentes de diferentes ranks para encontrar composicoes fortes
"""
import os, sys, json, time, logging
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from core.api_wrapper import safe_req
from core.riot_key_manager import riot_key_mgr
from core.config import get_riot_region, get_riot_platform

PROJECT_DIR = Path(__file__).parent
META_JSON = PROJECT_DIR / "data" / "meta_db.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")
if RIOT_API_KEY:
    riot_key_mgr.key = RIOT_API_KEY
    riot_key_mgr.register_key_creation(expires_in_hours=24)

# Mapeamento de tiers para ranks
TIER_RANKS = {
    "IRON": ["IV", "III", "II", "I"],
    "BRONZE": ["IV", "III", "II", "I"],
    "SILVER": ["IV", "III", "II", "I"],
    "GOLD": ["IV", "III", "II", "I"],
    "PLATINUM": ["IV", "III", "II", "I"],
    "DIAMOND": ["IV", "III", "II", "I"],
    "MASTER": [""],
    "GRANDMASTER": [""],
    "CHALLENGER": [""],
}

def get_summoners_by_rank(tier: str, rank: str = "", count: int = 10) -> list:
    region = get_riot_region()
    if not RIOT_API_KEY:
        logging.error("RIOT_API_KEY nao configurada")
        return []
    
    try:
        if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
            url = f"https://{region}.api.riotgames.com/tft/league/v1/{tier.lower()}"
            data = safe_req.get(url, use_key=True)
            if data:
                entries = data.get("entries", [])
                return [e.get("puuid", "") for e in entries[:count] if e.get("puuid")]
        else:
            url = f"https://{region}.api.riotgames.com/tft/league/v1/entries/{tier}/{rank}"
            params = {"page": 1}
            data = safe_req.get(url, params=params, use_key=True)
            if data and isinstance(data, list):
                return [e.get("puuid", "") for e in data[:count] if e.get("puuid")]
    except Exception as e:
        logging.warning(f"Erro ao buscar {tier} {rank}: {e}")
    return []

def get_match_ids(puuid: str, count: int = 20) -> list:
    platform = get_riot_platform()
    try:
        url = f"https://{platform}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids"
        data = safe_req.get(url, params={"count": count}, use_key=True)
        if data and isinstance(data, list):
            return data
    except Exception as e:
        logging.warning(f"Erro ao buscar matches: {e}")
    return []

def get_match_details(match_id: str) -> dict:
    platform = get_riot_platform()
    try:
        url = f"https://{platform}.api.riotgames.com/tft/match/v1/matches/{match_id}"
        data = safe_req.get(url, use_key=True)
        if data:
            return data
    except Exception as e:
        logging.warning(f"Erro ao buscar match {match_id}: {e}")
    return {}

def get_current_patch() -> str:
    """Busca patch atual do TFT via DataDragon"""
    try:
        import requests
        r = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10)
        if r.status_code == 200:
            versions = r.json()
            for v in versions:
                if "14." in v or "15." in v:
                    return v
            return versions[0] if versions else ""
    except Exception as e:
        logging.debug(f"Erro ao buscar patch: {e}")
    return ""

def analyze_matches_for_rank(tier: str, rank: str = "", matches_per_player: int = 10,
                             players_per_rank: int = 5, patch_filter: str = None) -> tuple:
    tier_rank = f"{tier} {rank}" if rank else tier
    logging.info(f"Analisando {tier_rank}...")
    
    if not patch_filter:
        patch_filter = get_current_patch()
        if patch_filter:
            logging.info(f"Filtrando por patch: {patch_filter}")
    
    puuids = get_summoners_by_rank(tier, rank, count=players_per_rank)
    if not puuids:
        logging.warning(f"Nenhum PUUID encontrado para {tier_rank}")
        return {}, {}
    
    logging.info(f"Encontrados {len(puuids)} PUUIDs para {tier_rank}")
    
    comp_stats = {}
    augment_wins = Counter()
    augment_total = Counter()
    item_wins = defaultdict(lambda: Counter())
    item_total = defaultdict(lambda: Counter())
    counter_wins = Counter()
    counter_total = Counter()
    matches_analyzed = 0
    
    for puuid in puuids:
        if not puuid:
            continue
            
        match_ids = get_match_ids(puuid, count=matches_per_player)
        if not match_ids:
            continue
            
        for mid in match_ids:
            details = get_match_details(mid)
            if not details:
                continue
            
            info = details.get("info", {})
            game_version = info.get("game_version", "")
            if patch_filter and game_version and not game_version.startswith(patch_filter.split(".")[0]):
                logging.debug(f"Patch mismatch: {game_version} != {patch_filter}")
                continue
            
            matches_analyzed += 1
            participants = info.get("participants", [])
            
            all_comps = []
            for p in participants:
                placement = p.get("placement", 8)
                units = p.get("units", [])
                traits = p.get("traits", [])
                augments = p.get("augments", [])
                
                unit_ids = [u.get("character_id", "") for u in units if u.get("tier", 0) >= 2]
                if len(unit_ids) < 3:
                    continue
                
                active_traits = [t.get("name", "") for t in traits if t.get("tier_current", 0) >= 2]
                comp_key = ",".join(sorted(unit_ids[:5]))
                
                champion_items = {}
                for u in units:
                    cid = u.get("character_id", "")
                    items = u.get("items", [])
                    if cid and items:
                        champion_items[cid] = items
                
                all_comps.append({
                    "puuid": p.get("puuid", ""),
                    "comp_key": comp_key,
                    "placement": placement,
                    "units": unit_ids,
                    "items": champion_items,
                    "augments": augments,
                    "traits": active_traits
                })
                
                if p.get("puuid") == puuid and placement <= 4:
                    if comp_key not in comp_stats:
                        comp_stats[comp_key] = {
                            "units": unit_ids,
                            "traits": active_traits,
                            "placements": [],
                            "count": 0,
                            "items": Counter(),
                            "item_games": Counter(),
                            "augments": Counter(),
                            "augment_games": Counter()
                        }
                    comp_stats[comp_key]["placements"].append(placement)
                    comp_stats[comp_key]["count"] += 1
                    
                    for cid, items in champion_items.items():
                        for item in items:
                            comp_stats[comp_key]["items"][cid + ":" + item] += 1
                            comp_stats[comp_key]["item_games"][cid] += 1
                    
                    for aug in augments:
                        comp_stats[comp_key]["augments"][aug] += 1
                        comp_stats[comp_key]["augment_games"][aug] += 1
                
                for aug in augments:
                    if placement <= 4:
                        augment_wins[aug] += 1
                    augment_total[aug] += 1
                
                for cid, items in champion_items.items():
                    for item in items:
                        if placement <= 4:
                            item_wins[cid][item] += 1
                        item_total[cid][item] += 1
            
            for i, a in enumerate(all_comps):
                for j, b in enumerate(all_comps):
                    if i != j and a["comp_key"] != b["comp_key"]:
                        key = a["comp_key"] + " vs " + b["comp_key"]
                        counter_total[key] += 1
                        if a["placement"] < b["placement"]:
                            counter_wins[key] += 1
    
    logging.info(f"Analisados {matches_analyzed} matches para {tier_rank}")
    
    result = []
    for comp_key, stats in comp_stats.items():
        if stats["count"] < 2:
            continue
        
        avg_placement = sum(stats["placements"]) / len(stats["placements"])
        win_rate = (1 - (avg_placement - 1) / 7) * 100
        
        best_items = {}
        for cid_item, count in stats["items"].items():
            cid, item = cid_item.split(":", 1)
            games = stats["item_games"][cid]
            if games >= 2:
                wr = count / games * 100
                if cid not in best_items or wr > best_items[cid][1]:
                    best_items[cid] = (item, wr, count)
        
        core_items = {}
        for cid, (item, wr, count) in best_items.items():
            from core.data import pt
            champ_name = pt(cid) if cid.startswith("TFT17_") else cid
            core_items[champ_name] = [item]
        
        top_augs = sorted(stats["augments"].items(), key=lambda x: -x[1])[:3]
        aug_names = [a[0] for a in top_augs]
        
        result.append({
            "units": stats["units"],
            "traits": stats["traits"],
            "avg_placement": round(avg_placement, 2),
            "win_rate": round(win_rate, 1),
            "games": stats["count"],
            "core_items": core_items,
            "augments": aug_names
        })
    
    result.sort(key=lambda x: (x["win_rate"], x["games"]), reverse=True)
    
    counters = {}
    for key, total in counter_total.items():
        wins = counter_wins.get(key, 0)
        if total >= 3:
            counters[key] = round(wins / total * 100, 1)
    
    return result[:10], counters, patch_filter

def build_meta_from_api():
    """Constroi meta database usando dados da API por rank"""
    meta = {
        "comps": {},
        "last_updated": datetime.now().isoformat(),
        "source": "riot-api",
        "ranks_analyzed": [],
        "patch": ""
    }
    
    def _generate_comp_data(comp, tier, rank=""):
        units = comp["units"]
        
        core_items = comp.get("core_items", {})
        if not core_items:
            carry_items = [
                ["InfinityEdge", "LastWhisper", "GuinsoosRageblade"],
                ["BlueBuff", "JeweledGauntlet", "RabadonsDeathcap"]
            ]
            tank_items = [
                ["WarmogsArmor", "DragonsClaw", "GargoyleStoneplate"],
                ["LocketOfTheIronSolari", "FrozenHeart", "Redemption"]
            ]
            for j, u in enumerate(units[:2]):
                from core.data import pt
                core_items[pt(u)] = carry_items[j % 2]
            for j, u in enumerate(units[2:4]):
                from core.data import pt
                core_items[pt(u)] = tank_items[j % 2]
        
        augments = comp.get("augments", [])
        if not augments:
            augments = ["TraitTree", "Lineup"]
        
        tanks = units[-4:] if len(units) >= 4 else units[-2:]
        rank_label = f"{tier} {rank}" if rank else tier
        
        return {
            "units": units,
            "traits": comp["traits"],
            "tier": "S" if comp["win_rate"] > 60 else "A" if comp["win_rate"] > 50 else "B",
            "win_rate": comp["win_rate"],
            "avg_placement": comp["avg_placement"],
            "games": comp["games"],
            "rank_tier": tier,
            "rank_div": rank,
            "core_items": core_items,
            "augments": augments,
            "positioning": "Posicione baseado nos oponentes",
            "tanks": tanks,
            "levels": "Siga o nivel natural do jogo",
            "dicas": f"Comp forte em {rank_label} ({comp['win_rate']}% WR em {comp['games']} jogos)"
        }
    
    # Analisa TODOS os ranks, nao so os altos
    for tier in ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "EMERALD", "MASTER", "GRANDMASTER", "CHALLENGER"]:
        if tier in ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "EMERALD"]:
            for rank in ["IV", "III", "II", "I"]:
                logging.info(f"Analisando {tier} {rank}...")
                rank_data, tier_counters, used_patch = analyze_matches_for_rank(tier, rank)
                if rank_data:
                    rank_key = f"{tier}_{rank}"
                    meta["ranks_analyzed"].append(rank_key)
                    for key, wr in tier_counters.items():
                        meta.setdefault("counters", {})[key] = wr
                    for i, comp in enumerate(rank_data):
                        comp_name = f"{tier} {rank} Comp {i+1}"
                        meta["comps"][comp_name] = _generate_comp_data(comp, tier, rank)
        else:
            rank_data, tier_counters, used_patch = analyze_matches_for_rank(tier)
            if rank_data:
                meta["ranks_analyzed"].append(tier)
                for key, wr in tier_counters.items():
                    meta.setdefault("counters", {})[key] = wr
                for i, comp in enumerate(rank_data):
                    comp_name = f"{tier} Comp {i+1}"
                    meta["comps"][comp_name] = _generate_comp_data(comp, tier)
    
    if used_patch:
        meta["patch"] = used_patch
    return meta

import argparse

def main():
    parser = argparse.ArgumentParser(description="Atualiza meta do TFT via Riot API")
    parser.add_argument("--rank", type=str, help="Atualiza apenas um rank especifico (ex: GOLD_IV, MASTER)")
    parser.add_argument("--players", type=int, default=5, help="Jogadores por rank (default: 5)")
    parser.add_argument("--matches", type=int, default=10, help="Matches por jogador (default: 10)")
    args = parser.parse_args()
    
    logging.info("Iniciando update_meta.py com API Riot")
    
    if not RIOT_API_KEY:
        logging.error("RIOT_API_KEY nao configurada no .env")
        return
    
    # Se rank especifico, atualiza so ele
    if args.rank:
        parts = args.rank.upper().split("_")
        tier = parts[0]
        div = parts[1] if len(parts) > 1 else ""
        
        logging.info(f"Atualizando apenas {tier} {div}...")
        comp_data, counters, used_patch = analyze_matches_for_rank(tier, div, matches_per_player=args.matches, players_per_rank=args.players)
        
        if not comp_data:
            logging.warning(f"Nenhuma composicao encontrada para {tier} {div}")
            return
        
        meta = {
            "comps": {},
            "last_updated": datetime.now().isoformat(),
            "source": "riot-api",
            "ranks_analyzed": [f"{tier}_{div}" if div else tier],
            "counters": counters,
            "patch": used_patch or ""
        }
        
        rank_label = f"{tier} {div}" if div else tier
        for i, comp in enumerate(comp_data):
            comp_name = f"{rank_label} Comp {i+1}"
            
            units = comp["units"]
            core_items = comp.get("core_items", {})
            if not core_items:
                carry_items = [
                    ["InfinityEdge", "LastWhisper", "GuinsoosRageblade"],
                    ["BlueBuff", "JeweledGauntlet", "RabadonsDeathcap"]
                ]
                tank_items = [
                    ["WarmogsArmor", "DragonsClaw", "GargoyleStoneplate"],
                    ["LocketOfTheIronSolari", "FrozenHeart", "Redemption"]
                ]
                for j, u in enumerate(units[:2]):
                    from core.data import pt
                    core_items[pt(u)] = carry_items[j % 2]
                for j, u in enumerate(units[2:4]):
                    from core.data import pt
                    core_items[pt(u)] = tank_items[j % 2]
            
            augments = comp.get("augments", [])
            if not augments:
                augments = ["TraitTree", "Lineup"]
            
            tanks = units[-4:] if len(units) >= 4 else units[-2:]
            
            meta["comps"][comp_name] = {
                "units": units,
                "traits": comp["traits"],
                "tier": "S" if comp["win_rate"] > 60 else "A" if comp["win_rate"] > 50 else "B",
                "win_rate": comp["win_rate"],
                "avg_placement": comp["avg_placement"],
                "games": comp["games"],
                "rank_tier": tier,
                "rank_div": div,
                "core_items": core_items,
                "augments": augments,
                "positioning": "Posicione baseado nos oponentes",
                "tanks": tanks,
                "levels": "Siga o nivel natural do jogo",
                "dicas": f"Comp forte em {rank_label} ({comp['win_rate']}% WR em {comp['games']} jogos)"
            }
    else:
        # Constroi meta completo
        meta = build_meta_from_api()
    
    if not meta["comps"]:
        logging.warning("Nenhuma composicao encontrada via API. Usando fallback hardcoded.")
        # Fallback para hardcoded
        sys.path.insert(0, str(PROJECT_DIR))
        from core.meta_db import MetaDB
        mdb = MetaDB()
        meta = {
            "comps": mdb.data["comps"],
            "last_updated": datetime.now().isoformat(),
            "source": "hardcoded-fallback"
        }
        riot_key_mgr.record_error(500)
    else:
        riot_key_mgr.record_success()
    
    # Salva
    META_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    
    logging.info(f"Meta salvo em {META_JSON}")
    logging.info(f"Fonte: {meta.get('source', 'unknown')}")
    logging.info(f"Ranks analisados: {meta.get('ranks_analyzed', [])}")
    
    # Mostra resumo
    n_comps = len(meta.get("comps", {}))
    logging.info(f"Meta atualizado: {n_comps} composicoes")
    for name, comp in meta.get("comps", {}).items():
        tier = comp.get("tier", "?")
        wr = comp.get("win_rate", "N/A")
        logging.info(f"  {name} (T{tier}, {wr}% WR)")

if __name__ == "__main__":
    main()
