"""Gestor de chave Riot API: detecta expiração, avisa na UI, fallback automatico para cache"""
import os, time, logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
KEY_STATE_FILE = DATA_DIR / "riot_key_state.json"

class RiotKeyManager:
    """Gerencia ciclo de vida da chave Riot API"""
    
    def __init__(self):
        self.key = os.getenv("RIOT_API_KEY", "")
        self._created_at = None
        self._expires_at = None
        self._last_status = "unknown"
        self._consecutive_errors = 0
        self._fallback_active = False
        self._load_state()
    
    def _load_state(self):
        """Carrega estado anterior da chave"""
        if KEY_STATE_FILE.exists():
            try:
                import json
                with open(KEY_STATE_FILE, "r") as f:
                    state = json.load(f)
                self._created_at = datetime.fromisoformat(state.get("created_at", ""))
                self._expires_at = datetime.fromisoformat(state.get("expires_at", ""))
                self._last_status = state.get("status", "unknown")
                logging.info(f"Estado da chave Riot carregado: {self._last_status}")
            except Exception as e:
                logging.warning(f"Erro ao carregar estado da chave: {e}")
    
    def _save_state(self):
        """Salva estado atual da chave"""
        import json
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "created_at": self._created_at.isoformat() if self._created_at else "",
            "expires_at": self._expires_at.isoformat() if self._expires_at else "",
            "status": self._last_status
        }
        try:
            with open(KEY_STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logging.warning(f"Erro ao salvar estado da chave: {e}")
    
    def register_key_creation(self, expires_in_hours: int = 24):
        """Registra quando a chave foi criada e quando expira"""
        self._created_at = datetime.now()
        self._expires_at = self._created_at + timedelta(hours=expires_in_hours)
        self._last_status = "active"
        self._save_state()
        logging.info(f"Chave Riot registrada. Expira em {expires_in_hours}h")
    
    def get_time_remaining(self) -> Optional[timedelta]:
        """Retorna tempo restante ate expiracao"""
        if not self._expires_at:
            return None
        remaining = self._expires_at - datetime.now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)
    
    def get_hours_remaining(self) -> Optional[float]:
        """Retorna horas restantes"""
        remaining = self.get_time_remaining()
        if remaining is None:
            return None
        return remaining.total_seconds() / 3600
    
    def is_expired(self) -> bool:
        """Verifica se a chave expirou"""
        remaining = self.get_time_remaining()
        if remaining is None:
            return False  # Sem info, assume valida
        return remaining.total_seconds() <= 0
    
    def is_expiring_soon(self, threshold_hours: float = 2.0) -> bool:
        """Verifica se a chave expira em breve (default: 2h)"""
        hours = self.get_hours_remaining()
        if hours is None:
            return False
        return 0 < hours < threshold_hours
    
    def record_success(self):
        """Registra chamada bem-sucedida"""
        self._consecutive_errors = 0
        self._last_status = "active"
        self._fallback_active = False
    
    def record_error(self, status_code: int = 0) -> bool:
        """Registra erro. Retorna True se deve ativar fallback"""
        self._consecutive_errors += 1
        
        # 401/403 = chave invalida/expirada
        if status_code in (401, 403):
            self._last_status = "expired"
            self._fallback_active = True
            self._save_state()
            logging.error(f"Chave Riot expirada ou invalida (HTTP {status_code}). Ativando fallback.")
            return True
        
        # 429 = rate limit
        if status_code == 429:
            logging.warning(f"Rate limit Riot API. Tentativa {self._consecutive_errors}")
            return False
        
        # Outros erros: ativa fallback apos 3 consecutivos
        if self._consecutive_errors >= 3:
            self._last_status = "error"
            self._fallback_active = True
            self._save_state()
            logging.error(f"3 erros consecutivos na Riot API. Ativando fallback.")
            return True
        
        return False
    
    @property
    def fallback_active(self) -> bool:
        return self._fallback_active
    
    @property
    def status_text(self) -> str:
        """Texto de status para UI"""
        if not self.key:
            return "Chave Riot nao configurada"
        
        if self._fallback_active:
            return "Chave expirada - usando cache local"
        
        hours = self.get_hours_remaining()
        if hours is None:
            return "Chave Riot ativa"
        
        if hours <= 0:
            return "Chave Riot expirada"
        
        if hours < 1:
            mins = int(hours * 60)
            return f"Chave expira em {mins}min"
        
        return f"Chave expira em {hours:.1f}h"
    
    @property
    def countdown_text(self) -> str:
        """Retorna countdown HH:MM:SS para exibicao precisa"""
        if not self.key:
            return "--:--:--"
        
        if self._fallback_active:
            return "EXPIRADA"
        
        remaining = self.get_time_remaining()
        if remaining is None:
            return "24:00:00"
        
        total_seconds = int(remaining.total_seconds())
        if total_seconds <= 0:
            return "EXPIRADA"
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    @property
    def status_icon(self) -> str:
        """Icone de status para UI"""
        if not self.key:
            return "⚪"
        if self._fallback_active:
            return "🔴"
        
        hours = self.get_hours_remaining()
        if hours is None:
            return "🟢"
        if hours <= 0:
            return "🔴"
        if hours < 2:
            return "🟡"
        return "🟢"


# Instancia global
riot_key_mgr = RiotKeyManager()
