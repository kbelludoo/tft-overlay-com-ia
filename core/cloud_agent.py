import os, json, logging, asyncio, re, hashlib
from datetime import datetime, timedelta
import httpx
from core.circuit_breaker import ai_api_breaker, CircuitBreakerOpenError
from core.local_llm_fallback import LocalLLMFallback

EXPECTED_KEYS = {"comp", "itens", "augments", "posicionamento", "contra", "motivo", "porque", "como", "viabilidade"}

def _extract_json(text: str) -> dict:
    """Extrai JSON de texto livre com multiplas estrategias de fallback"""
    if not text:
        return {}
    
    # 1. Tenta parse direto
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 2. Remove markdown blocks
    cleaned = text
    for marker in ["```json", "```"]:
        if cleaned.startswith(marker):
            cleaned = cleaned.split(marker, 1)[1].split("```", 1)[0].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
    
    # 3. Busca primeiro bloco JSON com regex
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    
    # 4. Tenta encontrar bloco maior (com nested braces)
    depth = 0
    start = None
    for i, c in enumerate(text):
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    start = None
    
    # 5. Fallback: constroi dict minimo com regex key-value
    result = {}
    for key in EXPECTED_KEYS:
        pattern = rf'"{key}"\s*:\s*"([^"]*)"'
        m = re.search(pattern, text)
        if m:
            result[key] = m.group(1)
    
    # viabilidade como numero
    m = re.search(r'"viabilidade"\s*:\s*(\d+)', text)
    if m:
        result["viabilidade"] = int(m.group(1))
    
    return result if result else {}


