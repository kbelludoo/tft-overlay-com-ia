import json, logging, base64, os, uuid, requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.data import to_tft17
from core.config import load_config, get_tft_set
from core.opponent_cache import opponent_cache_mgr
from core.lcu_parser import GamePhase
from core.opponent_tracker import get_tft_rank
from core.logging_utils import log_critical_error

_opponent_cache = set()
_OPPONENT_STATE_FILE = Path(__file__).parent.parent / "data" / "opponent_state.json"

def _save_opponent_state():
    global _opponent_cache
    try:
        _OPPONENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_OPPONENT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"opponents": list(_opponent_cache)}, f, indent=2)
    except Exception as e:
        logging.exception(f"Erro ao salvar estado oponentes: {e}")

def _load_opponent_state():
    global _opponent_cache
    try:
        if _OPPONENT_STATE_FILE.exists():
            with open(_OPPONENT_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _opponent_cache = set(data.get("opponents", []))
            logging.info(f"Estado oponentes carregado: {len(_opponent_cache)} nomes")
    except Exception as e:
        logging.warning(f"Erro ao carregar estado oponentes: {e}")

_load_opponent_state()

def get_team_import_code(units: list, creds: tuple) -> str:
    cfg = load_config()
    tft_set = get_tft_set(cfg)
    import urllib3
    urllib3.disable_warnings()
    try:
        port, pwd = creds
        auth = base64.b64encode(f'riot:{pwd}'.encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}

        champs = []
        for u in units:
            if u.startswith("TFT17_"):
                champs.append(u)
            else:
                tid = to_tft17(u)
                if tid:
                    champs.append(tid)

        if not champs:
            logging.warning(f"Nenhum campeao valido para import code. Units recebidos: {units}")
            return ""

        skipped = [u for u in units if not u.startswith("TFT17_") and not to_tft17(u)]
        if skipped:
            logging.warning(f"Campeoes ignorados (sem conversao TFT17): {skipped}")

        logging.info(f"Enviando para API LCU: {champs}")
        team_id = str(uuid.uuid4())

        r = requests.put(
            f"https://127.0.0.1:{port}/lol-tft-team-planner/v1/sets/{tft_set}/teams/{team_id}",
            headers=headers, json={"champions": champs}, verify=False, timeout=5
        )
        if r.status_code not in (200, 204):
            logging.warning(f"Falha ao criar time na LCU: HTTP {r.status_code}")
            return ""
        logging.info(f"PUT team {team_id}: HTTP {r.status_code}")

        r = requests.post(
            f"https://127.0.0.1:{port}/lol-tft-team-planner/v1/sets/{tft_set}/teams/{team_id}/import",
            headers=headers, json=champs, verify=False, timeout=5
        )
        if r.status_code in (200, 204):
            r2 = requests.post(
                f"https://127.0.0.1:{port}/lol-tft-team-planner/v1/sets/{tft_set}/team-code/{team_id}",
                headers=headers, verify=False, timeout=5
            )
            if r2.status_code == 200:
                code = r2.json().strip('"')
                logging.info(f"Codigo gerado: {code} para {len(champs)} campeoes")
                return code
        else:
            logging.warning(f"Falha ao importar time: HTTP {r.status_code} - {r.text[:200]}")
    except Exception as e:
        logging.warning(f"Erro ao gerar import code: {e}")
    return ""


def extract_opponent_names(session: dict, creds: tuple) -> list:
    port, pwd = creds
    auth = base64.b64encode(f'riot:{pwd}'.encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    opp_data = []
    seen_names = set()
    phase = session.get("phase") or (session.get("gameData") or {}).get("gamePhase", "")
    gd = session.get("gameData", {})

    logging.info(f"extract_opponent_names phase={phase}, gameData keys={list(gd.keys())}")

    if phase in {GamePhase.CHAMP_SELECT, GamePhase.GAME_START}:
        try:
            r = requests.get(f"https://127.0.0.1:{port}/lol-champ-select/v1/session",
                             headers=headers, verify=False, timeout=5)
            if r.status_code == 200:
                cs = r.json()
                for cell in cs.get("myTeam", []):
                    sid = cell.get("summonerId", 0)
                    if sid and sid > 0:
                        try:
                            r2 = requests.get(f"https://127.0.0.1:{port}/lol-summoner/v1/summoners/{sid}",
                                              headers=headers, verify=False, timeout=3)
                            if r2.status_code == 200:
                                d = r2.json()
                                name = d.get("gameName", "") or d.get("displayName", "")
                                if name and name not in seen_names:
                                    seen_names.add(name)
                                    opp_data.append({"name": name, "summonerId": str(sid)})
                        except Exception as e:
                            logging.debug(f"Erro ao resolver summoner {sid}: {e}")
                logging.info(f"ChampSelect: {len(opp_data)} jogadores capturados")
        except Exception as e:
            logging.warning(f"Erro champ-select: {e}")

    for team_key in ("teamOne", "teamTwo"):
        team = gd.get(team_key, [])
        if not isinstance(team, list): continue
        for p in team:
            if not isinstance(p, dict): continue
            sid = p.get("summonerId")
            name_raw = p.get("summonerName", "")
            if not name_raw or not name_raw.strip():
                continue
            if sid and sid > 0:
                if name_raw and name_raw not in seen_names:
                    seen_names.add(name_raw)
                    opp_data.append({"name": name_raw, "summonerId": str(sid)})
                    continue
                try:
                    r = requests.get(f"https://127.0.0.1:{port}/lol-summoner/v1/summoners/{sid}",
                                      headers=headers, verify=False, timeout=3)
                    if r.status_code == 200:
                        d = r.json()
                        name = d.get("gameName", "") or d.get("displayName", "")
                        if name and name not in seen_names:
                            seen_names.add(name)
                            opp_data.append({"name": name, "summonerId": str(sid)})
                except Exception as e:
                    logging.warning(f"Erro ao resolver summonerId {sid}: {e}")

    my_name = ""
    try:
        r = requests.get(f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
                          headers=headers, verify=False, timeout=3)
        if r.status_code == 200:
            d = r.json()
            my_name = d.get("gameName", "") or d.get("displayName", "")
            my_sid = str(d.get("summonerId", ""))
    except Exception as e:
        logging.debug(f"Erro ao remover proprio jogador: {e}")

    opp_data = [o for o in opp_data if o["name"] != my_name]

    new_names = {o["name"] for o in opp_data}
    if new_names:
        _opponent_cache.update(new_names)
        _save_opponent_state()
    if _opponent_cache:
        for name in list(_opponent_cache):
            if name not in seen_names:
                seen_names.add(name)
                opp_data.append({"name": name, "summonerId": ""})

    result = opp_data[:7]
    logging.info(f"extract_opponent_names: {len(result)} oponentes: {[o['name'] for o in result]}")
    return result


def fetch_opponents_rank(opponents_with_ids: list) -> dict:
    rank_map = {}
    uncached = []
    for o in opponents_with_ids:
        name = o["name"]
        cached = opponent_cache_mgr.get(name)
        if cached and cached.get("rank"):
            rank_map[name] = cached["rank"]
        else:
            uncached.append(o)
    if uncached:
        with ThreadPoolExecutor(max_workers=min(len(uncached), 4)) as executor:
            futures = {}
            for o in uncached:
                sid = o.get("summonerId", "")
                if sid:
                    futures[executor.submit(get_tft_rank, sid)] = o["name"]
            for future in as_completed(futures):
                name = futures[future]
                try:
                    rank = future.result()
                    rank_map[name] = rank
                    if rank:
                        opponent_cache_mgr.set(name, {"name": name, "rank": rank})
                except Exception as e:
                    log_critical_error("fetch_opponents_rank", e, name)
                    rank_map[name] = "Desconhecido"
    return rank_map


def detect_next_opponent(session: dict, creds: tuple) -> str | None:
    port, pwd = creds
    auth = base64.b64encode(f'riot:{pwd}'.encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    gd = session.get("gameData", {}) or {}

    for key in ("currentOpponentId", "opponentPlayerId", "nextOpponentId", "opponentSummonerId"):
        val = gd.get(key) or (gd.get("playerData") or {}).get(key)
        if val:
            logging.info(f"detect_next_opponent: encontrado {key}={val}")
            try:
                r = requests.get(f"https://127.0.0.1:{port}/lol-summoner/v1/summoners/{val}",
                                  headers=headers, verify=False, timeout=3)
                if r.status_code == 200:
                    name = r.json().get("gameName", "") or r.json().get("displayName", "")
                    if name:
                        return name
            except Exception as e:
                logging.debug(f"Erro ao resolver next opponent: {e}")

    opponent_data = gd.get("opponentData", [])
    if isinstance(opponent_data, list):
        for o in opponent_data:
            if isinstance(o, dict) and o.get("isFighting"):
                return o.get("summonerName") or o.get("gameName")
    elif isinstance(opponent_data, dict):
        for k, o in opponent_data.items():
            if isinstance(o, dict) and o.get("isFighting"):
                return o.get("summonerName") or o.get("gameName")

    return None
