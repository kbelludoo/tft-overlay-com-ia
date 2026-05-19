import os, requests, logging, base64
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")

def _get_region():
    from core.config import get_riot_region, get_riot_platform
    return get_riot_region(), get_riot_platform()

def _headers():
    return {"X-Riot-Token": RIOT_API_KEY}

def get_my_rank() -> dict:
    region, platform = _get_region()
    try:
        from core.lcu_parser import get_lcu_creds
        creds = get_lcu_creds()
        if not creds:
            return {"tier": "Unknown", "rank": "", "lp": 0}
        
        port, pwd = creds
        auth = base64.b64encode(f'riot:{pwd}'.encode()).decode()
        lcu_headers = {"Authorization": f"Basic {auth}"}
        
        # Passo 1: obtem PUUID via LCU
        r = requests.get(f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
                         headers=lcu_headers, verify=False, timeout=3)
        if r.status_code != 200:
            return {"tier": "Unknown", "rank": "", "lp": 0}
        
        summoner_data = r.json()
        encrypted_summoner_id = summoner_data.get("id", "")
        puuid = summoner_data.get("puuid", "")
        
        # Passo 2: obtem TFT rank via Riot API (usa encryptedSummonerId)
        if encrypted_summoner_id and RIOT_API_KEY:
            r = requests.get(f"https://{region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{encrypted_summoner_id}",
                             headers=_headers(), timeout=5)
            if r.status_code == 200:
                entries = r.json()
                for entry in entries:
                    if entry.get("queueType") == "RANKED_TFT":
                        return {
                            "tier": entry.get("tier", "Unknown"),
                            "rank": entry.get("rank", ""),
                            "lp": entry.get("leaguePoints", 0)
                        }
        
        # Fallback: tenta via PUUID (endpoint alternativo)
        if puuid and RIOT_API_KEY:
            r = requests.get(f"https://{region}.api.riotgames.com/tft/league/v1/by-puuid/{puuid}",
                             headers=_headers(), timeout=5)
            if r.status_code == 200:
                data = r.json()
                return {
                    "tier": data.get("tier", "Unknown"),
                    "rank": data.get("rank", ""),
                    "lp": data.get("leaguePoints", 0)
                }
        
    except Exception as e:
        logging.error(f"Erro ao buscar rank: {e}")
    
    return {"tier": "Unknown", "rank": "", "lp": 0}

def get_comps_for_rank(tier: str) -> list:
    try:
        from core.meta_db import MetaDB
        mdb = MetaDB(player_rank_tier=tier)
        top = mdb.get_top_comps()
        return [c.get("name", "") for c in top if c.get("name")]
    except Exception as e:
        logging.warning(f"Erro ao buscar comps para rank {tier}: {e}")
        return []