class CloudAgent:
    def __init__(self, cfg: dict):
        self.url = cfg["ai"]["base_url"]
        self.model = cfg["ai"]["model"]
        self.key = os.getenv("AI_API_KEY", "")
        self.timeout = cfg["ai"].get("timeout", 10)
        self.temp = cfg["ai"].get("temperature", 0.1)
        self.max_tokens = cfg["ai"].get("max_tokens", 400)
        self.max_retries = cfg["ai"].get("max_retries", 2)
        self.last = None
        self.debounce = timedelta(seconds=cfg.get("polling",{}).get("in_game",4))
        self.cache = None
        self.consecutive_failures = 0
        self.cooldown_until = None
        self._last_state_hash = None
        self._semantic_cache = {}
        logging.info(f"CloudAgent: {self.model} @ {self.url}")

    def _compute_state_hash(self, prompt: str) -> str:
        """Extrai partes relevantes do prompt e calcula hash"""
        relevant = []
        for line in prompt.split("\n"):
            if any(kw in line for kw in ["Stage:", "Ouro:", "Nivel:", "Board:", "Augments atuais:", "OPONENTES"]):
                relevant.append(line.strip())
        key = "|".join(relevant)
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cached_response(self, state_hash: str) -> dict | None:
        """Busca resposta cacheada para o mesmo estado"""
        if state_hash in self._semantic_cache:
            cached, timestamp = self._semantic_cache[state_hash]
            age = datetime.now() - timestamp
            if age < timedelta(minutes=5):
                logging.info(f"Cache semântico hit (idade: {age.seconds}s)")
                return cached
            del self._semantic_cache[state_hash]
        return None

    def _cache_response(self, state_hash: str, response: dict):
        """Armazena resposta no cache semântico"""
        self._semantic_cache[state_hash] = (response, datetime.now())
        if len(self._semantic_cache) > 20:
            oldest = min(self._semantic_cache.items(), key=lambda x: x[1][1])
            del self._semantic_cache[oldest[0]]

    def _should_call(self) -> bool:
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return False
        if not self.last:
            return True
        return datetime.now() - self.last > self.debounce

    async def call(self, prompt: str, fallback_meta: dict = None) -> dict:
        if not self._should_call():
            return self.cache or {"status": "Aguardando..."}
        if not self.key:
            return {"status": "AI_API_KEY nao configurada"}

        state_hash = self._compute_state_hash(prompt)
        cached = self._get_cached_response(state_hash)
        if cached:
            self.cache = cached
            self.last = datetime.now()
            return cached

        from core.config import get_tft_set
        tft_set = get_tft_set()
        system_prompt = (
            f"Voce e um coach Grandmaster de TFT {tft_set}. "
            "Retorne APENAS JSON valido em portugues, sem markdown, sem explicacao, sem texto extra. "
            "Chaves obrigatorias: comp, itens, augments, posicionamento, contra, motivo, porque, como, viabilidade. "
            "viabilidade: numero de 0 a 100 (quao forte e a sugestao). "
            "Exemplo: {\"comp\":\"Dark Star Flex\",\"itens\":\"Jhin: Gume do Infinito, Canhao de Repente, Ultimo Sussurro\",\"augments\":\"Arvore de Traits, Que os 4 Estejam Com Voce\",\"posicionamento\":\"Jhin no canto oposto ao carry inimigo\",\"contra\":\"Sniper\",\"motivo\":\"Counter direto com dano massivo\",\"porque\":\"Dark Star escala bem com Jhin como carry principal. Sinergia forte com Sniper e Dark Star.\",\"como\":\"Early: monte base com Dark Star 3. Mid: foque itens do Jhin. Late: complete com Kai'Sa e posicione Jhin no canto oposto.\",\"viabilidade\":85}"
        )

        payload = {
            "model": self.model,
            "temperature": self.temp,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

        for attempt in range(self.max_retries + 1):
            try:
                async def _do_request():
                    async with httpx.AsyncClient(timeout=self.timeout) as c:
                        r = await c.post(self.url, json=payload, headers=headers)
                        r.raise_for_status()
                        return r.json()

                try:
                    data = await ai_api_breaker.async_call(_do_request)
                except CircuitBreakerOpenError:
                    logging.warning("Circuit Breaker aberto — usando fallback")
                    return self._get_fallback_response(fallback_meta)

                choices = data.get("choices", [])
                if not choices:
                    raise ValueError(f"Resposta inesperada da API: {data}")
                msg = choices[0].get("message", {})
                content = msg.get("content", "") or ""
                if not content.strip():
                    content = msg.get("reasoning_content", "") or ""

                if content:
                    self._last_response = content
                    ai_api_breaker.record_success()
                    return self._parse_response(content, fallback_meta)
                else:
                    logging.warning("Resposta vazia da IA")
                    if attempt < self.max_retries:
                        continue
                    return self._get_fallback_response(fallback_meta)

            except CircuitBreakerOpenError:
                logging.warning("Circuit Breaker aberto — fallback ja tratado no inner try")
                return self._get_fallback_response(fallback_meta)

            except Exception as e:
                logging.warning(f"API error (try {attempt+1}/{self.max_retries+1}): {e}")
                ai_api_breaker.record_failure(e)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= 3:
                        self.cooldown_until = datetime.now() + timedelta(seconds=10)
                        logging.warning("3 falhas consecutivas. Cooldown de 10s ativado.")
                    if fallback_meta:
                        logging.info("Usando fallback deterministico (meta local)")
                        return self._get_fallback_response(fallback_meta)
                    return {"status": f"Falha API: {str(e)[:40]}"}

    def _get_fallback_response(self, fallback_meta: dict) -> dict:
        if not fallback_meta:
            return {"status": "Sem fallback disponivel"}
        local = LocalLLMFallback.get_instance()
        if local.is_available:
            local_result = local.generate(prompt_text, context)
            if local_result:
                return local_result
        return {
            "comp": fallback_meta.get("name", "Meta Padrao"),
            "itens": ", ".join(f"{champ}: {', '.join(items)}" for champ, items in fallback_meta.get("core_items", {}).items()),
            "augments": ", ".join(fallback_meta.get("augments", [])),
            "posicionamento": fallback_meta.get("positioning", ""),
            "contra": f"Forte vs {fallback_meta.get('counters', {}).get('strong_vs', [])}",
            "motivo": "Fallback: IA indisponivel. Usando meta local.",
            "viabilidade": 60,
            "units": fallback_meta.get("units", []),
            "core_items": fallback_meta.get("core_items", {}),
            "tanks": fallback_meta.get("tanks", []),
            "levels": fallback_meta.get("levels", ""),
            "dicas": fallback_meta.get("dicas", ""),
        }
