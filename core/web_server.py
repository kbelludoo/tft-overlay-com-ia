"""Servidor HTTP + WebSocket para overlay-hud.html e estado via JSON"""
import json, logging, threading, urllib.parse, mimetypes, asyncio, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

HUD_HTML = Path(__file__).parent.parent / "overlay-hud.html"
INDEX_HTML = Path(__file__).parent.parent / "index.html"
IMG_DIR = Path(__file__).parent.parent / "data" / "images"

_state = {}
_state_lock = threading.Lock()
_cmd_queue = None
_ws_clients = set()
_last_reanalyze = 0
REANALYZE_COOLDOWN = 5


def _normalize(data: dict) -> dict:
    out = {}
    out["status"] = data.get("status", "")
    out["stage"] = data.get("stage", "")
    out["level"] = data.get("level", "") if data.get("level") is not None else (
        data.get("nivel", "")
    )
    out["gold"] = data.get("gold", "") if data.get("gold") is not None else ""
    out["import_code"] = data.get("import_code", "")

    comp_name = data.get("comp", "")
    if isinstance(comp_name, str):
        clean = comp_name
        for pfx in ["[META] ", "[META]"]:
            if clean.startswith(pfx):
                clean = clean[len(pfx):]
        idx = clean.find(" (Tier ")
        if idx > 0:
            clean = clean[:idx]
        idx = clean.find(" - Rank:")
        if idx > 0:
            clean = clean[:idx]
        out["comp"] = {"name": clean.strip() or comp_name}
    elif isinstance(comp_name, dict):
        out["comp"] = dict(comp_name)
    else:
        out["comp"] = {"name": str(comp_name)}

    for k, wk in [("win_rate", "comp_win_rate"), ("avg_placement", "comp_avg_placement"), ("games", "comp_games")]:
        v = data.get(wk) or data.get(k)
        if v is not None and v != "":
            try:
                out["comp"][k] = float(v) if "." in str(v) else int(v)
            except (ValueError, TypeError):
                out["comp"][k] = v

    viab = data.get("viabilidade")
    if viab is not None:
        try:
            out["comp"]["viability"] = int(viab)
        except (ValueError, TypeError):
            pass
    contest = data.get("contest_risk")
    if contest == "ALTA":
        out["comp"]["contest"] = 4
    elif contest == "MEDIA":
        out["comp"]["contest"] = 2
    elif contest == "BAIXA":
        out["comp"]["contest"] = 0

    raw_units = data.get("units", [])
    core_items = data.get("core_items", {}) or {}
    tanks = data.get("tanks", []) or []
    if isinstance(tanks, str):
        tanks = [t.strip() for t in tanks.split(",") if t.strip()]
    units_out = []
    for u in raw_units:
        name = str(u)
        items = core_items.get(name, [])
        if isinstance(items, str):
            items = [i.strip() for i in items.split(",") if i.strip()]
        units_out.append({
            "name": name,
            "items": items,
            "tank": name in tanks
        })
    out["comp"]["units"] = units_out

    augs_raw = data.get("augments", [])
    if isinstance(augs_raw, str):
        augs_raw = [a.strip() for a in augs_raw.replace(":", ",").split(",") if a.strip()]
    out["comp"]["augments"] = augs_raw if isinstance(augs_raw, list) else []

    out["registered_augments"] = data.get("registered_augments", [])
    out["next_augments"] = data.get("next_augments", [])

    alt = data.get("alt_comps", [])
    if isinstance(alt, list):
        out["alternative_comps"] = []
        for a in alt:
            entry = {
                "name": a.get("name", ""),
                "tier": a.get("tier", ""),
                "units": [],
                "augments": [],
                "positioning": "",
                "levels": "",
                "dicas": "",
                "tanks": [],
            }
            raw_units = a.get("units", [])
            alt_items = a.get("core_items", {}) or {}
            alt_tanks = a.get("tanks", []) or []
            if isinstance(alt_tanks, str):
                alt_tanks = [t.strip() for t in alt_tanks.split(",") if t.strip()]
            units_out = []
            for u in raw_units:
                uname = str(u)
                items = alt_items.get(uname, alt_items.get(u, []))
                if isinstance(items, str):
                    items = [i.strip() for i in items.split(",") if i.strip()]
                units_out.append({
                    "name": uname,
                    "items": items if isinstance(items, list) else [],
                    "tank": uname in alt_tanks or u in alt_tanks
                })
            entry["units"] = units_out
            raw_augs = a.get("augments", [])
            if isinstance(raw_augs, str):
                raw_augs = [x.strip() for x in raw_augs.replace(":", ",").split(",") if x.strip()]
            entry["augments"] = raw_augs if isinstance(raw_augs, list) else []
            entry["positioning"] = a.get("posicionamento", a.get("positioning", ""))
            entry["levels"] = a.get("levels", "")
            entry["dicas"] = a.get("dicas", "")
            entry["porque"] = a.get("porque", "")
            entry["como"] = a.get("como", "")
            entry["tanks"] = [str(t) for t in alt_tanks]
            wr = a.get("win_rate") or a.get("comp_win_rate", "")
            if wr:
                try:
                    entry["win_rate"] = float(wr) if "." in str(wr) else int(wr)
                except (ValueError, TypeError):
                    entry["win_rate"] = wr
            out["alternative_comps"].append(entry)
    else:
        out["alternative_comps"] = []

    opps = data.get("opponents", [])
    out["opponents"] = []
    for o in (opps or []):
        if isinstance(o, dict):
            out["opponents"].append({
                "name": o.get("name", ""),
                "rank": o.get("rank", ""),
                "avg": o.get("avg", ""),
                "recent_comps": o.get("recent_comps", []),
                "state": o.get("state", 0)
            })
        elif isinstance(o, str):
            out["opponents"].append({"name": o, "rank": "", "avg": "", "recent_comps": [], "state": 0})

    next_opp = data.get("next_opponent", "")
    out["next_opponent"] = next_opp

    guides = {}
    tab_keys = {"posicionamento": "pos", "levels": "levels", "dicas": "dicas", "contra": "contra"}
    for src_k, dst_k in tab_keys.items():
        v = data.get(src_k, "")
        if v:
            guides[dst_k] = v
    oponentes_contra = data.get("oponentes_contra", "")
    if not guides.get("contra") and oponentes_contra:
        guides["contra"] = oponentes_contra
    motivo = data.get("motivo", "")
    if motivo:
        guides["summary"] = motivo
    prompt = data.get("prompt", "")
    if not guides.get("summary") and prompt:
        guides["summary"] = prompt
    guides["porque"] = data.get("porque", "")
    guides["como"] = data.get("como", "")
    out["guides"] = guides
    out["prompt"] = data.get("prompt", "")

    ctx = data.get("context") or {}
    out["match_history"] = {
        "recent": ctx.get("recent", []) if isinstance(ctx.get("recent"), list) else [],
        "win_rate": ctx.get("win_rate", 0),
        "total": ctx.get("total", 0),
        "overlay_win_rate": ctx.get("overlay_win_rate", 0),
        "overlay_total": ctx.get("overlay_total", 0)
    }

    out["overlay_win_rate"] = data.get("overlay_win_rate", 0)
    out["overlay_total"] = data.get("overlay_total", 0)
    out["account_win_rate"] = data.get("account_win_rate", 0)
    out["account_total"] = data.get("account_total", 0)

    for k in list(out.keys()):
        if out[k] is None:
            out[k] = "" if isinstance(out[k], str) else ([] if isinstance(out[k], list) else {})

    return out


