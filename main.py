#!/usr/bin/env python3
import os, sys, json, signal, queue, asyncio, threading, time, logging, argparse, requests, base64, random, uuid
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from enum import Enum, StrEnum
from core.config import load_config, setup_logging, enable_dpi_awareness, save_config, get_riot_region, get_riot_platform, get_tft_set
from core.lcu_parser import get_lcu_creds, fetch_session, parse_state, GameState, GamePhase, GAME_PHASES_ACTIVE, GAME_PHASES_ENDED
from core.memory_db import MemoryDB
from core.meta_db import MetaDB, pt, pt_item, pt_augment
from core.data import to_tft17, normalize_augment
from core.prompt_builder import PromptBuilder
from core.cloud_agent import CloudAgent
from core.opponent_tracker import analyze_all_opponents, get_tft_rank
from core.rank_tracker import get_my_rank, get_comps_for_rank
from core.stage_heuristics import enrich_state
from core.api_wrapper import safe_req, get_current_patch, check_patch_change, fetch_champion_list
from core.riot_key_manager import riot_key_mgr
from core.schema_validator import validate_and_repair_all, get_validation_summary
from core.web_server import start_server as start_web_server, set_state as set_web_state, set_cmd_queue as set_web_cmd_queue, update_status as update_web_status

from core.debouncer import state_debouncer
from core.ev_calculator import calculate_ev_decision, get_quick_tag, format_ev_display
from core.transition_advisor import get_slam_recommendation
from core.augment_synergy import analyze_augment_set, format_analysis_display
from core.matchup_tracker import ghost_tracker, get_ghost_opponents, format_ghost_display
from core.spike_detector import spike_detector, get_opponent_spike_status, format_spike_display
from core.carousel_predictor import carousel_predictor, predict_carousel
from core.opponent_cache import opponent_cache_mgr
from core.llm_stream import stream_manager
from core.contest_matrix import calc_contest_score
from core.lobby_pressure import calc_lobby_pressure
from core.top4_score import calc_top4_pressure
from core.zone_risk_map import calc_zone_risks
from core.micro_decision_engine import decide_micro_action
from core.game_session import GameSession, MatchState
from core.circuit_breaker import riot_api_breaker, CircuitBreakerOpenError
from core.game_loop import start_game_loop
from core.logging_utils import log_critical_error
from core.lcu_utils import get_team_import_code, extract_opponent_names, fetch_opponents_rank, detect_next_opponent

