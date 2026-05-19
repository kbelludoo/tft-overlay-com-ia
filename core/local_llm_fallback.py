"""
Fallback LLM Local (Edge AI).

Usa llama-cpp-python com grammar JSON para respostas estruturadas.
Ativado quando a API remota falha ou rate limit é atingido.

Requisitos (opcional):
  pip install llama-cpp-python

Modelos recomendados (GGUF Q4_K_M):
  - Qwen2.5-1.5B-Instruct (~1GB)
  - Phi-3-mini-4k-instruct (~2GB)
  - Gemma-2-2b-it (~1.5GB)
"""
import json, logging, os
from pathlib import Path

logger = logging.getLogger(__name__)

# Tenta importar llama_cpp (opcional)
try:
    from llama_cpp import Llama
    HAS_LLAMA = True
except ImportError:
    HAS_LLAMA = False
    logger.info("llama-cpp-python nao instalado. Fallback local desativado.")

MODEL_DIR = Path(__file__).parent.parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# JSON Schema para forçar formato correto
TFT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "comp": {"type": "string"},
        "itens": {"type": "string"},
        "augments": {"type": "string"},
        "posicionamento": {"type": "string"},
        "contra": {"type": "string"},
        "motivo": {"type": "string"},
        "porque": {"type": "string"},
        "como": {"type": "string"},
        "viabilidade": {"type": "integer", "minimum": 0, "maximum": 100},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["comp", "itens", "augments", "viabilidade"],
}

SYSTEM_PROMPT = """Voce e um coach Grandmaster de TFT Set 17.
Retorne APENAS JSON valido em portugues, sem markdown, sem explicacao extra.
Chaves obrigatorias: comp, itens, augments, posicionamento, contra, motivo, porque, como, viabilidade, confidence.
viabilidade e confidence: 0-100."""

COMPACT_PROMPT_SUFFIX = """
Responda APENAS com JSON. Seja direto. Maximo 200 tokens."""


class LocalLLM:
    def __init__(self, model_path: str = None, n_ctx: int = 2048, n_threads: int = 4):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._llm = None
        self._available = False
        self._init_model()

    def _init_model(self):
        if not HAS_LLAMA:
            logger.info("llama-cpp-python nao disponivel")
            return

        if not self.model_path:
            models = list(MODEL_DIR.glob("*.gguf"))
            if not models:
                logger.info("Nenhum modelo GGUF encontrado em models/")
                return
            self.model_path = str(models[0])

        if not os.path.exists(self.model_path):
            logger.warning(f"Modelo nao encontrado: {self.model_path}")
            return

        try:
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=False,
            )
            self._available = True
            logger.info(f"Modelo local carregado: {self.model_path}")
        except Exception as e:
            logger.warning(f"Erro ao carregar modelo: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    def call(self, prompt: str, max_tokens: int = 300) -> dict | None:
        """Chama o modelo local e retorna JSON"""
        if not self._available:
            return None

        try:
            full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}\n{COMPACT_PROMPT_SUFFIX}"
            output = self._llm(
                full_prompt,
                max_tokens=max_tokens,
                temperature=0.2,
                top_p=0.9,
                stop=["</s>", "\n\n"],
            )
            text = output["choices"][0]["text"].strip()

            # Tenta parsear JSON
            result = self._extract_json(text)
            if result and "comp" in result:
                result["confidence"] = min(result.get("confidence", 40), 40)
                result["motivo"] = result.get("motivo", "Fallback local (sem API)")
                return result

        except Exception as e:
            logger.warning(f"Erro no modelo local: {e}")

        return None

    def _extract_json(self, text: str) -> dict | None:
        """Extrai JSON de texto"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return None


class LocalLLMFallback:
    _instance = None

    def __init__(self):
        self._llm = LocalLLM()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_available(self):
        return self._llm.is_available

    def generate(self, prompt_text, context):
        if not self.is_available:
            return None
        prompt = f"{prompt_text}\n\nContext: {json.dumps(context, ensure_ascii=False)}"
        return self._llm.call(prompt)


def create_fallback_local(model_path: str = None) -> LocalLLM:
    """Cria instância do fallback local"""
    return LocalLLM(model_path=model_path)
