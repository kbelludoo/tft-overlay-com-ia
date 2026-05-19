"""Wrapper seguro para chamadas externas com retry, jitter, e deteccao de patch"""
import os, json, time, logging, random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import requests

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
CACHE_FILE = DATA_DIR / "api_cache.json"
PATCH_FILE = DATA_DIR / "current_patch.txt"

RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")

DEFAULT_HEADERS = {
    "User-Agent": "TFT-AI-Overlay/5.0",
    "Accept": "application/json",
}


class SafeRequest:
    """Wrapper com retry exponencial, jitter, e rate limit handling"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, timeout: float = 10.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self._last_status = {}  # Rate limit tracking per domain
        self._rate_limit_until = 0  # Timestamp quando rate limit expira
        self._rate_limit_remaining = 0  # Segundos restantes de rate limit
    
    @property
    def is_rate_limited(self) -> bool:
        """Verifica se esta em rate limit"""
        return time.time() < self._rate_limit_until
    
    @property
    def rate_limit_seconds_remaining(self) -> int:
        """Retorna segundos restantes de rate limit"""
        remaining = int(self._rate_limit_until - time.time())
        return max(0, remaining)
    
    def get(self, url: str, headers: dict = None, params: dict = None, use_key: bool = False) -> Optional[dict]:
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        if use_key and RIOT_API_KEY:
            req_headers["X-Riot-Token"] = RIOT_API_KEY
        
        for attempt in range(self.max_retries):
            try:
                # Jitter anti-deteccao
                jitter = random.uniform(0.1, 0.5)
                time.sleep(jitter)
                
                r = requests.get(url, headers=req_headers, params=params, timeout=self.timeout)
                
                # Rate limit 429
                if r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 5))
                    self._rate_limit_until = time.time() + retry_after
                    self._rate_limit_remaining = retry_after
                    logging.warning(f"Rate limit em {url}. Aguardando {retry_after}s")
                    time.sleep(retry_after + jitter)
                    continue
                
                # Erro client (4xx)
                if 400 <= r.status_code < 500:
                    logging.warning(f"Client error {r.status_code} em {url}: {r.text[:200]}")
                    return None
                
                # Erro server (5xx) - retry
                if r.status_code >= 500:
                    delay = self.base_delay * (2 ** attempt) + jitter
                    logging.warning(f"Server error {r.status_code} em {url}. Retry em {delay:.1f}s")
                    time.sleep(delay)
                    continue
                
                # Sucesso
                if r.status_code == 200:
                    try:
                        return r.json()
                    except ValueError:
                        return {"_raw": r.text}
                
            except requests.exceptions.Timeout:
                delay = self.base_delay * (2 ** attempt) + jitter
                logging.warning(f"Timeout em {url} (try {attempt+1}). Retry em {delay:.1f}s")
                time.sleep(delay)
            except requests.exceptions.ConnectionError:
                delay = self.base_delay * (2 ** attempt) + jitter
                logging.warning(f"Connection error em {url} (try {attempt+1}). Retry em {delay:.1f}s")
                time.sleep(delay)
            except Exception as e:
                logging.error(f"Erro inesperado em {url}: {e}")
                return None
        
        logging.error(f"Falha apos {self.max_retries} tentativas: {url}")
        return None


# Instancia global
safe_req = SafeRequest()


def get_current_patch() -> Optional[str]:
    """Detecta patch atual via Data Dragon (mais confiavel que Community Dragon)"""
    # Tenta Data Dragon primeiro (endpoint publico e confiavel da Riot)
    try:
        data = safe_req.get("https://ddragon.leagueoflegends.com/api/versions.json")
        if data and isinstance(data, list) and len(data) > 0:
            # Data Dragon retorna lista de versoes, a primeira e a mais recente
            patch = data[0]  # Ex: "15.11.1"
            if patch:
                return patch
    except Exception as e:
        logging.warning(f"Erro ao detectar patch via Data Dragon: {e}")
    
    # Fallback: tenta Community Dragon
    try:
        data = safe_req.get("https://raw.communitydragon.org/latest/data/info/info.json")
        if data and isinstance(data, dict):
            patch = data.get("version", "")
            if patch:
                return patch
    except Exception as e:
        logging.warning(f"Erro ao detectar patch via Community Dragon: {e}")
    
    return None


def check_patch_change() -> bool:
    """Verifica se o patch mudou desde a ultima vez"""
    current = get_current_patch()
    if not current:
        return False
    
    last = ""
    if PATCH_FILE.exists():
        last = PATCH_FILE.read_text().strip()
    
    changed = current != last
    if changed:
        PATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        PATCH_FILE.write_text(current)
    return changed


def fetch_champion_list(patch: str = None) -> dict:
    """Busca lista de campeoes do patch atual via Community Dragon"""
    if not patch:
        patch = get_current_patch() or "pbe"
    
    cache_key = f"champs_{patch}"
    cached = _load_cache(cache_key, ttl_hours=24)
    if cached:
        return cached
    
    try:
        url = f"https://raw.communitydragon.org/{patch}/info/champions.json"
        data = safe_req.get(url)
        if data and isinstance(data, list):
            result = {}
            for c in data:
                cid = c.get("id", "")
                name = c.get("name", "")
                if cid and name:
                    result[cid] = name
            _save_cache(cache_key, result)
            return result
    except Exception as e:
        logging.warning(f"Erro ao buscar campeoes: {e}")
    
    return {}


def fetch_item_list(patch: str = None) -> dict:
    """Busca lista de itens do patch atual via Community Dragon"""
    if not patch:
        patch = get_current_patch() or "pbe"
    
    cache_key = f"items_{patch}"
    cached = _load_cache(cache_key, ttl_hours=24)
    if cached:
        return cached
    
    try:
        url = f"https://raw.communitydragon.org/{patch}/info/items.json"
        data = safe_req.get(url)
        if data and isinstance(data, list):
            result = {}
            for item in data:
                iid = str(item.get("id", ""))
                name = item.get("name", "")
                if iid and name:
                    result[iid] = name
            _save_cache(cache_key, result)
            return result
    except Exception as e:
        logging.warning(f"Erro ao buscar itens: {e}")
    
    return {}


def fetch_augment_list(patch: str = None) -> dict:
    """Busca lista de augments do patch atual via Community Dragon"""
    if not patch:
        patch = get_current_patch() or "pbe"
    
    cache_key = f"augments_{patch}"
    cached = _load_cache(cache_key, ttl_hours=24)
    if cached:
        return cached
    
    try:
        url = f"https://raw.communitydragon.org/{patch}/info/sets/tft.json"
        data = safe_req.get(url)
        if data:
            augments = data.get("augments", [])
            result = {}
            for aug in augments:
                aid = aug.get("id", "")
                name = aug.get("name", "")
                if aid and name:
                    result[aid] = name
            _save_cache(cache_key, result)
            return result
    except Exception as e:
        logging.warning(f"Erro ao buscar augments: {e}")
    
    return {}


def sanitize_str(value, default="", max_len=200) -> str:
    """Sanitiza string: remove caracteres perigosos, limita tamanho"""
    if not value or not isinstance(value, str):
        return default
    # Remove null bytes e caracteres de controle
    cleaned = "".join(c for c in value if c.isprintable() or c in "\n\r\t")
    return cleaned[:max_len] if cleaned else default


def sanitize_int(value, default=0, min_val=0, max_val=9999) -> int:
    """Sanitiza inteiro com limites"""
    try:
        v = int(value)
        return max(min_val, min(max_val, v))
    except (ValueError, TypeError):
        return default


def sanitize_list(value, default=None) -> list:
    """Sanitiza lista: garante que e lista e limita tamanho"""
    if default is None:
        default = []
    if not isinstance(value, list):
        return default
    return value[:50]  # Max 50 itens


def sanitize_dict(value, default=None) -> dict:
    """Sanitiza dict: garante que e dict"""
    if default is None:
        default = {}
    if not isinstance(value, dict):
        return default
    return value


def _load_cache(key: str, ttl_hours: int = 24) -> Optional[dict]:
    """Carrega dado do cache se nao expirado"""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        entry = cache.get(key)
        if not entry:
            return None
        expires = datetime.fromisoformat(entry.get("expires", ""))
        if datetime.now() > expires:
            del cache[key]
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
            return None
        return entry.get("data")
    except Exception:
        return None


def _save_cache(key: str, data: dict, ttl_hours: int = 24):
    """Salva dado no cache com TTL"""
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    
    cache[key] = {
        "data": data,
        "expires": (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
    }
    
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