def get_my_puuid_and_summoner_id(creds: tuple) -> tuple:
    """Obtem PUUID e encryptedSummonerId via API Riot"""
    port, pwd = creds
    auth = base64.b64encode(f'riot:{pwd}'.encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    
    try:
        r = requests.get(f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner",
                         headers=headers, verify=False, timeout=5)
        if r.status_code == 200:
            data = r.json()
            puuid = data.get("puuid", "")
            summoner_id = data.get("summonerId", "")
            return puuid, summoner_id
    except Exception as e:
        logging.debug(f"Erro ao obter PUUID: {e}")
    return "", ""

def get_opponents_from_spectator_api(creds: tuple) -> list:
    cfg = load_config()
    region = get_riot_region(cfg)
    platform = get_riot_platform(cfg)
    puuid, summoner_id = get_my_puuid_and_summoner_id(creds)
    if not puuid:
        logging.warning("Nao conseguiu obter PUUID do jogador")
        return []
    
    # Obtem encryptedSummonerId via PUUID
    riot_key = os.getenv("RIOT_API_KEY", "")
    if not riot_key:
        logging.warning("RIOT_API_KEY nao configurada")
        return []
    
    try:
        r = requests.get(f"https://{platform}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}",
                         headers={"X-Riot-Token": riot_key}, verify=False, timeout=5)
        if r.status_code != 200:
            logging.warning(f"Erro ao buscar conta por PUUID: {r.status_code}")
            return []
        account = r.json()
        game_name = account.get("gameName", "")
        tag_line = account.get("tagLine", "")
        
        if not game_name:
            logging.warning("gameName vazio na resposta da conta")
            return []
        
        # Obtem encryptedSummonerId
        r = requests.get(f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-riot-id/{game_name}/{tag_line}",
                         headers={"X-Riot-Token": riot_key}, verify=False, timeout=5)
        if r.status_code != 200:
            logging.warning(f"Erro ao buscar summoner: {r.status_code}")
            return []
        summoner = r.json()
        encrypted_id = summoner.get("id", "")
        
        if not encrypted_id:
            logging.warning("encryptedSummonerId vazio")
            return []
        
        # Chama API de spectator
        r = requests.get(f"https://{region}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{encrypted_id}",
                         headers={"X-Riot-Token": riot_key}, verify=False, timeout=5)
        
        if r.status_code == 404:
            logging.info("Nenhuma partida ativa encontrada (404)")
            return []
        elif r.status_code != 200:
            logging.warning(f"Erro spectator API: {r.status_code} - {r.text[:200]}")
            return []
        
        game_data = r.json()
        participants = game_data.get("participants", [])
        logging.info(f"Spectator API retornou {len(participants)} participantes")
        
        opp_names = []
        for p in participants:
            name = p.get("summonerName", "") or p.get("gameName", "") or p.get("riotId", "")
            if name and name not in opp_names:
                opp_names.append(name)
        
        return opp_names
    except Exception as e:
        logging.error(f"Erro na spectator API: {e}")
        return []

def run_health_check(cfg: dict) -> dict:
    """Health check no startup: verifica APIs, chaves, e conexoes"""
    health = {"status": "online", "checks": {}}
    
    # AI API
    ai_key = os.getenv("AI_API_KEY", "")
    if ai_key:
        health["checks"]["ai_api"] = "ok"
    else:
        health["checks"]["ai_api"] = "missing"
        health["status"] = "limited"
    
    # Riot API
    riot_key = os.getenv("RIOT_API_KEY", "")
    if riot_key:
        health["checks"]["riot_api"] = "ok"
    else:
        health["checks"]["riot_api"] = "missing"
        health["status"] = "limited"
    
    # LCU
    creds = get_lcu_creds()
    if creds:
        health["checks"]["lcu"] = "ok"
    else:
        health["checks"]["lcu"] = "not_running"
        health["status"] = "offline"
    
    # Community Dragon
    try:
        patch = get_current_patch()
        health["checks"]["community_dragon"] = f"patch {patch}" if patch else "error"
    except Exception as e:
        logging.debug(f"Erro health check community dragon: {e}")
        health["checks"]["community_dragon"] = "error"
    
    logging.info(f"Health check result: {health}")
    return health


def _auto_update_meta_if_stale(riot_key: str):
    """Verifica se meta_db.json tem >24h e atualiza em background se possivel"""
    meta_path = Path(__file__).parent / "data" / "meta_db.json"
    if not meta_path.exists():
        logging.info("meta_db.json nao existe. Atualizando...")
        _run_meta_update_background()
        return
    
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last_updated = data.get("last_updated", "")
        if not last_updated:
            logging.info("meta_db.json sem timestamp. Atualizando...")
            _run_meta_update_background()
            return
        
        from datetime import datetime as dt
        updated_at = dt.fromisoformat(last_updated)
        age_hours = (dt.now() - updated_at).total_seconds() / 3600
        
        if age_hours > 24:
            logging.info(f"Meta tem {age_hours:.1f}h (>24h). Atualizando em background...")
            _run_meta_update_background()
        else:
            logging.info(f"Meta tem {age_hours:.1f}h (<24h). Cache valido.")
    except Exception as e:
        logging.warning(f"Erro ao verificar idade do meta: {e}")


def _run_meta_update_background():
    """Roda update_meta.py em thread background para nao bloquear startup"""
    def _worker():
        try:
            from update_meta import main as update_meta_main
            update_meta_main()
            logging.info("Meta atualizado automaticamente com sucesso.")
        except Exception as e:
            logging.warning(f"Falha ao atualizar meta automaticamente: {e}")
    threading.Thread(target=_worker, daemon=True).start()


# ============================================================
# GRACEFUL SHUTDOWN
# ============================================================

_shutdown_event = threading.Event()

def _shutdown_handler(signum, frame):
    logging.info("Sinal de encerramento recebido. Fechando aplicacao...")
    _shutdown_event.set()

def setup_graceful_shutdown():
    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _shutdown_handler)

