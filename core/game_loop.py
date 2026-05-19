import json, queue, asyncio, time, logging, random, base64, requests
from pathlib import Path
from datetime import datetime

from core.lcu_parser import get_lcu_creds, fetch_session, parse_state, GameState, GamePhase, GAME_PHASES_ACTIVE, GAME_PHASES_ENDED
from core.memory_db import MemoryDB
from core.meta_db import MetaDB, pt, pt_item, pt_augment
from core.data import normalize_augment
from core.prompt_builder import PromptBuilder
from core.cloud_agent import CloudAgent
from core.opponent_tracker import analyze_all_opponents
from core.rank_tracker import get_my_rank, get_comps_for_rank
from core.stage_heuristics import enrich_state
from core.web_server import set_state as set_web_state, update_status as update_web_status
from core.debouncer import state_debouncer
from core.ev_calculator import calculate_ev_decision, get_quick_tag, format_ev_display
from core.transition_advisor import get_slam_recommendation
from core.augment_synergy import analyze_augment_set, format_analysis_display
from core.matchup_tracker import ghost_tracker, get_ghost_opponents, format_ghost_display
from core.spike_detector import spike_detector, get_opponent_spike_status
from core.carousel_predictor import carousel_predictor, predict_carousel
from core.contest_matrix import calc_contest_score
from core.lobby_pressure import calc_lobby_pressure
from core.top4_score import calc_top4_pressure
from core.zone_risk_map import calc_zone_risks
from core.micro_decision_engine import decide_micro_action
from core.game_session import GameSession, MatchState
from core.circuit_breaker import CircuitBreakerOpenError
from core.logging_utils import log_critical_error



_AUGMENTS_FILE = Path(__file__).parent.parent / "data" / "registered_augments.json"

def _format_items_with_global_priority(core_items: dict) -> dict:
    if not core_items:
        return {}
    all_items = []
    for champ, items in core_items.items():
        for item in items:
            all_items.append((champ, item))
    result = {}
    for idx, (champ, item) in enumerate(all_items, 1):
        if champ not in result:
            result[champ] = []
        result[champ].append(f"{idx}. {item}")
    return result

def _inject_context(data: dict, mem: MemoryDB):
    ctx = mem.get_context()
    data["context"] = ctx
    data["overlay_win_rate"] = ctx.get("overlay_win_rate", 0)
    data["overlay_total"] = ctx.get("overlay_total", 0)
    data["account_win_rate"] = ctx.get("win_rate", 0)
    data["account_total"] = ctx.get("total", 0)

def _load_saved_augments() -> list:
    try:
        if _AUGMENTS_FILE.exists():
            with open(_AUGMENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            augments = data.get("augments", [])
            if augments:
                logging.info(f"Carregados {len(augments)} augments salvos: {augments}")
            return augments
    except Exception as e:
        logging.warning(f"Erro ao carregar augments salvos: {e}")
    return []

def _save_augments(augments: list):
    try:
        _AUGMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUGMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"augments": augments, "saved_at": datetime.now().isoformat()}, f, indent=2)
    except Exception as e:
        logging.exception(f"Erro ao salvar augments: {e}")

def _clear_augments():
    try:
        if _AUGMENTS_FILE.exists():
            _AUGMENTS_FILE.unlink()
    except Exception as e:
        logging.debug(f"Erro ao limpar augments: {e}")

