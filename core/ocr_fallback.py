"""
Fallback OCR - Tesseract + OpenCV.

Ativa quando LCU retorna dados stale ou falha:
- ROIs fixas para stage, gold, augments
- cv2.threshold + pytesseract
- asyncio.to_thread() com cooldown 12s
- Toggle em overlay_config.json
"""
import asyncio
import logging
import os
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Base resolution for ROI calculation (1920x1080)
BASE_WIDTH = 1920
BASE_HEIGHT = 1080

# ROI Config como percentual (0.0 - 1.0) da tela
ROI_CONFIG_PERCENT = {
    "stage": {"x_pct": 0.026, "y_pct": 0.028, "w_pct": 0.042, "h_pct": 0.028},
    "gold": {"x_pct": 0.094, "y_pct": 0.028, "w_pct": 0.031, "h_pct": 0.028},
    "level": {"x_pct": 0.063, "y_pct": 0.028, "w_pct": 0.021, "h_pct": 0.028},
    "hp": {"x_pct": 0.010, "y_pct": 0.093, "w_pct": 0.078, "h_pct": 0.019},
    "augments": {"x_pct": 0.208, "y_pct": 0.019, "w_pct": 0.156, "h_pct": 0.046},
    "shop": {"x_pct": 0.260, "y_pct": 0.463, "w_pct": 0.208, "h_pct": 0.093},
}

# Função para calcular ROIs baseadas na resolução atual
def calculate_rois(screen_width: int, screen_height: int) -> Dict:
    """Calcula ROIs absolutas baseadas na resolução da tela."""
    rois = {}
    for field, config in ROI_CONFIG_PERCENT.items():
        rois[field] = {
            "x": int(config["x_pct"] * screen_width),
            "y": int(config["y_pct"] * screen_height),
            "w": int(config["w_pct"] * screen_width),
            "h": int(config["h_pct"] * screen_height),
        }
    return rois

# ROI_CONFIG será calculado dinamicamente
ROI_CONFIG = None


class OCRState(Enum):
    """Estado do OCR."""
    IDLE = "idle"
    ACTIVE = "active"
    FAILED = "failed"


@dataclass
class OCRResult:
    """Resultado do OCR."""
    stage: Optional[str] = None
    gold: Optional[int] = None
    level: Optional[int] = None
    hp: Optional[int] = None
    augments: List[str] = None
    confidence: float = 0.0
    timestamp: str = ""


