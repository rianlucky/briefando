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


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
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
