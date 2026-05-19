import os, requests, logging, time, threading, asyncio
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

from core.opponent_cache import opponent_cache_mgr

RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")

def _get_region():
    from core.config import get_riot_region, get_riot_platform
    return get_riot_region(), get_riot_platform()

def _headers():
    return {"X-Riot-Token": RIOT_API_KEY}

_analysis_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 300

# Caches locais (substituem profile_cache do antigo rate_limiter.py)
_profile_cache = {}
_summoner_cache = {}
_match_cache = {}

def _wait_for_token(timeout=15):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(opponent_cache_mgr._rate_limiter.wait_and_acquire(timeout=timeout))
    finally:
        loop.close()

def get_name_by_puuid(puuid: str) -> str | None:
    cached = _profile_cache.get(puuid)
    if cached and "gameName" in cached:
        return f"{cached.get('gameName', '')}#{cached.get('tagLine', '')}"
    
    if not _wait_for_token():
        return None
    
    region, platform = _get_region()
    try:
        r = requests.get(f"https://{platform}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}", headers=_headers(), timeout=5)
        if r.status_code == 200:
            data = r.json()
            _profile_cache[puuid] = data
            return f"{data.get('gameName', '')}#{data.get('tagLine', '')}"
        elif r.status_code == 429:
            logging.warning("Rate limit atingido em get_name_by_puuid")
    except Exception as e:
        logging.debug(f"Erro get_name_by_puuid: {e}")
    return None

def get_puuid(summoner_name: str, tag: str = "") -> str | None:
    cached = _summoner_cache.get(summoner_name)
    if cached:
        return cached["puuid"]
    
    if not _wait_for_token():
        return None
    
    region, platform = _get_region()
    if not tag: tag = region.upper()
    try:
        name = summoner_name.replace(" ", "%20")
        r = requests.get(f"https://{platform}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}", headers=_headers(), timeout=5)
        if r.status_code == 200:
            data = r.json()
            puuid = data.get("puuid")
            if puuid:
                summoner_id = get_summoner_id_by_puuid(puuid) or ""
                _summoner_cache[summoner_name] = {"puuid": puuid, "summoner_id": summoner_id}
            return puuid
        elif r.status_code == 429:
            logging.warning("Rate limit atingido em get_puuid")
    except Exception as e:
        logging.error(f"Erro ao buscar PUUID de {summoner_name}: {e}")
    return None

def get_summoner_id_by_puuid(puuid: str) -> str | None:
    if not _wait_for_token():
        return None
    
    region, platform = _get_region()
    try:
        r = requests.get(f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}", headers=_headers(), timeout=5)
        if r.status_code == 200:
            return r.json().get("id")
        elif r.status_code == 429:
            logging.warning("Rate limit atingido em get_summoner_id_by_puuid")
    except Exception as e:
        logging.debug(f"Erro get_summoner_id_by_puuid: {e}")
    return None

def get_tft_rank(summoner_id: str) -> str:
    if not _wait_for_token():
        return "Desconhecido"
    
    region, platform = _get_region()
    try:
        r = requests.get(f"https://{region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summoner_id}", headers=_headers(), timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data:
                for entry in data:
                    if entry.get("queueType") == "RANKED_TFT":
                        return f"{entry['tier']} {entry['rank']} ({entry['leaguePoints']} LP)"
            return "Sem Rank"
        elif r.status_code == 429:
            logging.warning("Rate limit atingido em get_tft_rank")
            return "Desconhecido"
    except Exception as e:
        logging.debug(f"Erro get_tft_rank: {e}")
    return "Desconhecido"

def get_match_ids(puuid: str, count: int = 10) -> list:
    if not _wait_for_token():
        return []
    
    region, platform = _get_region()
    try:
        r = requests.get(f"https://{platform}.api.riotgames.com/tft/match/v1/matches/by-puuid/{puuid}/ids", headers=_headers(), params={"count": count, "queue": 480}, timeout=10)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429:
            logging.warning("Rate limit atingido em get_match_ids")
    except Exception as e:
        logging.error(f"Erro ao buscar matches de {puuid}: {e}")
    return []

def get_match_details(match_id: str) -> dict | None:
    cached = _match_cache.get(match_id)
    if cached:
        return cached
    
    if not _wait_for_token():
        return None
    
    region, platform = _get_region()
    try:
        r = requests.get(f"https://{platform}.api.riotgames.com/tft/match/v1/matches/{match_id}", headers=_headers(), timeout=10)
        if r.status_code == 200:
            data = r.json()
            _match_cache[match_id] = data
            return data
        elif r.status_code == 429:
            logging.warning("Rate limit atingido em get_match_details")
    except Exception as e:
        logging.error(f"Erro ao buscar detalhes de {match_id}: {e}")
    return None

def analyze_opponent(summoner_name: str) -> dict:
    now = time.time()
    with _cache_lock:
        if summoner_name in _analysis_cache:
            cached = _analysis_cache[summoner_name]
            if now - cached["_timestamp"] < CACHE_TTL:
                logging.info(f"Cache hit para oponente: {summoner_name}")
                return {k: v for k, v in cached.items() if k != "_timestamp"}

    result = {"name": summoner_name, "comps": [], "traits": [], "avg_placement": 0, "recent_comps": [], "rank": "Desconhecido"}
    
    puuid = get_puuid(summoner_name)
    if not puuid:
        return result
    
    summoner_id = get_summoner_id_by_puuid(puuid)
    if summoner_id:
        result["rank"] = get_tft_rank(summoner_id)
    
    match_ids = get_match_ids(puuid, count=10)
    if not match_ids:
        return result
    
    placements = []
    comp_counts = {}
    trait_counts = {}
    
    for mid in match_ids:
        details = get_match_details(mid)
        if not details:
            continue
        
        info = details.get("info", {})
        participants = info.get("participants", [])
        
        for p in participants:
            if p.get("puuid") == puuid:
                placement = p.get("placement", 8)
                placements.append(placement)
                
                traits = p.get("traits", [])
                for t in traits:
                    name = t.get("name", "")
                    tier = t.get("tier", 0)
                    if name and tier >= 2:
                        trait_counts[name] = trait_counts.get(name, 0) + 1
                
                units = p.get("units", [])
                unit_names = [u.get("character_id", "") for u in units if u.get("tier", 0) >= 2]
                if unit_names:
                    comp_key = ", ".join(sorted(unit_names[:5]))
                    comp_counts[comp_key] = comp_counts.get(comp_key, 0) + 1
                
                break
    
    result["avg_placement"] = round(sum(placements) / len(placements), 1) if placements else 0
    result["recent_comps"] = sorted(comp_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    result["traits"] = sorted(trait_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    with _cache_lock:
        cache_entry = dict(result)
        cache_entry["_timestamp"] = now
        _analysis_cache[summoner_name] = cache_entry
    
    return result

def analyze_all_opponents(opponent_names: list) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(opponent_names), 3)) as executor:
        futures = {}
        for name in opponent_names:
            if name and name != "?":
                futures[executor.submit(analyze_opponent, name)] = name
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                logging.error(f"Erro ao analisar {name}: {e}")
                results[name] = {"name": name, "comps": [], "traits": [], "avg_placement": 0, "rank": "Erro"}
    return results