class OCRFallback:
    """
    Fallback OCR usando Tesseract + OpenCV.
    Ativa apenas quando LCU falha.
    """

    def __init__(self, config_path: str = None, cooldown: float = 12.0):
        self._cooldown = cooldown
        self._last_run = 0.0
        self._enabled = True
        self._state = OCRState.IDLE
        self._tesseract_available = False
        self._screen_width = None
        self._screen_height = None
        self._rois = None

        # Tentar importar bibliotecas
        self._check_dependencies()

        # Detectar resolução e calcular ROIs
        self._detect_resolution()

        # Carregar config
        self._load_config(config_path)

    def _detect_resolution(self):
        """Detecta resolução da tela e calcula ROIs."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                self._screen_width = monitor["width"]
                self._screen_height = monitor["height"]
                self._rois = calculate_rois(self._screen_width, self._screen_height)
                logger.info(f"OCR: Resolução detectada {self._screen_width}x{self._screen_height}")
        except Exception as e:
            logger.warning(f"Erro ao detectar resolução: {e}. Usando fallback 1920x1080")
            self._screen_width = 1920
            self._screen_height = 1080
            self._rois = calculate_rois(1920, 1080)

    def get_rois(self) -> Dict:
        """Retorna ROIs calculadas para a resolução atual."""
        if self._rois is None:
            self._detect_resolution()
        return self._rois

    def _check_dependencies(self):
        """Verifica se Tesseract e OpenCV estão disponíveis."""
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            self._tesseract_available = True
            logger.info("Tesseract disponível")
        except ImportError:
            logger.warning("pytesseract não instalado")
        except Exception as e:
            logger.warning(f"Tesseract não encontrado: {e}")

        try:
            import cv2
            self._cv2_available = True
            logger.info("OpenCV disponível")
        except ImportError:
            logger.warning("OpenCV não instalado")
            self._cv2_available = False

    def _load_config(self, config_path: str = None):
        """Carrega configuração do toggle."""
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "overlay_config.json")

        if Path(config_path).exists():
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self._enabled = config.get("ocr_fallback", {}).get("enabled", True)
                logger.info(f"OCR fallback enabled: {self._enabled}")
            except Exception as e:
                logger.warning(f"Erro ao carregar config OCR: {e}")

    def is_enabled(self) -> bool:
        """Retorna se OCR está habilitado."""
        return self._enabled and self._tesseract_available

    def should_run(self) -> bool:
        """Verifica se deve rodar (cooldown)."""
        import time
        return (time.time() - self._last_run) >= self._cooldown

    async def capture_and_read(self, screenshot_path: str = None) -> Optional[OCRResult]:
        """
        Captura tela e faz OCR.
        Roda em thread separada (asyncio.to_thread).
        """
        import time

        if not self.is_enabled():
            logger.debug("OCR não disponível ou desabilitado")
            return None

        if not self.should_run():
            logger.debug("OCR em cooldown")
            return None

        self._last_run = time.time()
        self._state = OCRState.ACTIVE

        try:
            # Rodar em thread separada para não bloquear
            result = await asyncio.to_thread(self._do_ocr, screenshot_path)
            self._state = OCRState.IDLE
            return result

        except Exception as e:
            logger.error(f"Erro no OCR: {e}")
            self._state = OCRState.FAILED
            return None

    def _do_ocr(self, screenshot_path: str = None) -> Optional[OCRResult]:
        """Executa OCR no screenshot."""
        if not self._cv2_available or not self._tesseract_available:
            return None

        import cv2
        import pytesseract
        from datetime import datetime
        import numpy as np

        # Obter ROIs dinâmicas baseadas na resolução
        rois = self.get_rois()

        # Capturar screenshot se não fornecido
        if screenshot_path is None:
            img_bytes = self._capture_screenshot()
            if not img_bytes:
                return None
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        else:
            img = cv2.imread(screenshot_path)

        if img is None:
            logger.warning("Não foi possível decodificar a imagem capturada")
            return None

        # Obter resolução real da imagem para ajustar ROIs se necessário
        img_height, img_width = img.shape[:2]
        if img_width != self._screen_width or img_height != self._screen_height:
            rois = calculate_rois(img_width, img_height)
            logger.info(f"OCR: Ajustando ROIs para {img_width}x{img_height}")

        result = OCRResult()
        result.timestamp = datetime.now().isoformat()

        # Processar cada ROI
        for field, roi in rois.items():
            x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
            
            # Extrair ROI
            roi_img = img[y:y+h, x:x+w]
            
            # Pré-processamento
            gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
            
            # Threshold adaptativo
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # OCR
            text = pytesseract.image_to_string(thresh, config="--psm 6")
            text = text.strip()

            # Parse específico por campo
            if field == "stage":
                result.stage = self._parse_stage(text)
            elif field == "gold":
                result.gold = self._parse_gold(text)
            elif field == "level":
                result.level = self._parse_level(text)
            elif field == "hp":
                result.hp = self._parse_hp(text)
            elif field == "augments":
                result.augments = self._parse_augments(text)

        # Calcular confiança simples (campos preenchidos)
        filled = sum([
            result.stage is not None,
            result.gold is not None,
            result.level is not None,
            result.hp is not None,
        ])
        result.confidence = filled / 4

        return result

    def _capture_screenshot(self) -> Optional[bytes]:
        """Captura screenshot da janela do jogo, retorna bytes em memoria."""
        try:
            import mss
            from io import BytesIO

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                buf = BytesIO()
                buf.write(mss.tools.to_png(screenshot.rgb, screenshot.size))
                buf.seek(0)
                return buf.read()

        except Exception as e:
            logger.warning(f"Erro ao capturar screenshot: {e}")
            return None

    def _parse_stage(self, text: str) -> Optional[str]:
        """Parse do stage."""
        import re
        match = re.search(r"(\d)-(\d)", text)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None

    def _parse_gold(self, text: str) -> Optional[int]:
        """Parse do gold."""
        import re
        text = text.replace("O", "0").replace("o", "0")
        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))
        return None

    def _parse_level(self, text: str) -> Optional[int]:
        """Parse do level."""
        import re
        match = re.search(r"(\d)", text)
        if match:
            return int(match.group(1))
        return None

    def _parse_hp(self, text: str) -> Optional[int]:
        """Parse do HP."""
        import re
        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))
        return None

    def _parse_augments(self, text: str) -> List[str]:
        """Parse dos augments."""
        # Simplificado - em produção usar matching com lista conhecida
        words = text.split()
        return [w for w in words if len(w) > 3][:3]


# Instância global
ocr_fallback = OCRFallback()


def create_ocr_fallback(config_path: str = None) -> OCRFallback:
    """Factory para criar OCR fallback."""
    return OCRFallback(config_path)


# Função de integração com lcu_parser
async def fallback_ocr_state() -> Optional[Dict]:
    """
    Função de conveniência - tenta OCR se LCU falhar.
    Usar como fallback em lcu_parser.parse_state() quando API retorna dados inválidos.
    """
    result = await ocr_fallback.capture_and_read()
    if result and result.confidence > 0.5:
        return {
            "stage": result.stage or "1-1",
            "gold": result.gold or 0,
            "level": result.level or 1,
            "hp": result.hp or 100,
            "augments": result.augments or [],
            "source": "ocr_fallback"
        }
    return None