async def start_game_loop(q: queue.Queue, cmd_q: queue.Queue, builder: PromptBuilder, agent: CloudAgent, mem: MemoryDB, meta: MetaDB, cfg: dict, mock: bool = False):
    from core.lcu_utils import get_team_import_code, extract_opponent_names, fetch_opponents_rank, detect_next_opponent, _opponent_cache, _save_opponent_state, _load_opponent_state

    def _status(msg):
        q.put({"status": msg})
        update_web_status(msg)

    session = GameSession()
    session.registered_augments = _load_saved_augments()
    poll = cfg.get("polling", {})

    my_rank = get_my_rank()
    rank_tier = my_rank.get("tier", "GOLD")
    rank_div = my_rank.get("rank", "IV")
    session.session.last_known_rank = f"{rank_tier}_{rank_div}"
    logging.info(f"Rank do jogador: {rank_tier} {rank_div} ({my_rank.get('lp', 0)} LP)")

    top_comps = meta.get_top_comps()
    best_comps_for_rank = get_comps_for_rank(rank_tier)

    try:
        session.creds = get_lcu_creds()
    except Exception as e:
        logging.warning(f"LCU nao disponivel: {e}")
        session.creds = None

    best_comp_name = best_comps_for_rank[0] if best_comps_for_rank else "K/DA Popstar"
    best = None
    for comp in top_comps:
        if comp.get("name") == best_comp_name:
            best = comp
            break
    if not best and top_comps:
        best = top_comps[0]

    if best:
        items_info = best.get("core_items", {})
        units = [pt(u) for u in best.get("units", [])]
        initial_import_code = await asyncio.to_thread(get_team_import_code, units, session.creds) if session.creds else ""
        initial_data = {
            "status": "Inicializando...",
            "comp": f"[META] {best['name']} (Tier {best['tier']}) - Rank: {rank_tier}",
            "itens": " | ".join([f"{pt(champ)}: {', '.join(pt_item(i) for i in items)}" for champ, items in items_info.items()]),
            "augments": ", ".join([pt_augment(a) for a in best.get("augments", [])]),
            "posicionamento": best.get("positioning", ""),
            "tanks": [pt(t) for t in best.get("tanks", [])],
            "levels": best.get("levels", ""),
            "dicas": best.get("dicas", ""),
            "contra": f"Forte vs {best.get('counters', {}).get('strong_vs', [])}",
            "motivo": best.get("description", ""),
            "units": units,
            "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in items_info.items()}),
            "import_code": initial_import_code,
            "opponents": [],
            "game_id": -1
        }
        _inject_context(initial_data, mem)
        q.put(initial_data)
        set_web_state(initial_data)
        session.last_suggestion = q.queue[-1]

    while True:
        try:
            if session.match_state == MatchState.ENDED:
                session.match_state = MatchState.IDLE
                logging.info("FSM: ENDED -> IDLE (retornando ao lobby)")

            if not riot_api_breaker.is_available:
                logging.warning(
                    f"Riot API Circuit Breaker OPEN — pulando chamadas Riot. "
                    f"Status: {riot_api_breaker.get_status()}"
                )

            try:
                cmd = cmd_q.get_nowait()
                if cmd.get("action") == "reanalyze":
                    manual_aug = normalize_augment(cmd.get("manual_augment", ""))
                    if manual_aug and manual_aug not in session.registered_augments:
                        session.registered_augments.append(manual_aug)
                        await asyncio.to_thread(_save_augments, session.registered_augments)
                        logging.info(f"Augment manual adicionado: {manual_aug}")
                    logging.info("Comando de reanalise recebido. Forcando reexecutar...")
                    session._reanalyze_requested = True
                    _status("Reanalisando...")
                elif cmd.get("action") == "register_augment":
                    aug = normalize_augment(cmd.get("augment", ""))
                    if aug:
                        session.registered_augments.append(aug)
                        await asyncio.to_thread(_save_augments, session.registered_augments)
                        logging.info(f"Augment registrado pelo usuario: {aug}")
                        _status(f"Augment '{aug}' registrado! Sera usado na proxima analise.")
                elif cmd.get("action") == "quit":
                    logging.info("Quit recebido da interface. Encerrando game loop...")
                    return
            except queue.Empty:
                pass

            current_rank = await asyncio.to_thread(get_my_rank)
            current_tier = current_rank.get("tier", "GOLD")
            current_div = current_rank.get("rank", "IV")
            current_rank_key = f"{current_tier}_{current_div}"

            if current_rank_key != session.last_known_rank:
                logging.info(f"Rank mudou de {session.last_known_rank} para {current_rank_key}")
                session.last_known_rank = current_rank_key
                meta.update_rank(current_tier, current_div)
                _status(f"Meta atualizado para {current_tier} {current_div}!")

            if mock:
                top_comps = meta.get_top_comps()
                mock_comp = top_comps[0] if top_comps else {}
                mock_units = [pt(u) for u in mock_comp.get("units", [])]
                mock_res = {
                    "status": "Mock — Testando overlay",
                    "stage": "4-2",
                    "level": 7,
                    "gold": 42,
                    "comp": mock_comp.get("name", "Meta Padrao"),
                    "units": mock_units,
                    "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in mock_comp.get("core_items", {}).items()}),
                    "posicionamento": mock_comp.get("positioning", ""),
                    "tanks": [pt(t) for t in mock_comp.get("tanks", [])],
                    "levels": mock_comp.get("levels", ""),
                    "dicas": mock_comp.get("dicas", ""),
                    "viabilidade": 75,
                    "next_augments": [],
                    "augments": "",
                    "registered_augments": [],
                    "comp_win_rate": mock_comp.get("win_rate", "52"),
                    "comp_avg_placement": mock_comp.get("avg_placement", "3.8"),
                    "comp_games": mock_comp.get("games", "1200"),
                    "import_code": "",
                    "opponents": [
                        {"name": "Jogador1", "rank": "GOLD II (34 LP)", "avg": "4.1", "recent_comps": [], "health": 72},
                        {"name": "Jogador2", "rank": "PLATINUM IV (12 LP)", "avg": "3.5", "recent_comps": [], "health": 45},
                        {"name": "Jogador3", "rank": "SILVER I (78 LP)", "avg": "5.2", "recent_comps": [], "health": 88},
                        {"name": "Jogador4", "rank": "Sem Rank", "avg": "4.8", "recent_comps": [], "health": 30},
                        {"name": "Jogador5", "rank": "DIAMOND III (55 LP)", "avg": "2.9", "recent_comps": [], "health": 95},
                        {"name": "Jogador6", "rank": "GOLD IV (0 LP)", "avg": "4.5", "recent_comps": [], "health": 60},
                        {"name": "Jogador7", "rank": "EMERALD II (22 LP)", "avg": "3.2", "recent_comps": [], "health": 15},
                    ],
                    "next_opponent": "Jogador4",
                    "game_id": "mock12345",
                    "prompt": "(Mock: teste de interface)",
                    "alt_comps": [{
                        "name": c.get("name",""), "tier": c.get("tier",""),
                        "units": [pt(u) for u in c.get("units",[])],
                        "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in c.get("core_items",{}).items()}),
                        "posicionamento": c.get("posicionamento",""), "tanks": [pt(t) for t in c.get("tanks",[])],
                        "levels": c.get("levels",""), "dicas": c.get("dicas",""),
                    } for c in top_comps[:3] if c.get("name") != mock_comp.get("name","")],
                }
                _inject_context(mock_res, mem)
                q.put(mock_res)
                set_web_state(mock_res)
                await asyncio.sleep(10)
                continue

            session.creds = get_lcu_creds()
            if not session.creds:
                _status("Aguardando cliente do LoL...")
                await asyncio.sleep(5)
                continue

            sess = await asyncio.to_thread(fetch_session, *session.creds)
            if not sess:
                _status("Entre em uma partida de TFT para analisar oponentes")
                await asyncio.sleep(5)
                continue

            game_state = parse_state(sess)

            if hasattr(game_state, 'stage'):
                should_process = state_debouncer.should_process(
                    stage=game_state.stage,
                    gold=game_state.gold,
                    level=game_state.level,
                    board=game_state.my_board,
                    shop=game_state.shop,
                    augments=game_state.my_augments,
                    opponents=game_state.opponents,
                    hp=getattr(game_state, 'hp', 100)
                )
                if not should_process:
                    await asyncio.sleep(3)
                    continue

            phase = sess.get("phase") or (sess.get("gameData") or {}).get("gamePhase", "Unknown")
            game_id = (sess.get("gameData") or {}).get("gameId")
            game_mode = (sess.get("gameData") or {}).get("gameMode", "")

            logging.info(f"Session phase={phase}, gameMode={game_mode}, gameId={game_id}")
            logging.info(f"Session keys: {list(sess.keys())}")
            gd = sess.get("gameData", {})
            if gd:
                logging.info(f"gameData keys: {list(gd.keys())}")

            if not game_id:
                _status(f"Aguardando partida de TFT... (fase: {phase})")
                await asyncio.sleep(5)
                continue

            is_new_game = game_id and game_id != session.analyzed_game_id
            if phase in GAME_PHASES_ACTIVE and game_id and (is_new_game or session._reanalyze_requested):
                if is_new_game:
                    session.registered_augments.clear()
                    _clear_augments()
                    spike_detector.clear_spikes()
                    ghost_tracker.clear_history()
                session._reanalyze_requested = False
                _status("Analisando oponentes...")
                logging.info(f"Fase {phase} detectada. Extraindo oponentes...")

                opp_data = await asyncio.to_thread(extract_opponent_names, sess, session.creds)
                opp_names = [o["name"] for o in opp_data]
                logging.info(f"Encontrados {len(opp_names)} oponentes: {opp_names}")

                opp_ranks = await asyncio.to_thread(fetch_opponents_rank, opp_data)
                logging.info(f"Ranks obtidos via summonerId: {opp_ranks}")

                next_opp_name = await asyncio.to_thread(detect_next_opponent, sess, session.creds)
                logging.info(f"Proximo adversario detectado: {next_opp_name}")

                opponent_analysis = {}
                if opp_names:
                    try:
                        opponent_analysis = analyze_all_opponents(opp_names)
                        logging.info(f"Analise concluida para {len(opponent_analysis)} oponentes")
                    except Exception as e:
                        logging.exception(f"Erro ao analisar oponentes: {e}")
                        opponent_analysis = {}

                opp_list = []
                gs_opp_health = {o.get("name", ""): o.get("health", 100) for o in getattr(game_state, 'opponents', [])}
                for o in opp_data:
                    name = o["name"]
                    rank = opp_ranks.get(name, "")
                    if not rank and opponent_analysis.get(name):
                        rank = opponent_analysis[name].get("rank", "")
                    avg = opponent_analysis.get(name, {}).get("avg_placement", "")
                    recent_comps = opponent_analysis.get(name, {}).get("recent_comps", [])
                    health = gs_opp_health.get(name, 100)
                    opp_list.append({"name": name, "rank": rank, "avg": avg, "recent_comps": recent_comps, "health": health})

                ghost_pool = []
                try:
                    ghost_pool = get_ghost_opponents(opp_list, game_state.stage)
                    logging.info(f"Ghost pool: {len(ghost_pool)} possiveis oponentes")
                except Exception as e:
                    logging.exception(f"Erro no Ghost Matchups: {e}")
                    ghost_pool = []

                spike_status = []
                try:
                    spike_status = get_opponent_spike_status(opp_list, spike_detector)
                    logging.info(f"Spikes detectados: {len([s for s in spike_status if s.get('spike')])}")
                except Exception as e:
                    logging.exception(f"Erro no Spike Detector: {e}")
                    spike_status = []

                if opponent_analysis:
                    logging.info("Chamando IA para counter-pick...")
                    game_state.opponents = [{"name": n, "traits": []} for n in opponent_analysis.keys()]
                    game_state = enrich_state(game_state)
                    prompt = builder.build(game_state, opponent_analysis, my_rank, session.registered_augments)

                    fallback_meta = meta.suggest_by_board(game_state.my_board, game_state.stage)
                    try:
                        res = await agent.call(prompt, fallback_meta=fallback_meta)
                    except CircuitBreakerOpenError:
                        logging.warning("Circuit Breaker da IA aberto! Usando meta local instantaneo.")
                        res = {"comp": fallback_meta.get("name", "")}
                    except Exception as e:
                        logging.exception(f"Erro inesperado na IA: {e}")
                        res = {"comp": fallback_meta.get("name", "")}

                    print(f"[DEBUG AI] comp retornado: {res.get('comp')}")
                    print(f"[DEBUG AI] units retornados: {res.get('units')}")

                    ai_comp_name = res.get("comp", "")
                    meta_info = meta.get_comp_info(ai_comp_name)
                    print(f"[DEBUG] meta_info para '{ai_comp_name}': {meta_info}")

                    if not meta_info or not meta_info.get("units"):
                        logging.warning(f"Comp '{ai_comp_name}' nao encontrado no meta. Usando fallback.")
                        top_comps = meta.get_top_comps()
                        if top_comps:
                            meta_info = top_comps[0]
                            res["comp"] = meta_info.get("name", "Meta Padrao")
                            raw_units = meta_info.get("units", [])
                            res["units"] = [pt(u) for u in raw_units]
                            res["core_items"] = _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in meta_info.get("core_items", {}).items()})
                            res["posicionamento"] = meta_info.get("positioning", "")
                            res["tanks"] = [pt(t) for t in meta_info.get("tanks", [])]
                            res["levels"] = meta_info.get("levels", "")
                            res["dicas"] = meta_info.get("dicas", "")
                            print(f"[DEBUG] Fallback usando: {res['comp']} com {len(res['units'])} units: {res['units']}")
                        else:
                            logging.error("Sem comps disponiveis no meta!")
                            res["status"] = "Sem comps disponiveis para seu rank"
                            continue

                    if not res.get("units"):
                        res["units"] = [pt(u) for u in meta_info.get("units", [])]
                    if not res.get("core_items"):
                        raw_items = {pt(k): [pt_item(i) for i in v] for k, v in meta_info.get("core_items", {}).items()}
                        res["core_items"] = _format_items_with_global_priority(raw_items)
                    if not res.get("posicionamento"):
                        res["posicionamento"] = meta_info.get("positioning", "")
                    if not res.get("tanks"):
                        res["tanks"] = [pt(t) for t in meta_info.get("tanks", [])]
                    if not res.get("levels"):
                        res["levels"] = meta_info.get("levels", "")
                    if not res.get("dicas"):
                        res["dicas"] = meta_info.get("dicas", "")
                    if "viabilidade" not in res:
                        res["viabilidade"] = 70
                    if "augments" in res:
                        raw = res["augments"]
                        if isinstance(raw, list):
                            res["augments"] = ", ".join([pt_augment(a) for a in raw])
                        elif isinstance(raw, str):
                            res["augments"] = ", ".join([pt_augment(a.strip()) for a in raw.split(",")])
                    meta_augs = meta_info.get("augments", [])
                    if isinstance(meta_augs, list) and meta_augs:
                        reg_norm = [normalize_augment(a) for a in session.registered_augments]
                        next_augs = [pt_augment(a) for a in meta_augs if a not in reg_norm]
                        res["next_augments"] = next_augs
                    else:
                        res["next_augments"] = []
                    res["comp_win_rate"] = meta_info.get("win_rate", "")
                    res["comp_avg_placement"] = meta_info.get("avg_placement", "")
                    res["comp_games"] = meta_info.get("games", "")
                    res["import_code"] = await asyncio.to_thread(get_team_import_code, res["units"], session.creds)
                    res["opponents"] = opp_list or [{"name": "Carregando...", "rank": "", "avg": ""}]
                    res["next_opponent"] = next_opp_name or ""
                    res["game_id"] = game_id
                    res["prompt"] = prompt
                    alt = []
                    for c in meta.get_top_comps():
                        if c.get("name") != res.get("comp", ""):
                            alt.append({
                                "name": c.get("name", ""),
                                "tier": c.get("tier", ""),
                                "win_rate": c.get("win_rate", ""),
                                "units": [pt(u) for u in c.get("units", [])],
                                "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in c.get("core_items", {}).items()}),
                                "posicionamento": c.get("positioning", ""),
                                "tanks": [pt(t) for t in c.get("tanks", [])],
                                "levels": c.get("levels", ""),
                                "dicas": c.get("dicas", ""),
                            })
                        if len(alt) >= 3: break
                    res["alt_comps"] = alt

                    suggested_units = set([pt(u) for u in meta_info.get("units", [])])
                    contest_count = 0
                    contesting_players = []
                    for opp_name, opp_data in opponent_analysis.items():
                        opp_board = set([pt(u) for u in (opp_data.get("recent_units", []))])
                        overlap = suggested_units & opp_board
                        if len(overlap) >= 3:
                            contest_count += 1
                            contesting_players.append(opp_name)

                    if contest_count >= 2:
                        res["contest_risk"] = "ALTA"
                        res["contest_warning"] = f"\U0001f534 {contest_count} jogadores com comp similar: {', '.join(contesting_players)}"
                    elif contest_count == 1:
                        res["contest_risk"] = "MEDIA"
                        res["contest_warning"] = f"\U0001f7e1 1 jogador com comp similar: {', '.join(contesting_players)}"
                    else:
                        res["contest_risk"] = "BAIXA"
                        res["contest_warning"] = "\U0001f7e2 Nenhum jogador contestando"

                    try:
                        ev_result = calculate_ev_decision(
                            current_level=game_state.level,
                            gold=game_state.gold,
                            hp=getattr(game_state, 'hp', None),
                            stage=game_state.stage,
                            board=game_state.my_board,
                            suggested_comp_units=res.get("units", []),
                            opponent_boards=[o.get("board", []) for o in opp_list]
                        )
                        res["ev_decision"] = format_ev_display(ev_result)
                        res["ev_tag"] = get_quick_tag(game_state.level, game_state.gold, getattr(game_state, 'hp', 100))
                    except Exception as e:
                        logging.error(f"Erro no EV Calculator: {e}")
                        res["ev_decision"] = {"tag": "\u2753", "recommendation": "Erro no calculo"}
                        res["ev_tag"] = "\u26aa"

                    try:
                        items_in_hand = []
                        slam_rec = get_slam_recommendation(game_state.stage, items_in_hand, game_state.my_board)
                        res["item_slam"] = slam_rec
                    except Exception as e:
                        logging.error(f"Erro no Transition Advisor: {e}")
                        res["item_slam"] = {"recommendation": ""}

                    try:
                        aug_analysis = analyze_augment_set(session.registered_augments, game_state.stage, [], [])
                        res["augment_synergy"] = format_analysis_display(aug_analysis)
                    except Exception as e:
                        logging.error(f"Erro no Augment Synergy: {e}")
                        res["augment_synergy"] = {"overall_badge": "\u26aa", "overall_score": "0%"}

                    try:
                        res["ghost_opponents"] = format_ghost_display(ghost_pool)
                    except Exception as e:
                        logging.error(f"Erro no Ghost Matchups display: {e}")
                        res["ghost_opponents"] = []

                    res["spike_status"] = spike_status

                    try:
                        if carousel_predictor.should_predict(game_state.stage, phase):
                            carousel_pred = predict_carousel(
                                stage=game_state.stage,
                                comp=res.get("comp", ""),
                                items=res.get("core_items", {}),
                                board=game_state.my_board,
                                missing=[],
                                opponent_items={}
                            )
                            res["carousel_prediction"] = carousel_pred
                    except Exception as e:
                        logging.error(f"Erro no Carousel Predictor: {e}")
                        res["carousel_prediction"] = None

                    contest_data = {}
                    try:
                        opp_boards_raw = [o.get("board", []) for o in opp_list]
                        contest_data = calc_contest_score(
                            suggested_units=res.get("units", []),
                            opponent_boards=opp_boards_raw,
                            tanks=res.get("tanks", []),
                            core_items=res.get("core_items", {})
                        )
                    except Exception as e:
                        logging.error(f"Erro no Contest Data: {e}")
                        contest_data = {}

                    try:
                        lobby_press = calc_lobby_pressure(
                            stage=game_state.stage,
                            opponent_boards=[{"board": o.get("board", [])} for o in opp_list],
                            spike_status=res.get("spike_status", []),
                            contest_score=contest_data.get("score_total", 0)
                        )
                        res["lobby_pressure"] = lobby_press
                    except Exception as e:
                        logging.error(f"Erro no Lobby Pressure: {e}")
                        res["lobby_pressure"] = {"score": 0, "tier": "BAIXA", "label": "Lobby Aberto", "color": "green"}

                    try:
                        top4 = calc_top4_pressure(
                            hp=getattr(game_state, 'hp', 100) or 100,
                            gold=game_state.gold,
                            level=game_state.level,
                            stage=game_state.stage,
                            lobby_pressure_score=res.get("lobby_pressure", {}).get("score", 0),
                            streak=getattr(game_state, 'streak', 0)
                        )
                        res["top4_score"] = top4
                    except Exception as e:
                        logging.error(f"Erro no Top 4 Score: {e}")
                        res["top4_score"] = {"score": 0, "tier": "BAIXA", "label": "<40% Top 4", "color": "red"}

                    try:
                        zone_risks = calc_zone_risks(
                            ghost_pool,
                            [{"board": o.get("board", []), "traits": o.get("traits", [])} for o in opp_list]
                        )
                        res["zone_risks"] = zone_risks
                    except Exception as e:
                        logging.error(f"Erro no Zone Risk Map: {e}")
                        res["zone_risks"] = []

                    try:
                        micro_dec = decide_micro_action(
                            ev_result=ev_result,
                            slam_rec=slam_rec,
                            augment_analysis=aug_analysis,
                            contest_score=contest_data.get("score_total", 0),
                            stage=game_state.stage,
                            hp=getattr(game_state, 'hp', 100) or 100
                        )
                        res["micro_decision"] = micro_dec
                    except Exception as e:
                        logging.error(f"Erro no Micro Decision Engine: {e}")
                        res["micro_decision"] = {"action": "AGUARDAR", "priority": "LOW", "reason": "Erro no modulo"}

                    res["registered_augments"] = session.registered_augments.copy()

                    _inject_context(res, mem)
                    q.put(res)
                    set_web_state(res)
                    session.last_suggestion = res
                    session.last_comp_used = res.get("comp", "")
                    session.analyzed_game_id = game_id
                    _status("Sugestao pronta! Boa partida.")
                else:
                    now = time.time()
                    if now - session.last_fallback_time < 30:
                        logging.info(f"Fallback ja enviado ha {now-session.last_fallback_time:.0f}s, pulando.")
                        await asyncio.sleep(3)
                        continue
                    session.last_fallback_time = now
                    logging.info("Sem analise de IA. Mostrando sugestao padrao com oponentes.")
                    top_comps = meta.get_top_comps()
                    if session.registered_augments:
                        reg_norm = [normalize_augment(a) for a in session.registered_augments if a]
                        scored = []
                        for c in top_comps:
                            comp_augs = c.get("augments", [])
                            matches = sum(1 for a in reg_norm if a in comp_augs)
                            if matches > 0:
                                wr = c.get("win_rate", "0")
                                try:
                                    wr = float(str(wr).replace("%",""))
                                except (ValueError, TypeError):
                                    wr = 0
                                scored.append((matches, wr, c))
                        if scored:
                            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                            meta_info = scored[0][2]
                        else:
                            meta_info = top_comps[0] if top_comps else {}
                    else:
                        meta_info = top_comps[0] if top_comps else {}
                    fb_alt = []
                    if session.registered_augments and scored:
                        for _, _, c in scored[:4]:
                            if c.get("name") != meta_info.get("name", ""):
                                fb_alt.append({
                                    "name": c.get("name",""), "tier": c.get("tier",""),
                                    "win_rate": c.get("win_rate",""),
                                    "units": [pt(u) for u in c.get("units",[])],
                                    "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in c.get("core_items",{}).items()}),
                                    "posicionamento": c.get("positioning",""), "tanks": [pt(t) for t in c.get("tanks",[])],
                                    "levels": c.get("levels",""), "dicas": c.get("dicas",""),
                                })
                                if len(fb_alt) >= 3: break
                    if len(fb_alt) < 3:
                        for c in top_comps:
                            if c.get("name") != meta_info.get("name","") and c.get("name") not in [a["name"] for a in fb_alt]:
                                fb_alt.append({
                                    "name": c.get("name",""), "tier": c.get("tier",""),
                                    "win_rate": c.get("win_rate",""),
                                    "units": [pt(u) for u in c.get("units",[])],
                                    "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in c.get("core_items",{}).items()}),
                                    "posicionamento": c.get("positioning",""), "tanks": [pt(t) for t in c.get("tanks",[])],
                                    "levels": c.get("levels",""), "dicas": c.get("dicas",""),
                                })
                                if len(fb_alt) >= 3: break
                    meta_info = meta_info or {}
                    fb_units = [pt(u) for u in meta_info.get("units", [])]
                    fallback = {
                        **meta_info,
                        "comp": meta_info.get("name", "Meta Padrao"),
                        "units": fb_units,
                        "core_items": _format_items_with_global_priority({pt(k): [pt_item(i) for i in v] for k, v in meta_info.get("core_items", {}).items()}),
                        "posicionamento": meta_info.get("positioning", ""),
                        "tanks": [pt(t) for t in meta_info.get("tanks", [])],
                        "levels": meta_info.get("levels", ""),
                        "dicas": meta_info.get("dicas", ""),
                        "viabilidade": 70,
                        "next_augments": [],
                        "augments": "",
                        "registered_augments": session.registered_augments.copy(),
                        "comp_win_rate": meta_info.get("win_rate", ""),
                        "comp_avg_placement": meta_info.get("avg_placement", ""),
                        "comp_games": meta_info.get("games", ""),
                        "import_code": await asyncio.to_thread(get_team_import_code, fb_units, session.creds) if session.creds else "",
                        "opponents": opp_list or [{"name": "Carregando...", "rank": "", "avg": ""}],
                        "next_opponent": next_opp_name or "",
                        "game_id": game_id,
                        "prompt": "(Fallback: compoicao auto-selecionada sem analise de IA)",
                        "alt_comps": fb_alt,
                    }
                    _inject_context(fallback, mem)
                    q.put(fallback)
                    set_web_state(fallback)
                    session.last_suggestion = fallback
                    session.last_comp_used = fallback.get("comp", "")
                    _status(f"Sugestao pronta (fallback)! {len(opp_names)} oponentes.")

            if session.last_phase == GamePhase.IN_PROGRESS and phase in GAME_PHASES_ENDED.union({GamePhase.LOBBY}):
                if session.match_state != MatchState.ENDED:
                    session.match_state = MatchState.ENDING
                    placement, won = 8, False
                    try:
                        port_eog, pwd_eog = session.creds
                        auth_eog = base64.b64encode(f'riot:{pwd_eog}'.encode()).decode()
                        headers_eog = {"Authorization": f"Basic {auth_eog}"}
                        def _fetch_eog():
                            return requests.get(f"https://127.0.0.1:{port_eog}/lol-end-of-game/v1/eog-stats-block",
                                               headers=headers_eog, verify=False, timeout=5).json()
                        eog = await asyncio.to_thread(_fetch_eog)
                        placement = eog.get("myTeamStatus", {}).get("placement", 8)
                        won = placement <= 4
                        logging.info(f"Fim de partida! Colocacao: {placement} ({'Vitoria' if won else 'Derrota'})")
                    except Exception as e:
                        logging.warning(f"Falha ao ler EOG stats: {e}")

                    comp_name = session.last_suggestion.get("comp", "Desconhecida")
                    log_data = {
                        "ts": datetime.now().isoformat(),
                        "comp": comp_name,
                        "placement": placement,
                        "won": won,
                        "followed": True,
                        "rating": 5 if won else 1,
                        "traits": "[]",
                        "stage": "Post",
                        "gold": 0,
                        "level": 0,
                        "opponents": ",".join([o.get("name","") for o in session.last_suggestion.get("opponents", []) if isinstance(o, dict)]),
                    }
                    mem.log_match(log_data)
                    logging.info(f"Partida salva no banco: {comp_name} -> {placement} lugar")

                    q.put({"status": f"end_of_game", "placement": placement, "comp": comp_name}); update_web_status("end_of_game")

                    session.analyzed_game_id = None
                    _opponent_cache.clear()
                    await asyncio.to_thread(_save_opponent_state)
                    session.match_state = MatchState.ENDED
                    spike_detector.clear_spikes()
                    ghost_tracker.clear_history()

                await asyncio.sleep(10)
                continue

            if phase not in ("InProgress", "WaitingForStats", "EndOfGame", "Terminated"):
                session.match_state = MatchState.IDLE

            current_stage = (sess.get("gameData") or {}).get("gameStage", "Unknown")
            stage_changed = current_stage != session.last_stage
            if stage_changed:
                session.last_stage = current_stage
                logging.info(f"Stage mudou para {current_stage}")

            player_data = (sess.get("gameData") or {}).get("playerData") or {}
            my_hp = int(player_data.get("health", 100))

            if phase == "InProgress":
                if stage_changed:
                    delay = 2
                elif my_hp <= 20:
                    delay = 2
                elif my_hp <= 30:
                    delay = 4
                elif my_hp <= 50:
                    delay = 6
                else:
                    delay = 8
            elif phase in ("ChampSelect", "GameStart"):
                delay = 3
            else:
                delay = 12

            jitter = random.uniform(0.2, 0.8)
            delay += jitter

            _status(f"Jogo em andamento ({current_stage})")
            await asyncio.sleep(delay)

        except Exception as e:
            log_critical_error("GameLoop", e, "Loop principal")
            await asyncio.sleep(5)