def _graceful_shutdown():
    logging.info("Iniciando shutdown gracioso...")
    try:
        from core.opponent_cache import opponent_cache_mgr
        if hasattr(opponent_cache_mgr, '_cache') and hasattr(opponent_cache_mgr._cache, '_lock'):
            opponent_cache_mgr._cache._lock.acquire(timeout=2)
            opponent_cache_mgr._cache._lock.release()
    except Exception:
        pass
    logging.info("Shutdown concluido.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="TFT AI Overlay v5.0")
    parser.add_argument("--mock", action="store_true", help="Modo de teste")
    parser.add_argument("--ctk", action="store_true", help="Usar interface CustomTkinter (legado)")
    parser.add_argument("--port", type=int, default=8765, help="Porta do servidor web (padrao 8765)")
    args = parser.parse_args()

    enable_dpi_awareness()
    cfg = load_config()
    setup_logging(cfg)
    logging.info("TFT AI Overlay v5.0 - Iniciando")
    
    # Valida schemas no startup (com auto-repair)
    validation = validate_and_repair_all()
    logging.info(f"Schema validation:\n{get_validation_summary()}")
    
    # Inicializa gestor de chave Riot
    riot_key = os.getenv("RIOT_API_KEY", "")
    if riot_key:
        riot_key_mgr.key = riot_key
        # So registra nova criacao se nao houver estado valido ou se a chave mudou
        if not riot_key_mgr._expires_at or riot_key_mgr.is_expired():
            riot_key_mgr.register_key_creation(expires_in_hours=24)
            logging.info(f"Riot key manager: nova chave registrada")
        else:
            logging.info(f"Riot key manager: {riot_key_mgr.status_text}")
    
    # Health check no startup
    health = run_health_check(cfg)
    logging.info(f"Health check: {health}")
    
    # Detector de patch
    if check_patch_change():
        current_patch = get_current_patch()
        logging.info(f"Patch detectado: {current_patch}. Atualizando dados...")
        q_status = queue.Queue()
        # Atualiza dados dinamicos
        fetch_champion_list(current_patch)
        # Atualiza meta se tiver chave Riot
        if os.getenv("RIOT_API_KEY"):
            logging.info("Atualizando meta via Riot API...")
            try:
                from update_meta import main as update_meta_main
                update_meta_main()
            except Exception as e:
                logging.warning(f"Falha ao atualizar meta: {e}")
    
    # Auto-update meta se >24h e tiver chave Riot
    _auto_update_meta_if_stale(riot_key)
    
    if not args.mock and not os.getenv("AI_API_KEY"):
        print("AI_API_KEY nao configurada.")
        sys.exit(1)

    mem = MemoryDB()
    
    # Detecta rank do jogador para meta personalizado
    my_rank = get_my_rank()
    rank_tier = my_rank.get("tier", "GOLD")
    rank_div = my_rank.get("rank", "IV")
    logging.info(f"Rank do jogador: {rank_tier} {rank_div} ({my_rank.get('lp', 0)} LP)")
    
    meta = MetaDB(player_rank_tier=rank_tier, player_rank_div=rank_div)
    builder = PromptBuilder(mem, meta)
    agent = CloudAgent(cfg)
    q = queue.Queue()
    cmd_q = queue.Queue()  # Fila de comandos do overlay para main

    # Pre-carrega imagens de campeoes e itens do CommunityDragon
    try:
        from core.image_cache import preload_all_images
        threading.Thread(target=preload_all_images, daemon=True).start()
    except Exception as e:
        logging.warning(f"Falha ao pre-carregar imagens: {e}")

    # Inicia servidor web para overlay-hud.html
    set_web_cmd_queue(cmd_q)
    web_port = start_web_server(args.port)

    if args.ctk:
        from ui.overlay import Overlay
        app = Overlay(cfg, q, cmd_q)
        def close(sig, f):
            app._close()
            _shutdown_event.set()
        signal.signal(signal.SIGINT, close)
        signal.signal(signal.SIGTERM, close)
        if sys.platform == "win32":
            signal.signal(signal.SIGBREAK, close)

        threading.Thread(target=lambda: asyncio.run(start_game_loop(q, cmd_q, builder, agent, mem, meta, cfg, mock=args.mock)), daemon=True).start()
        app.run()
        _shutdown_event.set()
    else:
        print(f"TFT Overlay rodando em http://127.0.0.1:{web_port}")
        print(f"HUD: http://127.0.0.1:{web_port}/hud")

        overlay_w = cfg.get("window", {}).get("width", 480)
        overlay_h = cfg.get("window", {}).get("height", 860)
        overlay_alpha = cfg.get("window", {}).get("alpha", 0.95)

        setup_graceful_shutdown()

        def _shutdown():
            try:
                save_config(cfg)
            except Exception:
                pass
            sys.exit(0)

        threading.Thread(target=lambda: asyncio.run(start_game_loop(q, cmd_q, builder, agent, mem, meta, cfg, mock=args.mock)), daemon=True).start()

        try:
            from core.native_window import run_native
            started = run_native(
                f"http://127.0.0.1:{web_port}/hud",
                width=overlay_w,
                height=overlay_h,
            )
        except Exception as e:
            logging.warning(f"Falha ao abrir janela nativa: {e}")

        try:
            while not _shutdown_event.is_set():
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            _shutdown_event.set()
        finally:
            _graceful_shutdown()
        _shutdown()

if __name__ == "__main__":
    main()