def set_state(data: dict):
    with _state_lock:
        _state.clear()
        _state.update(_normalize(data))
    _broadcast_ws()


def update_status(msg: str):
    with _state_lock:
        _state["status"] = msg
    _broadcast_ws()


def get_state() -> dict:
    with _state_lock:
        return dict(_state)


def _get_all_comps() -> dict:
    try:
        from core.meta_db import MetaDB
        from core.data import pt, pt_item, pt_augment
        mdb = MetaDB()
        top = mdb.get_top_comps()
        comps = []
        for c in top:
            units = c.get("units", [])
            core_items = c.get("core_items", {}) or {}
            tanks = c.get("tanks", []) or []
            if isinstance(tanks, str):
                tanks = [t.strip() for t in tanks.split(",") if t.strip()]
            units_out = []
            for u in units:
                name = pt(u)
                items = core_items.get(u, core_items.get(name, []))
                if isinstance(items, str):
                    items = [i.strip() for i in items.split(",") if i.strip()]
                items = [pt_item(i) for i in (items or [])]
                units_out.append({"name": name, "items": items, "tank": u in tanks or name in tanks})
            raw_augs = c.get("augments", [])
            if isinstance(raw_augs, str):
                raw_augs = [a.strip() for a in raw_augs.split(",") if a.strip()]
            augs = [pt_augment(a) for a in raw_augs]
            comps.append({
                "name": c.get("name", ""),
                "tier": c.get("tier", ""),
                "win_rate": c.get("win_rate", ""),
                "avg_placement": c.get("avg_placement", ""),
                "games": c.get("games", ""),
                "units": units_out,
                "augments": augs,
                "positioning": c.get("positioning", ""),
                "levels": c.get("levels", ""),
                "dicas": c.get("dicas", ""),
                "tanks": [pt(t) for t in tanks],
            })
        return {"comps": comps}
    except Exception as e:
        logging.warning(f"Erro ao buscar comps: {e}")
        return {"comps": []}


