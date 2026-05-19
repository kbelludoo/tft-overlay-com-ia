"""
Debouncer de Estado + Pipeline Assíncrono.

Calcula hash do estado (stage+gold+board+augments). Se hash não mudar,
cancela task pendente e ignora chamada. Separa LCU → API → IA → HUD em
filas assíncronas.

Classes:
- StateHashDebouncer: calcula hash e gerencia tasks pendentes
- AsyncPipeline: pipeline de estágios (LCU → API → IA → HUD)
"""
import asyncio
import hashlib
import logging
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    LCU_POLL = "lcu_poll"
    API_EXTRACT = "api_extract"
    AI_ANALYSIS = "ai_analysis"
    HUD_UPDATE = "hud_update"


@dataclass
class PipelineTask:
    task_id: str
    stage: PipelineStage
    created_at: datetime = field(default_factory=datetime.now)
    state_hash: str = ""
    cancelled: bool = False
    result: Any = None
    error: Optional[str] = None


class StateHashDebouncer:
    """
    Debouncer baseado em hash MD5 do estado do jogo.
    Evita chamadas redundantes quando o estado não mudou.
    """

    def __init__(self, cooldown_seconds: float = 2.0):
        self._last_hash: str = ""
        self._last_update: float = 0
        self._cooldown = cooldown_seconds
        self._pending_tasks: Dict[str, asyncio.Task] = {}
        self._task_counter: int = 0

    def _normalize_value(self, value: Any) -> str:
        """Normaliza valor para hash consistente (força int/float)."""
        if value is None:
            return ""
        if isinstance(value, (int, float, bool)):
            return str(int(value))
        if isinstance(value, str):
            try:
                return str(int(float(value)))
            except (ValueError, TypeError):
                return value.strip().lower()
        if isinstance(value, list):
            return ",".join(sorted(str(v).strip().lower() for v in value if v))
        if isinstance(value, dict):
            items = []
            for k in sorted(value.keys()):
                v = value[k]
                items.append(f"{k}:{self._normalize_value(v)}")
            return "|".join(items)
        return str(value).strip().lower()

    def compute_hash(self, stage: str, gold: Any, level: Any,
                     board: list, shop: list, augments: list,
                     opponents: list, hp: Any = 100) -> str:
        """Calcula hash MD5 do estado atual do jogo com normalização."""
        stage_norm = self._normalize_value(stage)
        gold_norm = self._normalize_value(gold)
        level_norm = self._normalize_value(level)
        board_norm = self._normalize_value(board)
        shop_norm = self._normalize_value(shop)
        augments_norm = self._normalize_value(augments)
        opponents_norm = self._normalize_value(opponents)
        hp_norm = self._normalize_value(hp)

        state_str = f"{stage_norm}|{gold_norm}|{level_norm}|" + \
                    f"{board_norm}|" + \
                    f"{shop_norm}|" + \
                    f"{augments_norm}|" + \
                    f"{opponents_norm}|" + \
                    f"{hp_norm}"
        return hashlib.md5(state_str.encode()).hexdigest()

    def should_process(self, stage: str, gold: Any, level: Any,
                       board: list, shop: list, augments: list,
                       opponents: list, hp: Any = 100) -> bool:
        """
        Retorna True se o estado mudou (deve processar).
        Retorna False se estado igual (ignorar).
        """
        import time
        current_time = time.time()

        current_hash = self.compute_hash(stage, gold, level, board, shop, augments, opponents, hp=hp)

        # Primeiro chamada - sempre processa
        if not self._last_hash:
            self._last_hash = current_hash
            self._last_update = current_time
            return True

        # Hash igual - verificar cooldown
        if current_hash == self._last_hash:
            if current_time - self._last_update < self._cooldown:
                logger.debug(f"Hash inalterado ({current_hash[:8]}...), cooldown ativo. Ignorando.")
                return False
            # Cooldown expirou - reprocessar para atualizar UI
            self._last_update = current_time
            return True

        # Hash mudou - processar
        self._last_hash = current_hash
        self._last_update = current_time
        logger.info(f"Novo estado detectado. Hash: {current_hash[:8]}...")
        return True

    def get_task_id(self) -> str:
        """Gera ID único para task."""
        self._task_counter += 1
        return f"task_{self._task_counter}_{datetime.now().strftime('%H%M%S')}"

    async def cancel_pending_task(self, task_id: str) -> bool:
        """Cancela task pendente se existir."""
        if task_id in self._pending_tasks:
            task = self._pending_tasks[task_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"Task {task_id} cancelada com sucesso")
                del self._pending_tasks[task_id]
                return True
        return False

    def register_task(self, task_id: str, task: asyncio.Task):
        """Registra task no tracker."""
        self._pending_tasks[task_id] = task

    def cleanup_finished_tasks(self):
        """Remove tasks concluídas do tracker."""
        finished = [tid for tid, t in self._pending_tasks.items() if t.done()]
        for tid in finished:
            del self._pending_tasks[tid]


