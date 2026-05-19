import os, json, logging, ctypes
from pathlib import Path
from logging.handlers import RotatingFileHandler

PROJECT_DIR = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_DIR / "overlay_config.json"
LOG_DIR = PROJECT_DIR / "logs"

def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e: logging.error(f"Config save error: {e}")

def setup_logging(cfg: dict = None):
    cfg = cfg or load_config()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_cfg = cfg.get("logging", {})
    # Rotacao diaria: 5MB por arquivo, 7 backups (1 semana)
    handler = RotatingFileHandler(
        LOG_DIR / "overlay.log",
        maxBytes=log_cfg.get("max_bytes", 5*1024*1024),
        backupCount=log_cfg.get("backup_count", 7),
        encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(module)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger = logging.getLogger()
    logger.setLevel(log_cfg.get("level", "INFO").upper())
    logger.handlers.clear()
    logger.addHandler(handler)
    # Console handler para erros criticos
    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)

def enable_dpi_awareness():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def get_riot_region(cfg: dict = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("riot_region", "br1")

def get_riot_platform(cfg: dict = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("riot_platform", "americas")

def get_tft_set(cfg: dict = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("tft_set", "TFTSet17")

def get_window_pos(cfg: dict, w: int, h: int) -> tuple:
    x = cfg.get("window", {}).get("x", 100)
    y = cfg.get("window", {}).get("y", 100)
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return 100, 100
    return int(x), int(y)