"""
Cache Persistente de Oponentes + Rate Limiter Adaptativo.

Persiste _analysis_cache em data/opponent_cache.db (SQLite) com coluna
expires_at. Limpeza automática no startup. Rate limiter usa token bucket
assíncrono para evitar 429s.

Classes:
- OpponentCache: cache SQLite persistente
- AdaptiveRateLimiter: token bucket assíncrono com adaptação
- OpponentCacheManager: coordena cache + rate limiting
"""
import sqlite3
import json
import logging
import asyncio
import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from collections import deque

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent.parent
CACHE_DB = PROJECT_DIR / "data" / "opponent_cache.db"

# Configurações de cache
CACHE_TTL_SECONDS = 300  # 5 minutos
CLEANUP_INTERVAL_HOURS = 24
CACHE_SCHEMA_VERSION = 1


@dataclass
class CachedOpponentData:
    """Dados de oponente em cache."""
    name: str
    puuid: Optional[str]
    summoner_id: Optional[str]
    rank: str
    avg_placement: float
    recent_comps: List[tuple]
    traits: List[tuple]
    cached_at: datetime
    expires_at: datetime


class OpponentCache:
    """
    Cache persistente de dados de oponentes.
    Armazena em SQLite para sobreviver a reinícios.
    """

    def __init__(self, db_path: str = None):
        self._db_path = db_path or str(CACHE_DB)
        self._lock = threading.Lock()
        self._init_db()
        self._cleanup_old_entries()

    def _init_db(self):
        """Inicializa tabela do cache com índices e schema versioning."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opponent_cache (
                    name TEXT PRIMARY KEY,
                    puuid TEXT,
                    summoner_id TEXT,
                    rank TEXT,
                    avg_placement REAL,
                    recent_comps TEXT,
                    traits TEXT,
                    cached_at TEXT,
                    expires_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opponent_puuid ON opponent_cache(puuid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opponent_summoner ON opponent_cache(summoner_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opponent_rank ON opponent_cache(rank)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opponent_expires ON opponent_cache(expires_at)")
            conn.execute("PRAGMA user_version = 1")
            logging.info("OpponentCache: migrated to v1 (base tables)")
        conn.commit()
        conn.close()
        logger.info(f"OpponentCache inicializado em {self._db_path}")

    def _cleanup_old_entries(self):
        """Remove entradas expiradas."""
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            now = datetime.now().isoformat()
            result = conn.execute(
                "DELETE FROM opponent_cache WHERE expires_at < ?", (now,)
            ).rowcount
            if result > 0:
                logger.info(f"Limpeza: {result} entradas expiradas removidas")
        except Exception as e:
            logger.error(f"Erro na limpeza: {e}")
        finally:
            conn.close()

    def get(self, name: str) -> Optional[Dict]:
        """Busca oponente no cache se não expirou."""
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            now = datetime.now().isoformat()
            row = conn.execute(
                """SELECT puuid, summoner_id, rank, avg_placement,
                          recent_comps, traits, cached_at
                   FROM opponent_cache
                   WHERE name = ? AND expires_at > ?""",
                (name, now)
            ).fetchone()

            if row:
                return {
                    "name": name,
                    "puuid": row[0],
                    "summoner_id": row[1],
                    "rank": row[2],
                    "avg_placement": row[3],
                    "recent_comps": json.loads(row[4]) if row[4] else [],
                    "traits": json.loads(row[5]) if row[5] else [],
                    "cached_at": row[6]
                }
        except Exception as e:
            logger.error(f"Erro ao buscar cache: {e}")
        finally:
            conn.close()
        return None

    def set(self, name: str, data: Dict, ttl_seconds: int = None):
        """Salva oponente no cache."""
        ttl = ttl_seconds or CACHE_TTL_SECONDS
        now = datetime.now()
        expires = now + timedelta(seconds=ttl)

        conn = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO opponent_cache
                (name, puuid, summoner_id, rank, avg_placement,
                 recent_comps, traits, cached_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                data.get("puuid"),
                data.get("summoner_id"),
                data.get("rank", "Desconhecido"),
                data.get("avg_placement", 8.0),
                json.dumps(data.get("recent_comps", [])),
                json.dumps(data.get("traits", [])),
                now.isoformat(),
                expires.isoformat()
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar cache: {e}")
        finally:
            conn.close()

    def get_all(self) -> Dict[str, Dict]:
        """Retorna todos os oponentes válidos no cache."""
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        result = {}
        try:
            now = datetime.now().isoformat()
            rows = conn.execute(
                """SELECT name, puuid, summoner_id, rank, avg_placement,
                          recent_comps, traits, cached_at
                   FROM opponent_cache
                   WHERE expires_at > ?""",
                (now,)
            ).fetchall()

            for row in rows:
                result[row[0]] = {
                    "name": row[0],
                    "puuid": row[1],
                    "summoner_id": row[2],
                    "rank": row[3],
                    "avg_placement": row[4],
                    "recent_comps": json.loads(row[5]) if row[5] else [],
                    "traits": json.loads(row[6]) if row[6] else [],
                    "cached_at": row[7]
                }
        except Exception as e:
            logger.error(f"Erro ao buscar todos: {e}")
        finally:
            conn.close()
        return result

    def invalidate(self, name: str):
        """Invalidar entrada específica."""
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            conn.execute("DELETE FROM opponent_cache WHERE name = ?", (name,))
            conn.commit()
        finally:
            conn.close()


class AdaptiveRateLimiter:
    """
    Rate limiter adaptativo usando token bucket assíncrono.
    Adapta baseado em 429s e latência.
    """

    def __init__(self, rate: int = 100, per_seconds: int = 120,
                 initial_tokens: int = None):
        # rate = chamadas permitidas
        # per_seconds = janela de tempo
        self._rate = rate
        self._per_seconds = per_seconds
        self._tokens = initial_tokens or rate
        self._last_update = time.time()
        self._lock = asyncio.Lock()

        # Histórico para adaptação
        self._recent_429s = deque(maxlen=10)
        self._recent_latencies = deque(maxlen=20)

        # Estado
        self._cooldown_until = 0.0

    async def _refill_tokens(self):
        """Refill tokens baseado no tempo decorrido."""
        now = time.time()
        elapsed = now - self._last_update
        self._last_update = now

        # Adicionar tokens proporcionais
        tokens_to_add = (elapsed / self._per_seconds) * self._rate
        self._tokens = min(self._rate, self._tokens + tokens_to_add)

    async def acquire(self, timeout: float = 10.0) -> bool:
        """Tenta adquirir token para fazer chamada."""
        async with self._lock:
            await self._refill_tokens()

            # Verificar cooldown forçado
            if time.time() < self._cooldown_until:
                logger.debug("Rate limiter em cooldown forçado")
                return False

            if self._tokens >= 1:
                self._tokens -= 1
                return True

            # Não há tokens disponíveis
            return False

    async def wait_and_acquire(self, timeout: float = 30.0) -> bool:
        """Espera até adquirir token ou timeout."""
        start = time.time()
        while (time.time() - start) < timeout:
            if await self.acquire():
                return True
            await asyncio.sleep(0.1)
        return False

    def report_success(self, latency: float):
        """Reporta sucesso - ajusta para usar menos tokens."""
        self._recent_latencies.append(latency)
        # Se latência está alta, pode estar perto do limite
        avg_latency = sum(self._recent_latencies) / len(self._recent_latencies) if self._recent_latencies else 0
        if avg_latency > 2.0:  # >2s de latência
            # Reduzir slightly
            self._tokens = max(0, self._tokens - 0.1)

    def report_429(self):
        """Reporta 429 - ativa cooldown e reduz tokens."""
        self._recent_429s.append(time.time())
        self._cooldown_until = time.time() + 5.0  # 5s de cooldown
        # Reduzir significativamente
        self._tokens = max(0, self._tokens * 0.5)
        logger.warning("429 detectado - rate limiter ajustando")

    def is_in_cooldown(self) -> bool:
        """Verifica se está em cooldown."""
        return time.time() < self._cooldown_until

    def get_status(self) -> Dict:
        """Retorna status do rate limiter."""
        return {
            "tokens_available": round(self._tokens, 1),
            "rate": self._rate,
            "per_seconds": self._per_seconds,
            "in_cooldown": self.is_in_cooldown(),
            "recent_429s": len(self._recent_429s)
        }


class OpponentCacheManager:
    """
    Coordena cache de oponentes + rate limiting.
    Wrapper unificado para opponent_tracker.py usar.
    """

    def __init__(self, rate: int = 100, per_seconds: int = 120):
        self._cache = OpponentCache()
        self._rate_limiter = AdaptiveRateLimiter(rate, per_seconds)

        # Callbacks para API calls
        self._api_callbacks = {}

    def get(self, name: str) -> Optional[Dict]:
        """Busca dados de um oponente (cache + rate limit)."""
        return self._cache.get(name)

    def set(self, name: str, data: Dict, ttl_seconds: int = None):
        """Salva dados de um oponente no cache."""
        self._cache.set(name, data, ttl_seconds)

    def invalidate(self, name: str):
        """Remove um oponente do cache."""
        self._cache.invalidate(name)

    def get_all(self) -> Dict[str, Dict]:
        """Retorna todos os oponentes em cache."""
        return self._cache.get_all()

    def register_api(self, name: str, callback: callable):
        """Registra API call para usar com rate limiting."""
        self._api_callbacks[name] = callback

    async def get_with_limit(self, api_name: str, key: str, fallback_fn: callable) -> Optional[Dict]:
        """
        Busca dados usando cache + rate limit.
        Se cache existe e válido, retorna.
        Se não, faz API call com rate limiting.
        """
        # 1. Verificar cache
        cached = self._cache.get(key)
        if cached:
            logger.debug(f"Cache hit para {key}")
            return cached

        # 2. Verificar rate limit
        if not await self._rate_limiter.wait_and_acquire(timeout=15):
            logger.warning(f"Rate limit excedido para {api_name}")
            return None

        # 3. Fazer API call
        try:
            result = await fallback_fn()
            if result:
                # Salvar no cache
                result["name"] = key
                self._cache.set(key, result)
            return result
        except Exception as e:
            logger.error(f"Erro na API call {api_name}: {e}")
            return None

    def report_429(self):
        """Reporta 429 para o rate limiter."""
        self._rate_limiter.report_429()

    def report_success(self, latency: float):
        """Reporta sucesso para o rate limiter."""
        self._rate_limiter.report_success(latency)

    def get_rate_status(self) -> Dict:
        """Retorna status do rate limiter."""
        return self._rate_limiter.get_status()

    def get_cache_stats(self) -> Dict:
        """Retorna estatísticas do cache."""
        all_data = self._cache.get_all()
        return {
            "cached_opponents": len(all_data),
            "cache_file": str(CACHE_DB)
        }

    def force_refresh(self, name: str):
        """Força refresh de um oponente."""
        self._cache.invalidate(name)
        logger.info(f"Cache invalidado para {name}")


# Instância global
opponent_cache_mgr = OpponentCacheManager(rate=100, per_seconds=120)


def create_cache_manager(rate: int = 100, per_seconds: int = 120) -> OpponentCacheManager:
    """Factory para criar cache manager configurável."""
    return OpponentCacheManager(rate, per_seconds)