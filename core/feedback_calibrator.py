"""
Loop de Feedback do Usuário (Calibração Local).

Usa EMA (Exponential Moving Average) com mínima amostragem
para evitar viés de resultado curto (Top 8 por RNG ruim).

Funcões:
- log_feedback() — registra feedback do usuário
- get_comp_effectiveness() — retorna win rate suavizado da comp
- get_calibration_summary() — resumo da calibração local
- inject_calibration() — injeta dados no prompt da IA
"""
import sqlite3, json, logging, time
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
FEEDBACK_DB = DATA_DIR / "feedback.db"

# Configurações
MIN_SAMPLE = 3            # Mínimo de jogos antes de penalizar
EMA_ALPHA = 0.3           # Fator de suavização (0.1 = lento, 0.5 = rápido)
MAX_HISTORY = 50          # Máximo de registros por comp


class FeedbackCalibrator:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(FEEDBACK_DB), timeout=5.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                comp_name TEXT,
                user_followed INTEGER,
                placement INTEGER,
                won INTEGER,
                stage TEXT,
                gold INTEGER,
                level INTEGER,
                confidence INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comp_stats (
                comp_name TEXT PRIMARY KEY,
                ema_wr REAL DEFAULT 0.5,
                total_games INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                last_updated TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log_feedback(self, comp_name: str, followed: bool, placement: int,
                     won: bool, stage: str = "", gold: int = 0,
                     level: int = 0, confidence: int = 0):
        """Registra feedback do usuário"""
        conn = sqlite3.connect(str(FEEDBACK_DB), timeout=5.0)
        try:
            conn.execute(
                """INSERT INTO feedback (ts, comp_name, user_followed, placement, won,
                   stage, gold, level, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now().isoformat(), comp_name, int(followed),
                 placement, int(won), stage, gold, level, confidence)
            )
            conn.commit()
            self._update_ema(conn, comp_name, won)
        except Exception as e:
            logging.error(f"Erro ao salvar feedback: {e}")
        finally:
            conn.close()

    def _update_ema(self, conn, comp_name: str, won: bool):
        """Atualiza EMA da comp"""
        row = conn.execute(
            "SELECT ema_wr, total_games, wins FROM comp_stats WHERE comp_name = ?",
            (comp_name,)
        ).fetchone()

        if row:
            old_ema, total, wins = row
            new_ema = EMA_ALPHA * (1.0 if won else 0.0) + (1 - EMA_ALPHA) * old_ema
            total += 1
            wins += 1 if won else 0
            conn.execute(
                "UPDATE comp_stats SET ema_wr = ?, total_games = ?, wins = ?, last_updated = ? WHERE comp_name = ?",
                (new_ema, total, wins, datetime.now().isoformat(), comp_name)
            )
        else:
            new_ema = 1.0 if won else 0.0
            conn.execute(
                "INSERT INTO comp_stats (comp_name, ema_wr, total_games, wins, last_updated) VALUES (?, ?, ?, ?, ?)",
                (comp_name, new_ema, 1, 1 if won else 0, datetime.now().isoformat())
            )
        conn.commit()

    def get_comp_effectiveness(self, comp_name: str) -> dict:
        """Retorna win rate suavizado da comp"""
        conn = sqlite3.connect(str(FEEDBACK_DB), timeout=5.0)
        try:
            row = conn.execute(
                "SELECT ema_wr, total_games, wins FROM comp_stats WHERE comp_name = ?",
                (comp_name,)
            ).fetchone()
            if row:
                ema_wr, total, wins = row
                return {
                    "comp": comp_name,
                    "ema_wr": round(ema_wr * 100, 1),
                    "total_games": total,
                    "wins": wins,
                    "reliable": total >= MIN_SAMPLE,
                    "raw_wr": round(wins / total * 100, 1) if total > 0 else 0,
                }
        except Exception as e:
            logging.debug(f"Erro ao buscar efetividade: {e}")
        finally:
            conn.close()
        return {"comp": comp_name, "ema_wr": 50, "total_games": 0, "wins": 0, "reliable": False, "raw_wr": 0}

    def get_calibration_summary(self) -> dict:
        """Resumo da calibração local"""
        conn = sqlite3.connect(str(FEEDBACK_DB), timeout=5.0)
        try:
            total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            followed = conn.execute("SELECT COUNT(*) FROM feedback WHERE user_followed = 1").fetchone()[0]
            avg_placement = conn.execute(
                "SELECT AVG(placement) FROM feedback WHERE user_followed = 1"
            ).fetchone()[0] or 0
            top_comps = conn.execute(
                """SELECT comp_name, ema_wr, total_games FROM comp_stats
                   WHERE total_games >= ? ORDER BY ema_wr DESC LIMIT 5""",
                (MIN_SAMPLE,)
            ).fetchall()
            return {
                "total_feedbacks": total,
                "followed_count": followed,
                "avg_placement_followed": round(avg_placement, 1),
                "top_comps": [
                    {"comp": c[0], "ema_wr": round(c[1] * 100, 1), "games": c[2]}
                    for c in top_comps
                ],
            }
        except Exception as e:
            logging.debug(f"Erro no resumo: {e}")
        finally:
            conn.close()
        return {"total_feedbacks": 0}

    def get_recent_feedback(self, comp_name: str = None, limit: int = 15) -> list:
        """Retorna apenas as ultimas N partidas (janela deslizante)."""
        conn = sqlite3.connect(str(FEEDBACK_DB), timeout=5.0)
        try:
            if comp_name:
                rows = conn.execute(
                    "SELECT * FROM feedback WHERE comp_name = ? ORDER BY id DESC LIMIT ?",
                    (comp_name, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return rows
        except Exception as e:
            logging.debug(f"Erro ao buscar feedback recente: {e}")
            return []
        finally:
            conn.close()

    def inject_calibration(self, comp_name: str) -> str:
        """Gera texto de calibração para injetar no prompt da IA"""
        eff = self.get_comp_effectiveness(comp_name)
        if not eff["reliable"]:
            return f"Comp '{comp_name}': dados insuficientes ({eff['total_games']} jogos)."

        wr = eff["ema_wr"]
        games = eff["total_games"]

        if wr >= 55:
            return f"Comp '{comp_name}': forte no seu historico ({wr}% WR suavizado em {games} jogos). Mantenha prioridade alta."
        elif wr >= 45:
            return f"Comp '{comp_name}': performance media ({wr}% WR suavizado em {games} jogos). Considere ajustes."
        else:
            return f"Comp '{comp_name}': fraca no seu historico ({wr}% WR suavizado em {games} jogos). Evite ou ajuste significativamente."


feedback_calibrator = FeedbackCalibrator()
