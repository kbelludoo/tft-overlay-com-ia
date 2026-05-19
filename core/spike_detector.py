"""
Spike Detector - Economia Inimiga.

Detecta quando um oponente "spikou" (fez power spike):
- Subiu de nível repentinamente (ex: 7→8)
- Board atualizou com unidades de alto custo
- Ouro gasto em roll

Indicadores:
- 📈 Vermelho: Spike recente (1-2 rodadas)
- 🟡 Amarelo:-spike moderado
- 🟢 Verde: Estável
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from core.stage_heuristics import CHAMPION_COST

logger = logging.getLogger(__name__)


class SpikeType(Enum):
    """Tipo de spike detectado."""
    LEVEL_UP = "level_up"       # Subiu nível
    ROLL = "roll"              # Rolou units de custo alto
    ITEM_POWER = "item_power"  #.items fortes montados
    COMP_COMPLETE = "comp_complete"  # Comp completa
    NONE = "none"


class SpikeSeverity(Enum):
    """Severidade do spike."""
    CRITICAL = "critical"  # 🔴 Vermelho
    MODERATE = "moderate"   # 🟡 Amarelo
    LOW = "low"            # 🟢 Verde
    NONE = "none"


@dataclass
class SpikeEvent:
    """Evento de spike detectado."""
    opponent: str
    spike_type: SpikeType
    severity: SpikeSeverity
    description: str
    stage: str
    timestamp: datetime
    delta: Dict  # Dados do que mudou


@dataclass
class OpponentHistory:
    """Histórico de um oponente."""
    name: str
    levels: List[int]  # Histórico de níveis
    units: List[List[str]]  # Histórico de units por snapshot
    golds: List[int]  # Histórico de ouro
    hps: List[int]    # Histórico de HP
    last_roll_stage: Optional[str] = None
    last_level_up_stage: Optional[str] = None


class SpikeDetector:
    """
    Detecta spikes de oponentes analisando mudanças de estado.
    """

    def __init__(self, history_window: int = 5):
        self._history_window = history_window
        self._opponent_history: Dict[str, OpponentHistory] = {}
        self._spike_cache: Dict[str, SpikeEvent] = {}  # Cache de spikes ativos

    def _get_or_create_history(self, name: str) -> OpponentHistory:
        """Obtém ou cria histórico de um oponente."""
        if name not in self._opponent_history:
            self._opponent_history[name] = OpponentHistory(
                name=name,
                levels=[],
                units=[],
                golds=[],
                hps=[]
            )
        return self._opponent_history[name]

    def update_opponent(self, name: str, level: int, units: List[str],
                       gold: int, hp: int, stage: str):
        """
        Atualiza estado de um oponente e detecta spikes.
        """
        history = self._get_or_create_history(name)

        # Adicionar ao histórico
        history.levels.append(level)
        history.units.append(units)
        history.golds.append(gold)
        history.hps.append(hp)

        # Manter janela limitada
        if len(history.levels) > self._history_window:
            history.levels = history.levels[-self._history_window:]
            history.units = history.units[-self._history_window:]
            history.golds = history.golds[-self._history_window:]
            history.hps = history.hps[-self._history_window:]

        # Detectar spike se tem dados suficientes
        if len(history.levels) >= 2:
            spike = self._detect_spike(history, stage)
            if spike:
                self._spike_cache[name] = spike
                logger.info(f"Spike detectado para {name}: {spike.spike_type.value} ({spike.severity.value})")

    def _detect_spike(self, history: OpponentHistory, current_stage: str) -> Optional[SpikeEvent]:
        """Detecta tipo e severidade do spike."""
        if len(history.levels) < 2:
            return None

        prev_level = history.levels[-2]
        curr_level = history.levels[-1]
        prev_units = history.units[-2] if len(history.units) >= 2 else []
        curr_units = history.units[-1]

        # === 1. Detectar Level Spike ===
        if curr_level > prev_level:
            level_gap = curr_level - prev_level
            if level_gap >= 2:
                # Spike crítico (ex: 6→8)
                return SpikeEvent(
                    opponent=history.name,
                    spike_type=SpikeType.LEVEL_UP,
                    severity=SpikeSeverity.CRITICAL,
                    description=f"Subiu {level_gap} níveis (L{prev_level}→L{curr_level})",
                    stage=current_stage,
                    timestamp=datetime.now(),
                    delta={"prev_level": prev_level, "curr_level": curr_level}
                )
            elif level_gap == 1:
                # Verificar se level up recente (stage mudança)
                if not history.last_level_up_stage or history.last_level_up_stage < current_stage:
                    return SpikeEvent(
                        opponent=history.name,
                        spike_type=SpikeType.LEVEL_UP,
                        severity=SpikeSeverity.MODERATE,
                        description=f"Subiu nível (L{prev_level}→L{curr_level})",
                        stage=current_stage,
                        timestamp=datetime.now(),
                        delta={"prev_level": prev_level, "curr_level": curr_level}
                    )

        # === 2. Detectar Roll Spike (unidades de alto custo) ===
        if len(curr_units) > len(prev_units):
            # Units adicionadas
            new_units = [u for u in curr_units if u not in prev_units]
            high_cost_new = [u for u in new_units if CHAMPION_COST.get(u, 1) >= 4]

            if high_cost_new:
                total_cost = sum(CHAMPION_COST.get(u, 1) for u in high_cost_new)
                if total_cost >= 8:  # 2+ units de custo 4+
                    return SpikeEvent(
                        opponent=history.name,
                        spike_type=SpikeType.ROLL,
                        severity=SpikeSeverity.CRITICAL,
                        description=f"Rolou: {', '.join(high_cost_new)}",
                        stage=current_stage,
                        timestamp=datetime.now(),
                        delta={"new_units": high_cost_new, "total_cost": total_cost}
                    )
                elif total_cost >= 4:
                    return SpikeEvent(
                        opponent=history.name,
                        spike_type=SpikeType.ROLL,
                        severity=SpikeSeverity.MODERATE,
                        description=f"Rolou: {', '.join(high_cost_new)}",
                        stage=current_stage,
                        timestamp=datetime.now(),
                        delta={"new_units": high_cost_new, "total_cost": total_cost}
                    )

        # === 3. Detectar Comp Completa ===
        if len(curr_units) >= 6:
            # Verificar se comp parece completa (múltiplos 2-stars)
            # Simplificado: se tem 6+ units, considerar completa
            # (em produção, usar tier das units)
            return SpikeEvent(
                opponent=history.name,
                spike_type=SpikeType.COMP_COMPLETE,
                severity=SpikeSeverity.MODERATE,
                description=f"Comp completa ({len(curr_units)} units)",
                stage=current_stage,
                timestamp=datetime.now(),
                delta={"unit_count": len(curr_units)}
            )

        return None

    def get_spike(self, opponent_name: str) -> Optional[SpikeEvent]:
        """Retorna spike ativo de um oponente."""
        return self._spike_cache.get(opponent_name)

    def get_all_spikes(self) -> Dict[str, SpikeEvent]:
        """Retorna todos os spikes ativos."""
        return self._spike_cache.copy()

    def get_critical_spikes(self) -> List[SpikeEvent]:
        """Retorna apenas spikes críticos."""
        return [s for s in self._spike_cache.values() if s.severity == SpikeSeverity.CRITICAL]

    def clear_spikes(self):
        """Limpa spikes (chamar no início de nova partida)."""
        self._spike_cache.clear()
        self._opponent_history.clear()
        logger.info("Spikes resetados")

    def cleanup_old_spikes(self, max_age_minutes: int = 5):
        """Remove spikes velhos."""
        now = datetime.now()
        to_remove = []

        for name, spike in self._spike_cache.items():
            age = (now - spike.timestamp).total_seconds() / 60
            if age > max_age_minutes:
                to_remove.append(name)

        for name in to_remove:
            del self._spike_cache[name]

        if to_remove:
            logger.info(f"Cleaned {len(to_remove)} old spikes")


def format_spike_display(spike: SpikeEvent) -> Dict:
    """Formata spike para display na HUD."""
    icons = {
        SpikeSeverity.CRITICAL: "🔴",
        SpikeSeverity.MODERATE: "🟡",
        SpikeSeverity.LOW: "🟢",
        SpikeSeverity.NONE: "⚪"
    }

    return {
        "icon": icons.get(spike.severity, "⚪"),
        "type": spike.spike_type.value,
        "severity": spike.severity.value,
        "description": spike.description,
        "stage": spike.stage
    }


def get_opponent_spike_status(opponents: List[Dict], detector: SpikeDetector) -> List[Dict]:
    """
    Retorna status de spike para cada oponente.
    Integração com opponent_tracker.
    """
    result = []

    for opp in opponents:
        name = opp.get("name", "")
        if not name:
            continue

        # Atualizar detector
        level = opp.get("level", 1)
        units = opp.get("board", [])
        hp = opp.get("health", 100)
        stage = opp.get("stage", "1-1")

        detector.update_opponent(name, level, units, 0, hp, stage)

        # Obter spike
        spike = detector.get_spike(name)
        if spike:
            result.append({
                "name": name,
                "spike": format_spike_display(spike)
            })
        else:
            result.append({
                "name": name,
                "spike": None
            })

    return result


# Instância global
spike_detector = SpikeDetector()


def create_spike_detector() -> SpikeDetector:
    """Factory para criar detector."""
    return SpikeDetector()