def set_cmd_queue(q):
    global _cmd_queue
    _cmd_queue = q


def _broadcast_ws():
    if not HAS_WEBSOCKETS or not _ws_clients:
        return
    try:
        with _state_lock:
            msg = json.dumps(_state, ensure_ascii=False, default=str)
        dead = set()
        for ws in list(_ws_clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send(msg), _ws_loop)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)
    except Exception as e:
        logging.debug(f"WS broadcast error: {e}")


_ws_loop = None


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    try:
        with _state_lock:
            initial = json.dumps(_state, ensure_ascii=False, default=str)
        await websocket.send(initial)
        async for message in websocket:
            pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)


async def _ws_server(port: int):
    global _ws_loop
    _ws_loop = asyncio.get_event_loop()
    async with websockets.serve(_ws_handler, "127.0.0.1", port + 1):
        await asyncio.Future()


def _start_ws(port: int):
    if not HAS_WEBSOCKETS:
        logging.info("websockets nao instalado. Usando polling HTTP.")
        return
    try:
        def _run():
            asyncio.run(_ws_server(port))
        t = threading.Thread(target=_run, daemon=True, name="ws-server")
        t.start()
        logging.info(f"WebSocket ativo em ws://127.0.0.1:{port + 1}")
    except Exception as e:
        logging.warning(f"Falha ao iniciar WebSocket: {e}. Usando polling.")


def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.debug(f"[web] {fmt % args}")

        def _send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path, status=200):
            try:
                body = path.read_bytes()
                mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self._send_json({"error": "not found"}, 404)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            params = dict(urllib.parse.parse_qsl(parsed.query))

            if path == "/api/state":
                self._send_json(get_state())
            elif path == "/api/comps":
                self._send_json(_get_all_comps())
            elif path == "/api/reanalyze":
                global _last_reanalyze
                now = time.time()
                if now - _last_reanalyze < REANALYZE_COOLDOWN:
                    self._send_json({"message": f"Aguarde {REANALYZE_COOLDOWN}s entre reanalises", "cooldown": True})
                    return
                _last_reanalyze = now
                cmd = {"action": "reanalyze"}
                aug = params.get("augment", "").strip()
                if aug:
                    cmd["manual_augment"] = aug
                if _cmd_queue is not None:
                    _cmd_queue.put(cmd)
                self._send_json({"message": "Reanalise solicitada"})
            elif path == "/api/mappings":
                from core.data import CHAMP_TFTACADEMY, ITEM_TFTACADEMY
                self._send_json({
                    "champions": CHAMP_TFTACADEMY,
                    "items": ITEM_TFTACADEMY
                })
            elif path == "/" or path == "/hud" or path == "/overlay-hud.html":
                self._send_file(HUD_HTML)
            elif path == "/index.html" or path == "/launcher":
                if INDEX_HTML.exists():
                    self._send_file(INDEX_HTML)
                else:
                    self._send_file(HUD_HTML)
            elif path.startswith("/images/"):
                filename = Path(path).name
                if filename:
                    filepath = IMG_DIR / filename
                    self._send_file(filepath)
            else:
                self._send_json({"error": "not found"}, 404)

    return Handler


def start_server(port: int = 8765) -> int:
    handler = _make_handler()
    try:
        server = HTTPServer(("127.0.0.1", port), handler)
    except OSError:
        for p in range(port + 1, port + 100):
            try:
                server = HTTPServer(("127.0.0.1", p), handler)
                port = p
                break
            except OSError:
                continue
    set_state({"status": "Inicializando..."})
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="web-server")
    thread.start()
    logging.info(f"Web UI em http://127.0.0.1:{port}")
    _start_ws(port)
    return port
