"""
Circuit Breaker for Riot API calls.

States:
- CLOSED: normal operation, requests pass through
- OPEN: requests are rejected immediately (after N consecutive failures)
- HALF_OPEN: test request allowed, success -> CLOSED, failure -> OPEN
"""
import time
import logging
from enum import Enum
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 1,
    ):
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_retries = half_open_max_retries

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_attempts = 0
        self._total_failures = 0
        self._total_successes = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self._recovery_timeout:
                logger.info(f"CircuitBreaker[{self.name}]: OPEN -> HALF_OPEN (timeout expired)")
                self._state = CircuitState.HALF_OPEN
                self._half_open_attempts = 0
        return self._state

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(f"CircuitBreaker[{self.name}] is OPEN, request rejected")

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    async def async_call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(f"CircuitBreaker[{self.name}] is OPEN, request rejected")

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    def _on_success(self):
        self._total_successes += 1
        if self._state == CircuitState.HALF_OPEN:
            logger.info(f"CircuitBreaker[{self.name}]: HALF_OPEN -> CLOSED (test request succeeded)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_attempts = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)

    def record_success(self):
        """Registra sucesso externo (apenas contador, sem transicao de estado)."""
        self._total_successes += 1

    def record_failure(self, exc: Exception = None):
        """Registra falha externa (apenas contador, sem transicao de estado)."""
        self._total_failures += 1

    def _on_failure(self, exc: Exception):
        self._total_failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_attempts += 1
            if self._half_open_attempts >= self._half_open_max_retries:
                logger.warning(f"CircuitBreaker[{self.name}]: HALF_OPEN -> OPEN ({exc})")
                self._state = CircuitState.OPEN
            return

        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            logger.warning(
                f"CircuitBreaker[{self.name}]: CLOSED -> OPEN "
                f"({self._failure_count} consecutive failures, last: {exc})"
            )
            self._state = CircuitState.OPEN

    def force_open(self):
        self._state = CircuitState.OPEN
        self._last_failure_time = time.time()
        logger.warning(f"CircuitBreaker[{self.name}]: force OPEN")

    def force_closed(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_attempts = 0
        logger.info(f"CircuitBreaker[{self.name}]: force CLOSED")

    def reset(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_attempts = 0
        self._last_failure_time = 0.0
        logger.info(f"CircuitBreaker[{self.name}]: reset")

    @property
    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "is_available": self.is_available,
        }


class CircuitBreakerOpenError(Exception):
    pass


# Instancias globais
riot_api_breaker = CircuitBreaker(name="riot_api", failure_threshold=5, recovery_timeout=30.0)
lcu_breaker = CircuitBreaker(name="lcu_api", failure_threshold=3, recovery_timeout=10.0)
ai_api_breaker = CircuitBreaker(name="ai_api", failure_threshold=3, recovery_timeout=20.0)


def create_breaker(name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> CircuitBreaker:
    return CircuitBreaker(name=name, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout)
