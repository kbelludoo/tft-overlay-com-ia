"""
Utilitarios de logging para erros criticos e avisos.
Fornece funcoes com stack trace completo + contexto do modulo.
"""
import logging

logger = logging.getLogger(__name__)


def log_critical_error(module: str, error: Exception, extra_info: str = ""):
    """Loga erro critico com stack trace completo. Use em erros que afetam a jogabilidade."""
    msg = f"ERRO CRITICO no modulo [{module}]"
    if extra_info:
        msg += f" | {extra_info}"
    logger.exception(f"{msg}: {error}")


def log_warning_error(module: str, error: Exception, extra_info: str = ""):
    """Loga avisos de erro (menos graves, sem stack trace completo)."""
    msg = f"AVISO no modulo [{module}]"
    if extra_info:
        msg += f" | {extra_info}"
    logger.warning(f"{msg}: {error}")
