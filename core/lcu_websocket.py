"""
LCU WebSocket - Substitui polling HTTP por WebSocket nativo.

Conecta em wss://127.0.0.1:{port}/ com auth Basic riot:<pwd>.
Escuta /lol-gameflow/v1/gameflow-phase. Só dispara análise pesada
em InProgress ou mudança de stage. Fallback automático para polling
se WS cair.

Eventos capturados:
- gameflow-phase (phase change)
- ChampSelect events
- game-start
- game-end
"""
import asyncio
import json
import logging
import base64
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import websockets
import websockets.client
import websockets.exceptions

logger = logging.getLogger(__name__)


class GameFlowPhase(Enum):
    """Fases do gameflow da LCU."""
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


@dataclass
class WSMessage:
    """Mensagem recebida via WebSocket."""
    type: str
    uri: str
    data: Any
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class LCUWebSocket:
    """
    Gerenciador de WebSocket para LCU.
    Substitui polling HTTP por conexão persistente.
    """

    def __init__(self, port: int, password: str,
                 on_phase_change: Callable[[str], None] = None,
                 on_event: Callable[[str, Any], None] = None):
        self._port = port
        self._password = password
        self._ws: Optional[websockets.client.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = 5.0
        self._max_reconnect_delay = 30.0
        self._fallback_mode = False

        # Callbacks
        self._on_phase_change = on_phase_change
        self._on_event = on_event

        # Estado
        self._current_phase = GameFlowPhase.NONE
        self._last_phase = GameFlowPhase.NONE
        self._session_active = False

        # Auth
        self._auth_header = self._generate_auth_header()

    def _generate_auth_header(self) -> str:
        """Gera header de autenticação Base64."""
        credentials = f"riot:{self._password}"
        return base64.b64encode(credentials.encode()).decode()

    async def connect(self) -> bool:
        """Estabelece conexão WebSocket."""
        try:
            import ssl

            # URI para WebSocket da LCU
            ws_uri = f"wss://127.0.0.1:{self._port}/"

            # Headers com autenticação
            headers = {
                "Authorization": f"Basic {self._auth_header}"
            }

            # SSL context - aceitar certificado local自签字
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            logger.info(f"Conectando WebSocket em {ws_uri}...")
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    ws_uri,
                    headers=headers,
                    ping_interval=None,
                    ssl=ssl_context
                ),
                timeout=5.0
            )

            logger.info("WebSocket conectado com sucesso!")
            self._fallback_mode = False
            self._reconnect_delay = 5.0
            return True

        except asyncio.TimeoutError:
            logger.warning("Timeout ao conectar WebSocket")
            self._fallback_mode = True
            return False
        except Exception as e:
            logger.warning(f"Erro ao conectar WebSocket: {e}")
            self._fallback_mode = True
            return False

    async def subscribe(self, uri: str) -> bool:
        """Assina um endpoint para receber eventos."""
        if not self._ws:
            return False

        try:
            # Formato da mensagem de subscribe
            subscribe_msg = json.dumps([
                {"uri": uri, "preventInitialization": False}
            ])

            await self._ws.send(subscribe_msg)
            logger.info(f"Subscreveu em {uri}")
            return True

        except Exception as e:
            logger.error(f"Erro ao subscrever {uri}: {e}")
            return False

    async def subscribe_all(self):
        """Assina todos os eventos relevantes."""
        # Gameflow phase - o mais importante
        await self.subscribe("/lol-gameflow/v1/gameflow-phase")

        # ChampSelect events
        await self.subscribe("/lol-champ-select/v1/session")

        # Game stats (HP, gold, stage)
        await self.subscribe("/lol-game/v1/client")

        # Augments (quando selecionados)
        await self.subscribe("/lol-gameflow/v1/summoner-selection")

        logger.info("Todas as subscriptions enviadas")

    async def listen(self):
        """Loop principal de escuta."""
        self._running = True

        while self._running:
            try:
                if not self._ws:
                    # Tentar reconectar
                    connected = await self.connect()
                    if not connected:
                        await asyncio.sleep(self._reconnect_delay)
                        continue
                    await self.subscribe_all()

                # Receber mensagem
                message = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
                await self._handle_message(message)

            except asyncio.TimeoutError:
                # Enviar ping para manter conexão viva
                try:
                    if self._ws and self._ws.open:
                        await self._ws.ping()
                except:
                    pass
                continue

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket fechado: {e.code} - {e.reason}")
                self._ws = None
                self._fallback_mode = True

                # Backoff exponencial
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                logger.info(f"Tentando reconectar em {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)

            except asyncio.CancelledError:
                break

            except Exception as e:
                logger.error(f"Erro no listen: {e}")
                await asyncio.sleep(1.0)

    async def _handle_message(self, message: str):
        """Processa mensagem recebida."""
        try:
            # Mensagens podem vir como string ou array
            data = json.loads(message)

            if isinstance(data, list):
                # Array de eventos
                for item in data:
                    await self._process_event(item)
            else:
                # Evento único
                await self._process_event(data)

        except json.JSONDecodeError:
            logger.debug(f"Mensagem não-JSON: {message[:100]}")

    async def _process_event(self, event: Dict):
        """Processa um evento individual."""
        uri = event.get("uri", "")
        data = event.get("data", {})

        # Log para debug
        logger.debug(f"WS Event: {uri}")

        # Gameflow phase change - o mais importante
        if "/gameflow-phase" in uri:
            phase = data if isinstance(data, str) else data.get("phase", "")
            if phase:
                self._last_phase = self._current_phase
                try:
                    self._current_phase = GameFlowPhase(phase)
                except ValueError:
                    self._current_phase = GameFlowPhase.UNKNOWN

                logger.info(f"Phase change: {self._last_phase.value} -> {self._current_phase.value}")

                if self._on_phase_change:
                    self._on_phase_change(self._current_phase.value)

        # ChampSelect
        elif "/champ-select" in uri:
            if self._on_event:
                await self._on_event("champ_select", data)

        # Game data (HP, gold, etc)
        elif "/game/v1/client" in uri:
            if self._on_event:
                await self._on_event("game_client", data)

    async def disconnect(self):
        """Desconecta WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("WebSocket desconectado")

    def is_connected(self) -> bool:
        """Retorna se está conectado."""
        return self._ws is not None and self._ws.open

    def is_fallback_mode(self) -> bool:
        """Retorna se está em modo fallback (polling)."""
        return self._fallback_mode

    def get_current_phase(self) -> str:
        """Retorna fase atual."""
        return self._current_phase.value


class LCUWebSocketManager:
    """
    Gerenciador central que coordena WebSocket + Fallback.
    """

    def __init__(self, port: int, password: str,
                 fallback_poll_fn: Callable = None):
        self._ws = LCUWebSocket(port, password)
        self._fallback_poll_fn = fallback_poll_fn
        self._poll_task: Optional[asyncio.Task] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False

        # Configurar callbacks
        self._ws._on_phase_change = self._handle_phase_change

    async def _handle_phase_change(self, phase: str):
        """Callback quando fase muda."""
        logger.info(f"Phase change detectado: {phase}")

        # Se voltou para Lobby/EndOfGame, cancelar poll fallback
        if phase in {"Lobby", "EndOfGame", "WaitingForStats"}:
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
                logger.info("Poll fallback cancelado")

        # Se entrou em InProgress, garantir análise
        elif phase == "InProgress":
            logger.info("Game InProgress - disparando análise")

    async def start(self):
        """Inicia o gerenciador."""
        self._running = True

        # Iniciar WebSocket em background
        self._ws_task = asyncio.create_task(self._ws.listen())

        # Se WebSocket falhar, iniciar polling fallback
        await asyncio.sleep(2)  # Esperar inicialização do WS

        if self._ws.is_fallback_mode() and self._fallback_poll_fn:
            logger.info("Iniciando modo fallback (polling)")
            self._start_fallback_poll()

    async def stop(self):
        """Para o gerenciador."""
        self._running = False
        await self._ws.disconnect()

        if self._poll_task:
            self._poll_task.cancel()

        if self._ws_task:
            self._ws_task.cancel()

    def _start_fallback_poll(self):
        """Inicia polling fallback se WebSocket falhar."""
        async def poll_loop():
            while self._running and self._ws.is_fallback_mode():
                if self._fallback_poll_fn:
                    try:
                        await self._fallback_poll_fn()
                    except Exception as e:
                        logger.error(f"Erro no poll fallback: {e}")
                await asyncio.sleep(5)

        self._poll_task = asyncio.create_task(poll_loop())


# Função factory para criar manager
def create_websocket_manager(port: int, password: str,
                              fallback_fn: Callable = None) -> LCUWebSocketManager:
    """Factory para criar WebSocket Manager."""
    return LCUWebSocketManager(port, password, fallback_fn)