class AsyncPipeline:
    """
    Pipeline assíncrono que separa estágios em filas.
    LCU → API → IA → HUD
    """

    def __init__(self, max_concurrent: int = 2):
        self._queues: Dict[PipelineStage, asyncio.Queue] = {}
        self._stage_handlers: Dict[PipelineStage, Callable] = {}
        self._running = False
        self._workers: list = []
        self._max_concurrent = max_concurrent

        # Criar filas para cada estágio
        for stage in PipelineStage:
            self._queues[stage] = asyncio.Queue(maxsize=10)

    def register_handler(self, stage: PipelineStage, handler: Callable):
        """Registra handler para um estágio."""
        self._stage_handlers[stage] = handler
        logger.info(f"Handler registrado para {stage.value}")

    async def _worker(self, stage: PipelineStage):
        """Worker que processa items de uma fila."""
        logger.info(f"Worker started para {stage.value}")

        while self._running:
            try:
                #Timeout para permitir shutdown limpo
                item = await asyncio.wait_for(
                    self._queues[stage].get(),
                    timeout=5.0
                )

                handler = self._stage_handlers.get(stage)
                if handler:
                    try:
                        result = await handler(item)
                        # Passa para próximo estágio se houver
                        if stage != PipelineStage.HUD_UPDATE and result is not None:
                            next_stage = PipelineStage(stage.value + 1)
                            if next_stage in self._queues:
                                await self._queues[next_stage].put(result)
                    except Exception as e:
                        logger.error(f"Erro no handler {stage.value}: {e}")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {stage.value} erro: {e}")

    async def start(self):
        """Inicia o pipeline."""
        if self._running:
            return

        self._running = True

        # Iniciar workers para cada estágio
        for stage in PipelineStage:
            if stage in self._stage_handlers:
                worker = asyncio.create_task(self._worker(stage))
                self._workers.append(worker)

        logger.info(f"Pipeline iniciado com {len(self._workers)} workers")

    async def stop(self):
        """Para o pipeline."""
        self._running = False

        # Cancelar workers
        for worker in self._workers:
            worker.cancel()

        # Esperar cancelamento
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Pipeline parado")

    async def submit(self, stage: PipelineStage, item: Any):
        """Submete item para um estágio."""
        await self._queues[stage].put(item)

    def get_queue_size(self, stage: PipelineStage) -> int:
        """Retorna tamanho da fila de um estágio."""
        return self._queues[stage].qsize()


class ThrottledCaller:
    """
    Limita chamadas para evitar sobrecarga.
    Implementa token bucket com cooldown mínimo.
    """

    def __init__(self, min_interval: float = 1.0, max_burst: int = 3):
        self._min_interval = min_interval
        self._max_burst = max_burst
        self._tokens = max_burst
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Tenta adquirir permissão para chamada."""
        import time
        async with self._lock:
            now = time.time()

            # Recarregar tokens baseado no tempo
            elapsed = now - self._last_call
            self._tokens = min(self._max_burst, self._tokens + elapsed / self._min_interval)

            if self._tokens >= 1:
                self._tokens -= 1
                self._last_call = now
                return True

            return False

    async def wait_and_acquire(self, timeout: float = 10.0) -> bool:
        """Espera até adquirir permissão ou timeout."""
        start = import_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            if await self.acquire():
                return True
            await asyncio.sleep(0.1)
        return False


# Instância global do debouncer
state_debouncer = StateHashDebouncer(cooldown_seconds=2.0)


# Função auxiliar para integrar no main.py
def create_state_debouncer(cooldown: float = 2.0) -> StateHashDebouncer:
    """Factory para criar debouncer configurável."""
    return StateHashDebouncer(cooldown_seconds=cooldown)