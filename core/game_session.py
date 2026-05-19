"""
GameSession dataclass — centraliza todo o estado do poll_loop.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum


class MatchState(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"


@dataclass
class GameSession:
    # Estado da partida
    match_state: MatchState = MatchState.IDLE
    analyzed_game_id: Optional[str] = None
    registered_augments: List[str] = field(default_factory=list)
    last_comp_used: str = ""
    last_suggestion: dict = field(default_factory=dict)

    # Estado de polling
    last_phase: str = "Unknown"
    last_stage: str = "Unknown"
    last_poll_time: int = 0
    last_known_rank: str = ""
    last_fallback_time: int = 0
    _reanalyze_requested: bool = False

    # Credenciais LCU
    creds: Optional[Tuple[str, str]] = None

    def start_new_game(self, game_id: str):
        """Transicao IDLE/ACTIVE -> ACTIVE: reseta estado especifico de partida."""
        self.match_state = MatchState.ACTIVE
        self.analyzed_game_id = game_id
        self.registered_augments.clear()
        self._reanalyze_requested = False

    def end_game(self, game_id: str):
        """Transicao ACTIVE/ENDING -> ENDING: flag para coleta EOG."""
        self.match_state = MatchState.ENDING

    def finish_end(self):
        """Transicao ENDING -> ENDED: reseta para aguardar lobby."""
        self.match_state = MatchState.ENDED
        self.analyzed_game_id = None

    def return_to_lobby(self):
        """Transicao ENDED -> IDLE: pronto para nova partida."""
        self.match_state = MatchState.IDLE

    def request_reanalyze(self):
        """Sinaliza reanalise (mantem augments)."""
        self._reanalyze_requested = True

    def should_analyze(self, game_id: Optional[str]) -> bool:
        """True se é partida nova ou reanalise requisitada."""
        if not game_id:
            return False
        return game_id != self.analyzed_game_id or self._reanalyze_requested

    def is_new_game(self, game_id: Optional[str]) -> bool:
        return bool(game_id) and game_id != self.analyzed_game_id

    def mark_analyzed(self, game_id: str, comp: str, result: dict):
        self.analyzed_game_id = game_id
        self.last_comp_used = comp
        self.last_suggestion = result
        self._reanalyze_requested = False

    def update_rank(self, rank_key: str):
        self.last_known_rank = rank_key

    def update_stage(self, stage: str):
        self.last_stage = stage

    def update_phase(self, phase: str):
        self.last_phase = phase
