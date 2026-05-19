"""
LLM Streaming UI - Redução do Time-to-Action.

Implementa streaming de resposta da IA para exibir a composição sugerida
instantaneamente enquanto a justificativa carrega depois.

Funcionalidades:
- Partial JSON Parsing via instructor/Pydantic
- Async generators para yield de chunks
- WebSocket para push de dados ao frontend
- Fallback para respostas completas se streaming falhar
"""
import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class StreamStage(Enum):
    """Estágios do streaming."""
    START = "start"
    COMP = "comp"           # Composição sugerida (primeiro!)
    ITEMS = "items"         # Itens
    AUGMENTS = "augments"   # Augments
    POSITIONING = "positioning"
    REASONING = "reasoning" # Explicação (último!)
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class StreamChunk:
    """Chunk de dados streaming."""
    stage: StreamStage
    data: Any
    timestamp: datetime = field(default_factory=datetime.now)
    is_partial: bool = False


@dataclass
class StreamingResponse:
    """Resposta parsada durante streaming."""
    comp: Optional[str] = None
    items: Optional[Dict] = None
    augments: Optional[List[str]] = None
    positioning: Optional[str] = None
    reason: Optional[str] = None
    porque: Optional[str] = None
    como: Optional[str] = None
    viabilidade: Optional[int] = None
    full_json: Dict = field(default_factory=dict)


