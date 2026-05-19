"""
Tracker de Ghost Matchups - Piscina de Oponentes.

Implementa matriz local de pareamento:
- Registra IDs enfrentados a cada turno
- Exclui oponentes recentes (últimas 4-5 rodadas)
- Reduz para 2-3 possíveis oponentes no early/mid game
- Exibe "Ameaças Possíveis" na HUD

Regras de pareamento TFT:
- Não enfrenta oponentes jogados nas últimas 4-5 rodadas
- Quanto menos jogadores, menor o histórico de exclusão
"""
import asyncio
import logging
import json
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent.parent
MATCHUP_FILE = PROJECT_DIR / "data" / "matchup_history.json"

# Número de rodadas no histórico de exclusão
MAX_HISTORY_ROUNDS = 5

# Lock para operações de arquivo
_file_lock = asyncio.Lock()


@dataclass
class OpponentSnapshot:
    """Snapshot de um oponente em um momento."""
    name: str
    summoner_id: str
    level: int
    units: List[str]
    hp: int
    stage: str
    timestamp: datetime


@dataclass
class MatchupResult:
    """Resultado de um pareamento."""
    opponent: str
    stage: str
    won: bool
    damage_taken: int


class GhostMatchupTracker:
    """
    Tracker de matchups "fantasma" (possíveis próximos oponentes).
    Mantém matriz de oponentes enfrentados e calcula possibilidades.
    """

    def __init__(self):
        # Histórico de enfrentados por estágio
        self._faced_history: deque = deque(maxlen=20)  # (stage, opponent_name)
        
        # Snapshots de oponentes (para detecção de spike)
        self._opponent_snapshots: Dict[str, List[OpponentSnapshot]] = {}
        
        # Carregar histórico persistido
        self._load_history()
        
        # Stage atual
        self._current_stage = "1-1"
        self._alive_players: List[str] = []

    def _load_history(self):
        """Carrega histórico de matchups."""
        if MATCHUP_FILE.exists():
            try:
                with open(MATCHUP_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    history = data.get("faced_history", [])
                    self._faced_history = deque(
                        [(h["stage"], h["opponent"]) for h in history],
                        maxlen=20
                    )
                logger.info(f"Histórico carregado: {len(self._faced_history)} entries")
            except Exception as e:
                logger.warning(f"Erro ao carregar histórico: {e}")

    async def _save_history_async(self):
        """Salva histórico de matchups (async com lock)."""
        async with _file_lock:
            try:
                MATCHUP_FILE.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "faced_history": [
                        {"stage": stage, "opponent": opp}
                        for stage, opp in self._faced_history
                    ],
                    "last_updated": datetime.now().isoformat()
                }
                with open(MATCHUP_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.warning(f"Erro ao salvar histórico: {e}")

    def _save_history(self):
        """Salva histórico de matchups (seguro para sync/async)."""
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._save_history_async())
        except RuntimeError:
            logger.warning("Falha ao adquirir _file_lock para save_history")

    def register_fought(self, opponent_name: str, stage: str):
        """Registra que enfrentou um oponente."""
        self._faced_history.append((stage, opponent_name))
        logger.info(f"Registrado: enfrentou {opponent_name} no stage {stage}")
        self._save_history()

    def register_opponent_state(self, name: str, summoner_id: str,
                                level: int, units: List[str],
                                hp: int, stage: str):
        """Registra estado atual de um oponente (para spike detection)."""
        if name not in self._opponent_snapshots:
            self._opponent_snapshots[name] = []

        snapshot = OpponentSnapshot(
            name=name,
            summoner_id=summoner_id,
            level=level,
            units=units,
            hp=hp,
            stage=stage,
            timestamp=datetime.now()
        )

        self._opponent_snapshots[name].append(snapshot)

        # Manter apenas últimos 10 snapshots
        if len(self._opponent_snapshots[name]) > 10:
            self._opponent_snapshots[name] = self._opponent_snapshots[name][-10:]

    def get_ghost_pool(self, all_opponents: List[Dict],
                       current_stage: str) -> List[Dict]:
        """
        Calcula pool de possíveis próximos oponentes.

        Args:
            all_opponents: Lista de todos os oponentes vivos
            current_stage: Stage atual

        Returns:
            Lista de oponentes possíveis com probability
        """
        # 1. Coletar oponentes enfrentados nas últimas rodadas
        recent_faced = set()
        for stage, name in list(self._faced_history)[-MAX_HISTORY_ROUNDS:]:
            # Verificar se ainda é relevante (mesma fase do jogo)
            recent_faced.add(name)

        # 2. Excluir enfrentados recentemente
        possible_opponents = []
        excluded = []

        for opp in all_opponents:
            name = opp.get("name", "")
            
            if name in recent_faced:
                excluded.append(name)
                continue

            # Verificar se está vivo (HP > 0)
            hp = opp.get("health", 100)
            if hp <= 0:
                continue

            possible_opponents.append({
                "name": name,
                "rank": opp.get("rank", ""),
                "hp": hp,
                "avg_placement": opp.get("avg", ""),
                "level": opp.get("level", 0),
                "probability": self._calculate_probability(opp, current_stage)
            })

        # 3. Ordenar por probabilidade
        possible_opponents.sort(key=lambda x: x["probability"], reverse=True)

        logger.info(f"Ghost pool: {len(possible_opponents)} possíveis, {len(excluded)} excluídos")

        return possible_opponents

    def _calculate_probability(self, opponent: Dict, stage: str) -> float:
        """Calcula probabilidade de ser o próximo oponente."""
        # Fatores:
        # 1. HP baixo = mais provável de estar "disposto" a enfrentar (rule do game)
        # 2. Posição no board (simulado)
        # 3. Stage atual

        hp = opponent.get("health", 100)
        
        # HP factor: quanto menor, mais próximo de morrer = mais provável enfrentar
        hp_factor = (100 - hp) / 100 * 0.4  # 40% de peso

        # Avg placement factor
        avg = opponent.get("avg", "")
        try:
            avg_placement = float(avg)
            # Quem placement pior (maior número) tende a enfrentar mais
            avg_factor = (avg_placement - 1) / 7 * 0.3  # 30% de peso
        except:
            avg_factor = 0.15

        # Stage factor: early game mais imprevisível
        stage_num = int(stage.split("-")[0]) if stage else 3
        if stage_num <= 2:
            stage_factor = 0.3
        elif stage_num <= 4:
            stage_factor = 0.2
        else:
            stage_factor = 0.1

        probability = hp_factor + avg_factor + stage_factor
        return min(1.0, probability)

    def get_snapshot_history(self, opponent_name: str) -> List[OpponentSnapshot]:
        """Retorna histórico de snapshots de um oponente."""
        return self._opponent_snapshots.get(opponent_name, [])

    def get_last_faced(self, count: int = 5) -> List[Tuple[str, str]]:
        """Retorna últimos oponentes enfrentados."""
        return list(self._faced_history)[-count:]

    def clear_history(self):
        """Limpa histórico (chamar no início de nova partida)."""
        self._faced_history.clear()
        self._opponent_snapshots.clear()
        self._save_history()
        logger.info("Histórico de matchups limpo")

    def update_alive_players(self, players: List[str]):
        """Atualiza lista de jogadores vivos."""
        self._alive_players = players


def format_ghost_display(ghost_pool: List[Dict], max_display: int = 3) -> List[Dict]:
    """Formata pool de fantasmas para display na HUD."""
    display = []
    for opp in ghost_pool[:max_display]:
        # Calcular confiança
        if opp["probability"] > 0.5:
            confidence = "ALTA"
            icon = "🔴"
        elif opp["probability"] > 0.3:
            confidence = "MEDIA"
            icon = "🟡"
        else:
            confidence = "BAIXA"
            icon = "🟢"

        display.append({
            "icon": icon,
            "name": opp["name"],
            "rank": opp.get("rank", ""),
            "hp": opp.get("hp", 0),
            "probability": f"{opp['probability']*100:.0f}%",
            "confidence": confidence
        })

    return display


# Instância global
ghost_tracker = GhostMatchupTracker()


def create_ghost_tracker() -> GhostMatchupTracker:
    """Factory para criar tracker."""
    return GhostMatchupTracker()


# Função de integração
def get_ghost_opponents(opponents: List[Dict], stage: str) -> List[Dict]:
    """Função de conveniência para obter pool de fantasmas."""
    return ghost_tracker.get_ghost_pool(opponents, stage)