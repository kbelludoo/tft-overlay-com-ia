import sqlite3, json, logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).parent.parent

SCHEMA_VERSION = 2


class MemoryDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(PROJECT_DIR / "data" / "memory.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.path = db_path
        self._write_count = 0
        self._conn = None
        self._init()
        self._migrate()
        logging.info("MemoryDB initialized (WAL mode, thread-safe, schema v%s)", SCHEMA_VERSION)

    def _get_conn(self):
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.path, timeout=10.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def _migrate(self):
        """Schema versioning: roda migracoes conforme PRAGMA user_version."""
        conn = self._get_conn()
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS matches (
                        id INTEGER PRIMARY KEY, ts TEXT, patch TEXT, stage TEXT, gold INTEGER, level INTEGER,
                        comp TEXT, traits TEXT, followed INTEGER, rating INTEGER, placement INTEGER, won INTEGER,
                        opponents TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS patterns (
                        key TEXT PRIMARY KEY, comp TEXT, traits TEXT, stage TEXT, success REAL, trials INTEGER, last TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_recent ON matches(id DESC)")
                conn.execute("PRAGMA user_version = 1")
                logging.info("MemoryDB: migrated to v1 (base tables)")
            if version < 2:
                try:
                    conn.execute("ALTER TABLE matches ADD COLUMN opponents TEXT DEFAULT ''")
                except Exception:
                    pass
                conn.execute("PRAGMA user_version = 2")
                logging.info("MemoryDB: migrated to v2 (opponents column)")
            conn.commit()
        except Exception as e:
            logging.warning(f"MemoryDB migration error: {e}")
        finally:
            if version is None:
                pass

    def _init(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY, ts TEXT, patch TEXT, stage TEXT, gold INTEGER, level INTEGER,
                    comp TEXT, traits TEXT, followed INTEGER, rating INTEGER, placement INTEGER, won INTEGER,
                    opponents TEXT
                );
                CREATE TABLE IF NOT EXISTS patterns (
                    key TEXT PRIMARY KEY, comp TEXT, traits TEXT, stage TEXT, success REAL, trials INTEGER, last TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_matches_recent ON matches(id DESC);
            """)
            try:
                conn.execute("ALTER TABLE matches ADD COLUMN opponents TEXT DEFAULT ''")
            except Exception:
                pass
            conn.commit()
        finally:
            self._prune_if_needed(conn)

    def _prune_if_needed(self, conn=None):
        should_close = conn is None
        if conn is None:
            conn = self._get_conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            if count > 500:
                conn.execute("DELETE FROM matches WHERE id < (SELECT MAX(id) FROM matches) - 500")
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def _prune(self):
        self._prune_if_needed()

    def log_match(self, d: Dict):
        for attempt in range(3):
            try:
                conn = self._get_conn()
                conn.execute("INSERT INTO matches VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    d.get("ts"), d.get("patch","?"), d.get("stage","?"), d.get("gold",0), d.get("level",1),
                    d.get("comp",""), d.get("traits","[]"), int(d.get("followed",False)),
                    d.get("rating",0), d.get("placement",8), int(d.get("won",False)),
                    d.get("opponents","")
                ))
                try: traits_list = json.loads(d.get("traits", "[]"))
                except (json.JSONDecodeError, TypeError): traits_list = []
                
                traits = ",".join(sorted(traits_list[:3]))
                key = f"{d.get('stage','?')}|{traits}|{d.get('comp','')}"
                conn.execute("""INSERT INTO patterns VALUES (?,?,?,?,?,1,?)
                             ON CONFLICT(key) DO UPDATE SET trials=trials+1, success=(success*trials+?)/(trials+1), last=?""",
                          (key, d.get("comp",""), traits, d.get("stage","?"), float(d.get("won",False)), d.get("ts"),
                           float(d.get("won",False)), d.get("ts")))
                conn.commit()
                
                self._write_count += 1
                if self._write_count % 10 == 0:
                    self._prune()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 2:
                    import time
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                logging.warning(f"MemoryDB write error (try {attempt+1}): {e}")
            except Exception as e:
                logging.error(f"MemoryDB critical error: {e}")
                break

    def get_context(self) -> Dict:
        conn = self._get_conn()
        cur = conn.execute("SELECT COUNT(*), AVG(won), AVG(followed), AVG(rating) FROM matches")
        s = cur.fetchone()
        top = conn.execute("SELECT comp, COUNT(*) as t, AVG(won) as w FROM matches WHERE followed=1 AND comp!='' GROUP BY comp ORDER BY w DESC, t DESC LIMIT 3").fetchall()
        avoid = conn.execute("SELECT comp FROM matches WHERE followed=1 AND comp!='' GROUP BY comp ORDER BY AVG(won) ASC, COUNT(*) DESC LIMIT 2").fetchall()

        followed_cur = conn.execute("SELECT COUNT(*), AVG(won) FROM matches WHERE followed=1")
        f = followed_cur.fetchone()

        recent = conn.execute("SELECT won FROM matches ORDER BY id DESC LIMIT 10").fetchall()

        return {
            "total": s[0] or 0, "win_rate": round((s[1] or 0)*100),
            "follow_rate": round((s[2] or 0)*100), "avg_rating": round(s[3] or 0, 1),
            "overlay_total": f[0] or 0, "overlay_win_rate": round((f[1] or 0)*100),
            "top_comps": [{"comp": r[0], "t": r[1], "w": round(r[2]*100)} for r in top],
            "avoid_comps": [r[0] for r in avoid],
            "recent": ["win" if r[0] else "loss" for r in recent]
        }

    def get_cached_pattern(self, stage: str, traits: List[str]) -> Optional[Dict]:
        t = ",".join(sorted(traits[:3]))
        conn = self._get_conn()
        r = conn.execute("SELECT comp, success, trials FROM patterns WHERE key LIKE ? AND trials>=? AND success>0.6 ORDER BY success DESC LIMIT 1", (f"{stage}|{t}%", 3)).fetchone()
        return {"comp": r[0], "success": r[1], "trials": r[2]} if r else None

    def get_recent_matches(self, limit: int = 10) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT comp, placement, won, opponents FROM matches ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"comp": r[0], "placement": r[1], "won": bool(r[2]), "opponents": r[3]} for r in rows]
    
    def export_csv(self, filepath: str) -> bool:
        import csv
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT ts, patch, stage, gold, level, comp, traits, followed, rating, placement, won, opponents 
                FROM matches ORDER BY id DESC
            """).fetchall()
            
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Patch", "Stage", "Gold", "Level", "Comp", "Traits", "Followed", "Rating", "Placement", "Won", "Opponents"])
                for r in rows:
                    writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]])
            
            logging.info(f"Historico exportado para CSV: {filepath} ({len(rows)} partidas)")
            return True
        except Exception as e:
            logging.error(f"Erro ao exportar CSV: {e}")
            return False
    
    def export_json(self, filepath: str) -> bool:
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT ts, patch, stage, gold, level, comp, traits, followed, rating, placement, won, opponents 
                FROM matches ORDER BY id DESC
            """).fetchall()
            
            matches = []
            for r in rows:
                matches.append({
                    "timestamp": r[0], "patch": r[1], "stage": r[2], "gold": r[3], "level": r[4],
                    "comp": r[5], "traits": r[6], "followed": bool(r[7]), "rating": r[8],
                    "placement": r[9], "won": bool(r[10]), "opponents": r[11]
                })
            
            export_data = {
                "exported_at": datetime.now().isoformat(),
                "total_matches": len(matches),
                "matches": matches
            }
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logging.info(f"Historico exportado para JSON: {filepath} ({len(matches)} partidas)")
            return True
        except Exception as e:
            logging.error(f"Erro ao exportar JSON: {e}")
            return False