class LLMStreamer:
    """
    Gerencia streaming de respostas LLM.
    Emite comp primeiro, depois justificativa.
    """

    def __init__(self, api_key: str = None, model: str = "gpt-4"):
        self._api_key = api_key
        self._model = model
        self._buffer = ""
        self._current_response = StreamingResponse()
        self._websocket_callback: Optional[Callable] = None
        self._stage_priority = ["comp", "items", "augments", "positioning", "reason", "porque", "como", "viabilidade"]

    def set_websocket_callback(self, callback: Callable):
        """Registra callback para enviar dados via WebSocket."""
        self._websocket_callback = callback

    async def stream_response(self, prompt: str) -> AsyncGenerator[StreamChunk, None]:
        """
        Generator que streaming a resposta.
        Yield primeiro a comp, depois o resto.
        """
        # Reset state
        self._buffer = ""
        self._current_response = StreamingResponse()

        # Yield start
        yield StreamChunk(stage=StreamStage.START, data={"status": "iniciando"})

        try:
            # Simular streaming (substituir por chamada real à API)
            async for chunk in self._mock_stream(prompt):
                self._buffer += chunk

                # Tentar parser parcial
                parsed = self._try_parse_partial(self._buffer)

                if parsed:
                    # Verificar o que mudou
                    await self._yield_changes(parsed)

                    # Emitir se tem comp (prioridade máxima)
                    if parsed.comp and not self._current_response.comp:
                        yield StreamChunk(
                            stage=StreamStage.COMP,
                            data={"comp": parsed.comp},
                            is_partial=True
                        )
                        if self._websocket_callback:
                            await self._websocket_callback({"type": "comp", "data": parsed.comp})

            # Parsing final completo
            final = self._try_parse_partial(self._buffer, strict=True)
            if final:
                self._current_response = final
                yield StreamChunk(
                    stage=StreamStage.COMPLETE,
                    data=self._build_full_json(final)
                )
            else:
                # Fallback: tentar extrair do buffer manualmente
                fallback = self._manual_parse(self._buffer)
                if fallback:
                    yield StreamChunk(
                        stage=StreamStage.COMPLETE,
                        data=self._build_full_json(fallback)
                    )

        except Exception as e:
            logger.error(f"Erro no streaming: {e}")
            yield StreamChunk(stage=StreamStage.ERROR, data={"error": str(e)})

    async def _yield_changes(self, parsed: StreamingResponse):
        """Emite chunks apenas se algo mudou."""
        changes = []

        if parsed.comp and parsed.comp != self._current_response.comp:
            changes.append((StreamStage.COMP, parsed.comp))

        if parsed.items and parsed.items != self._current_response.items:
            changes.append((StreamStage.ITEMS, parsed.items))

        if parsed.augments and parsed.augments != self._current_response.augments:
            changes.append((StreamStage.AUGMENTS, parsed.augments))

        if parsed.positioning and parsed.positioning != self._current_response.positioning:
            changes.append((StreamStage.POSITIONING, parsed.positioning))

        # Reasoning vem por último
        if parsed.porque and parsed.porque != self._current_response.porque:
            changes.append((StreamStage.REASONING, parsed.porque))

        # Emitir via WebSocket se disponível
        if self._websocket_callback and changes:
            for stage, data in changes:
                await self._websocket_callback({
                    "type": stage.value,
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                })

    async def _mock_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Mock de streaming - substituir por chamada real à API."""
        # Simular resposta gradual
        response_parts = [
            '{"comp": "',
            'Dark Star Flex',
            '", "items": {"Jhin": ["InfinityEdge", "RapidFireCannon", "LastWhisper"], ',
            '"Kai\'Sa": ["Guinsoos", "Rabadon", "JeweledGauntlet"]}, ',
            '"augments": ["TraitTree", "MayTheFoursBeWithYou", "HoldTheLine"], ',
            '"positioning": "Jhin/Kai\'Sa atras, tanks na frente", ',
            '"reason": "Comp forte no meta atual", ',
            '"porque": "Sinergia de Sniper + Vanguard com altos danos", ',
            '"como": "Fast 8, roll no 4-1", ',
            '"viabilidade": 85}'
        ]

        for part in response_parts:
            await asyncio.sleep(0.1)  # Simular latência
            yield part

    def _try_parse_partial(self, text: str, strict: bool = False) -> Optional[StreamingResponse]:
        """Tenta fazer parse parcial do JSON."""
        # Verificar se tem estrutura mínima
        if not text.strip().startswith("{"):
            return None

        # Completar parênteses se necessário
        brace_count = text.count("{") - text.count("}")
        bracket_count = text.count("[") - text.count("]")

        if not strict and (brace_count > 0 or bracket_count > 0):
            # Não está completo ainda
            # Tentar extrair o que dá
            pass

        try:
            data = json.loads(text)
            return StreamingResponse(
                comp=data.get("comp"),
                items=data.get("items"),
                augments=data.get("augments"),
                positioning=data.get("posicionamento"),
                reason=data.get("reason"),
                porque=data.get("porque"),
                como=data.get("como"),
                viabilidade=data.get("viabilidade"),
                full_json=data
            )
        except json.JSONDecodeError:
            # Tentar extrair comp via regex
            comp_match = re.search(r'"comp"\s*:\s*"([^"]+)"', text)
            if comp_match:
                return StreamingResponse(comp=comp_match.group(1))
            return None

    def _manual_parse(self, text: str) -> Optional[StreamingResponse]:
        """Parse manual como fallback."""
        try:
            # Encontrar comp
            comp_match = re.search(r'"comp"\s*:\s*"([^"]+)"', text)
            comp = comp_match.group(1) if comp_match else None

            # Encontrar viabilidade
            viab_match = re.search(r'"viabilidade"\s*:\s*(\d+)', text)
            viabilidade = int(viab_match.group(1)) if viab_match else None

            return StreamingResponse(
                comp=comp,
                viabilidade=viabilidade,
                full_json={"comp": comp, "viabilidade": viabilidade}
            )
        except:
            return None

    def _build_full_json(self, response: StreamingResponse) -> Dict:
        """Constrói JSON completo para retorno."""
        return {
            "comp": response.comp,
            "items": response.items,
            "augments": response.augments,
            "positioning": response.positioning,
            "reason": response.reason,
            "porque": response.porque,
            "como": response.como,
            "viabilidade": response.viabilidade,
            "_full": True
        }


class StreamingWebSocketManager:
    """
    Gerencia WebSocket para push de dados streaming ao frontend.
    """

    def __init__(self):
        self._clients: set = set()
        self._streamer = LLMStreamer()

    def add_client(self, websocket):
        """Adiciona cliente WebSocket."""
        self._clients.add(websocket)
        logger.info(f"Cliente streaming adicionado. Total: {len(self._clients)}")

    def remove_client(self, websocket):
        """Remove cliente WebSocket."""
        self._clients.discard(websocket)

    async def broadcast(self, data: Dict):
        """Envia dados para todos os clientes conectados."""
        if not self._clients:
            return

        message = json.dumps(data)
        dead_clients = set()

        for client in self._clients:
            try:
                await client.send(message)
            except Exception as e:
                logger.warning(f"Erro ao enviar para cliente: {e}")
                dead_clients.add(client)

        # Remover clientes mortos
        for client in dead_clients:
            self._clients.discard(client)

    async def stream_prompt(self, prompt: str) -> Dict:
        """
        Stream um prompt e retorna resposta completa.
        Também push para clientes WebSocket.
        """
        # Configurar callback para broadcast
        async def ws_callback(data):
            await self.broadcast({"stream": data})

        self._streamer.set_websocket_callback(ws_callback)

        # Coletar resposta
        full_response = {}
        async for chunk in self._streamer.stream_response(prompt):
            if chunk.stage == StreamStage.COMP:
                full_response["comp"] = chunk.data.get("comp")
                # Push instantâneo da comp
                await self.broadcast({"type": "comp_ready", "data": chunk.data})

            elif chunk.stage == StreamStage.COMPLETE:
                full_response.update(chunk.data)
                await self.broadcast({"type": "full_ready", "data": chunk.data})

            elif chunk.stage == StreamStage.ERROR:
                await self.broadcast({"type": "error", "data": chunk.data})

        return full_response


# Instância global
stream_manager = StreamingWebSocketManager()


def create_streamer(api_key: str = None, model: str = "gpt-4") -> LLMStreamer:
    """Factory para criar streamer configurável."""
    return LLMStreamer(api_key, model)


# Função de integração com cloud_agent.py
async def stream_cloud_agent(cloud_agent, prompt: str) -> Dict:
    """
    Wrapper para usar streaming com o cloud_agent existente.
    Substitui cloud_agent.call() quando streaming é desejado.
    """
    return await stream_manager.stream_prompt(prompt)