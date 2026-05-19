"""Gerenciador de ciclo de vida da Riot API Key.
Rastreia criacao, expiracao, sucesso/erro de chamadas."""
import json, logging, time
from pathlib import Path
from datetime import datetime, timedelta

STATE_FILE = Path(__file__).parent.parent / "data" / "riot_key_state.json"


class RiotKeyManager:
    def __init__(self):
        self.key = ""
        self._created_at = None
        self._expires_at = None
        self._consecutive_errors = 0
        self._total_calls = 0
        self._total_errors = 0
        self._last_success = None
        self._last_error = None
        self._load_state()

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._created_at = data.get("created_at")
                self._expires_at = data.get("expires_at")
                if data.get("status") == "active" and self._expires_at:
                    exp = datetime.fromisoformat(self._expires_at)
                    if exp < datetime.now():
                        self._created_at = None
                        self._expires_at = None
        except Exception as e:
            logging.warning(f"Erro ao carregar riot key state: {e}")

    def _save_state(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            status = "active" if not self.is_expired() else "expired"
            data = {
                "created_at": self._created_at,
                "expires_at": self._expires_at,
                "status": status,
                "key_prefix": self.key[:8] + "..." if len(self.key) > 8 else ""
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logging.warning(f"Erro ao salvar riot key state: {e}")

    def register_key_creation(self, expires_in_hours: int = 24):
        now = datetime.now()
        self._created_at = now.isoformat()
        self._expires_at = (now + timedelta(hours=expires_in_hours)).isoformat()
        self._consecutive_errors = 0
        self._save_state()
        logging.info(f"Riot key registrada. Expira em {expires_in_hours}h")

    def is_expired(self) -> bool:
        if not self._expires_at:
            return True
        try:
            return datetime.fromisoformat(self._expires_at) < datetime.now()
        except (ValueError, TypeError):
            return True

    @property
    def status_text(self) -> str:
        if not self.key:
            return "Sem chave"
        if self.is_expired():
            return "Chave expirada"
        return "Chave ativa"

    @property
    def status_icon(self) -> str:
        if not self.key:
            return "⚠"
        if self.is_expired():
            return "🔴"
        if self._consecutive_errors >= 3:
            return "🟡"
        return "🟢"

    @property
    def countdown_text(self) -> str:
        if not self._expires_at:
            return ""
        try:
            exp = datetime.fromisoformat(self._expires_at)
            remaining = exp - datetime.now()
            if remaining.total_seconds() <= 0:
                return "Expirada"
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            if hours > 0:
                return f"Expira em {hours}h{mins}m"
            return f"Expira em {mins}m"
        except (ValueError, TypeError):
            return ""

    def record_success(self):
        self._consecutive_errors = 0
        self._total_calls += 1
        self._last_success = datetime.now().isoformat()

    def record_error(self, status_code: int = 0):
        self._consecutive_errors += 1
        self._total_errors += 1
        self._total_calls += 1
        self._last_error = datetime.now().isoformat()
        logging.warning(f"Riot API error {status_code} (consecutive: {self._consecutive_errors})")


riot_key_mgr = RiotKeyManager()
