import os, requests, logging, urllib3
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import StrEnum

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GamePhase(StrEnum):
    NONE = "None"
    LOBBY = "Lobby"
    MATCHMAKING = "Matchmaking"
    READY_CHECK = "ReadyCheck"
    CHAMP_SELECT = "ChampSelect"
    GAME_START = "GameStart"
    IN_PROGRESS = "InProgress"
    RECONNECT = "Reconnect"
    PRE_END_OF_GAME = "PreEndOfGame"
    WAITING_FOR_STATS = "WaitingForStats"
    END_OF_GAME = "EndOfGame"
    TERMINATED = "Terminated"
    UNKNOWN = "Unknown"

GAME_PHASES_ACTIVE = {GamePhase.CHAMP_SELECT, GamePhase.GAME_START, GamePhase.IN_PROGRESS}
GAME_PHASES_ENDED = {GamePhase.WAITING_FOR_STATS, GamePhase.END_OF_GAME, GamePhase.TERMINATED}
GAME_PHASES_IDLE = {GamePhase.NONE, GamePhase.LOBBY, GamePhase.MATCHMAKING, GamePhase.READY_CHECK}

@dataclass
class GameState:
    phase: str = "Unknown"
    stage: str = "1-1"
    gold: int = 0
    level: int = 1
    my_board: List[str] = field(default_factory=list)
    shop: List[str] = field(default_factory=list)
    my_augments: List[str] = field(default_factory=list)
    opponents: List[Dict] = field(default_factory=list)
    is_tft: bool = False
    game_active: bool = False

def get_lcu_creds() -> Optional[tuple]:
    possible_paths = [
        "D:\\Riot Games\\League of Legends\\lockfile",
        "C:\\Riot Games\\League of Legends\\lockfile",
        "C:\\Program Files\\Riot Games\\League of Legends\\lockfile",
        "D:\\Riot Games\\League of Legends (PBE)\\lockfile",
        os.path.join(os.environ.get("LOCALAPPDATA",""), "Riot Games", "League of Legends", "lockfile"),
    ]
    
    for lf in possible_paths:
        if not os.path.exists(lf): continue
        try:
            with open(lf, "r", encoding="utf-8") as f:
                p = f.read().strip().split(":")
            if len(p) >= 5 and p[2].isdigit() and "League" in p[0]:
                return (p[2], p[3])
        except Exception as e:
            logging.debug(f"Erro lendo lockfile {lf}: {e}")
            continue
    return None

def fetch_session(port: str, pwd: str) -> Optional[dict]:
    try:
        r = requests.get(f"https://127.0.0.1:{port}/lol-gameflow/v1/session", auth=("riot", pwd), verify=False, timeout=3)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logging.debug(f"Erro fetch_session: {e}")
        return None

def parse_state(session: Optional[dict]) -> GameState:
    st = GameState()
    if not session: return st
    try:
        gd = session.get("gameData") or {}
        st.phase = session.get("phase") or gd.get("gamePhase", "Unknown")
        
        # GameMode pode estar em diferentes lugares
        game_mode = gd.get("gameMode") or (gd.get("queue") or {}).get("gameMode") or ""
        if game_mode != "TFT": return st
        st.is_tft = True
        st.stage = str(gd.get("gameStage", "1-1"))
        st.game_active = st.phase in {GamePhase.IN_PROGRESS, GamePhase.RECONNECT, GamePhase.PRE_END_OF_GAME}
        
        pd = gd.get("playerData") or {}
        st.gold = int(pd.get("currentGold", 0))
        st.level = int(pd.get("level", 1))
        st.my_board = [u.get("name","") for u in (pd.get("champions") or []) if isinstance(u, dict) and u.get("name")]
        st.shop = [c.get("name","") for c in (pd.get("shopChampions") or []) if isinstance(c, dict) and c.get("name")]
        
        augments_raw = (pd.get("augments") or []) + (gd.get("augments") or [])
        st.my_augments = [a.get("name","") for a in augments_raw if isinstance(a, dict) and a.get("name")]
        
        opps = gd.get("opponentData", [])
        my_id = pd.get("playerId")
        if isinstance(opps, dict):
            items = list(opps.values())
        else:
            items = opps if isinstance(opps, list) else []
        for o in items:
            if isinstance(o, dict) and o.get("playerId") != my_id:
                st.opponents.append({
                    "name": o.get("summonerName", "?"),
                    "board": [u.get("name","") for u in (o.get("champions") or []) if isinstance(u, dict) and u.get("name")],
                    "health": int(o.get("health", 100)),
                    "traits": [t.get("name","") for t in (o.get("activeTraits") or []) if isinstance(t, dict) and t.get("tier",0) >= 2]
                })
    except Exception as e: logging.error(f"LCU parse error: {e}")
    return st