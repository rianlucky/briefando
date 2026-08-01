import sqlite3
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    clips_generated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Migracao minima: adiciona a coluna se o banco foi criado antes dela existir."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    _ensure_column(conn, "runs", "source_duration_seconds", "REAL")
    return conn


class RunRecorder:
    """Registra estados, tempo por etapa e erros de uma execucao do pipeline em SQLite."""

    def __init__(self, db_path: Path, run_id: str, source: str) -> None:
        self._conn = connect(db_path)
        self._run_id = run_id
        self._conn.execute(
            "INSERT INTO runs (run_id, source, status, started_at, clips_generated) "
            "VALUES (?, ?, 'running', ?, 0)",
            (run_id, source, _now()),
        )
        self._conn.commit()

    def start_stage(self, stage: str) -> None:
        self._conn.execute(
            "INSERT INTO run_stages (run_id, stage, started_at) VALUES (?, ?, ?)",
            (self._run_id, stage, _now()),
        )
        self._conn.commit()

    def end_stage(self, stage: str) -> None:
        self._conn.execute(
            "UPDATE run_stages SET finished_at = ? "
            "WHERE run_id = ? AND stage = ? AND finished_at IS NULL",
            (_now(), self._run_id, stage),
        )
        self._conn.commit()

    def mark_success(self, clips_generated: int) -> None:
        self._conn.execute(
            "UPDATE runs SET status = 'success', finished_at = ?, clips_generated = ? WHERE run_id = ?",
            (_now(), clips_generated, self._run_id),
        )
        self._conn.commit()
        self._conn.close()

    def mark_error(self, message: str) -> None:
        self._conn.execute(
            "UPDATE runs SET status = 'error', finished_at = ?, error_message = ? WHERE run_id = ?",
            (_now(), message, self._run_id),
        )
        self._conn.commit()
        self._conn.close()

    def mark_cancelled(self) -> None:
        self._conn.execute(
            "UPDATE runs SET status = 'cancelled', finished_at = ? WHERE run_id = ?",
            (_now(), self._run_id),
        )
        self._conn.commit()
        self._conn.close()

    def set_source_duration(self, seconds: float) -> None:
        self._conn.execute(
            "UPDATE runs SET source_duration_seconds = ? WHERE run_id = ?",
            (seconds, self._run_id),
        )
        self._conn.commit()


def get_daily_stats(db_path: Path) -> dict:
    """Shorts gerados hoje, execucoes com erro hoje e tempo medio por etapa.

    Fonte unica reutilizada pelo comando `stats` (CLI) e pelo painel de
    estatisticas do TUI.
    """
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    today = datetime.now().strftime("%Y-%m-%d")

    clips_today = conn.execute(
        "SELECT COALESCE(SUM(clips_generated), 0) FROM runs WHERE status = 'success' AND started_at LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]
    errors_today = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE status = 'error' AND started_at LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]
    stage_rows = conn.execute(
        "SELECT stage, AVG((julianday(finished_at) - julianday(started_at)) * 86400.0) AS avg_seconds "
        "FROM run_stages WHERE finished_at IS NOT NULL GROUP BY stage"
    ).fetchall()
    conn.close()

    return {
        "clips_today": clips_today,
        "errors_today": errors_today,
        "stage_avgs": {row["stage"]: row["avg_seconds"] for row in stage_rows},
    }


DEFAULT_TRANSCRIPTION_FACTOR = 1.5


def get_transcription_factor(db_path: Path) -> float:
    """Media (tempo de transcricao / duracao do video) das execucoes passadas.

    Usado pra estimar o progresso de uma transcricao em andamento (o
    faster-whisper nao reporta progresso incremental). Sem historico
    suficiente, cai no `DEFAULT_TRANSCRIPTION_FACTOR`.
    """
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            (julianday(s.finished_at) - julianday(s.started_at)) * 86400.0 AS transcricao_seconds,
            r.source_duration_seconds AS video_seconds
        FROM run_stages s
        JOIN runs r ON r.run_id = s.run_id
        WHERE s.stage = 'transcricao'
          AND s.finished_at IS NOT NULL
          AND r.source_duration_seconds IS NOT NULL
          AND r.source_duration_seconds > 0
        """
    ).fetchall()
    conn.close()

    if not rows:
        return DEFAULT_TRANSCRIPTION_FACTOR

    ratios = [row["transcricao_seconds"] / row["video_seconds"] for row in rows]
    return sum(ratios) / len(ratios)
