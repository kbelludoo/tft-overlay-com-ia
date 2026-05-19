# TFT AI Overlay v5.0

Overlay inteligente para Teamfight Tactics com IA cloud + meta local + rastreamento de oponentes via Riot API.
OLED-black HUD em janela nativa (Chrome/Edge `--app` mode) ou CustomTkinter (`--ctk`).

## Instalacao

```
pip install -r requirements.txt
```

## Chaves de API (OBRIGATORIO)

### 1. Riot API Key (renova a cada 24h)
- Crie uma conta em: https://developer.riotgames.com/
- Gere uma **Development API Key** (válida por 24 horas)
- Cole no `.env`: `RIOT_API_KEY=sua_chave_riot`

> ⚠️ Se muitas pessoas usarem a mesma chave ao mesmo tempo, você pode ficar sem acesso.
> **Nunca compartilhe seu `.env`** — cada usuário deve ter sua própria chave.

### 2. AI API Key (coloca uma vez e pronto)
- Acesse https://opencode.ai e crie uma conta gratuita
- Gere sua chave de API (modelo compatível com OpenAI)
- Cole no `.env`: `AI_API_KEY=sua_chave_ai`

> ✅ A chave da IA é configurada **uma única vez** e não expira.

Configure as variaveis de ambiente (`.env`):

```
AI_API_KEY=sua_chave_llm
RIOT_API_KEY=sua_chave_riot
```

## Uso

```bash
python main.py              # HUD nativa (Chromium --app mode, 480px)
python main.py --ctk        # CustomTkinter legacy overlay
python main.py --mock       # Testa UI sem precisar do jogo
python main.py --port 9999  # Porta customizada
```

## Funcionalidades

- **Rastreamento de oponentes** — LCU API + Riot API com rank, composicoes, traits e historico
- **Deteccao de proximo adversario** — destaque do oponente que voce enfrentara
- **Rank badges** — elo visual de cada oponente (Iron → Challenger)
- **IA cloud** — prompt estruturado com meta local, augments registrados e analise de oponentes
- **MetaDB local** — composicoes por rank com fallback hardcoded
- **MemoryDB SQLite** — historico de partidas, winrates, padroes
- **Modo idle** — navegacao entre comps do meta quando fora de jogo
- **WebSocket push** — atualizacao em tempo real (fallback HTTP polling 2s)
- **Modo streamer** — oculta nomes e ranks dos oponentes

## Estrutura

```
tft-ai-overlay/
├── main.py                     # Orquestrador central
├── update_meta.py              # Atualizador de meta via Riot API
├── overlay_hud.html            # HUD OLED-black (interface principal)
├── overlay_config.json         # Configuracoes do usuario
├── requirements.txt
├── .env.example
├── .gitignore
├── core/
│   ├── lcu_parser.py           # LCU lockfile, sessao, parse_state, GamePhase
│   ├── opponent_tracker.py     # Analise de oponentes via Riot API
│   ├── rank_tracker.py         # Rank do jogador via LCU + Riot API
│   ├── web_server.py           # HTTP + WebSocket (estado, comps, mappings)
│   ├── memory_db.py            # SQLite WAL com conexao cacheada
│   ├── meta_db.py              # DB de composicoes por rank
│   ├── prompt_builder.py       # Construcao de prompt para IA
│   ├── cloud_agent.py          # Cliente OpenAI-compatible (httpx async)
│   ├── stage_heuristics.py     # Estimativas de level/ouro por stage
│   ├── api_wrapper.py          # SafeRequest com retry/jitter/cache
│   ├── data.py                 # Dados centralizados (champs, itens, augments)
│   ├── schema_validator.py     # Validacao + auto-reparo de JSON
│   ├── riot_key_manager.py     # Ciclo de vida da chave Riot API
│   ├── prompt_compressor.py    # Compressao de historico de partidas
│   ├── image_cache.py          # Cache de imagens TFT Academy
│   ├── native_window.py        # Janela Chromium --app mode
│   └── config.py               # Config, logging, DPI awareness
├── ui/
│   ├── overlay.py              # CustomTkinter overlay (legacy, --ctk)
│   └── styles.py               # Estilos CTk
└── data/
    ├── meta_db.json            # Meta composicoes
    ├── memory.db               # Historico SQLite
    └── images/                 # Cache de assets
```

## Atalhos

| Tecla | Acao |
|-------|------|
| `←` `→` | Navegar comps (modo idle) |
| `Esc` | Fechar HUD |
| Clique no oponente | Ciclar vivo → lutando → morto |
