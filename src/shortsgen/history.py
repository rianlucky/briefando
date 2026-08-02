import json
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

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_dedup_active
    ON queue(dedup_key) WHERE status IN ('pending', 'running');

CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published INTEGER NOT NULL DEFAULT 0,
    published_at TEXT
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
    _ensure_column(conn, "clips", "description", "TEXT")
    _ensure_column(conn, "clips", "tags", "TEXT")
    _ensure_column(conn, "clips", "hashtags", "TEXT")
    _ensure_column(conn, "clips", "category_id", "TEXT")
    _ensure_column(conn, "clips", "deleted_at", "TEXT")
    _ensure_column(conn, "clips", "youtube_video_id", "TEXT")
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

    def record_clip(
        self,
        path: str,
        title: str,
        description: str,
        tags: list[str],
        hashtags: list[str],
        category_id: str,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO clips (run_id, path, title, description, tags, hashtags, category_id, created_at, published) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (self._run_id, path, title, description, json.dumps(tags), json.dumps(hashtags), category_id, _now()),
        )
        self._conn.commit()
        return cursor.lastrowid


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


class DuplicateQueueItem(Exception):
    """Levantada ao enfileirar um source que ja esta pendente ou rodando na fila."""


def enqueue(db_path: Path, source: str, dedup_key: str) -> int:
    conn = connect(db_path)
    now = _now()
    try:
        cursor = conn.execute(
            "INSERT INTO queue (source, dedup_key, status, retry_count, created_at, updated_at) "
            "VALUES (?, ?, 'pending', 0, ?, ?)",
            (source, dedup_key, now, now),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise DuplicateQueueItem(f"'{source}' ja esta na fila (pendente ou rodando)") from exc
    finally:
        conn.close()


def list_queue(db_path: Path, statuses: tuple[str, ...] | None = None) -> list[dict]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        rows = conn.execute(
            f"SELECT * FROM queue WHERE status IN ({placeholders}) ORDER BY created_at", statuses
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM queue ORDER BY created_at").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_clips(db_path: Path, published: bool | None = None) -> list[dict]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    if published is None:
        rows = conn.execute("SELECT * FROM clips ORDER BY created_at").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM clips WHERE published = ? ORDER BY created_at", (1 if published else 0,)
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_clip(db_path: Path, clip_id: int) -> dict | None:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_clip_path(db_path: Path, clip_id: int, new_path: str) -> None:
    conn = connect(db_path)
    conn.execute("UPDATE clips SET path = ? WHERE id = ?", (new_path, clip_id))
    conn.commit()
    conn.close()


def clips_ready_for_cleanup(db_path: Path, retention_days: int) -> list[dict]:
    """Clipes publicados ha mais de `retention_days` dias e ainda nao apagados."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, path FROM clips WHERE published = 1 AND deleted_at IS NULL "
        "AND datetime(published_at) <= datetime('now', ?)",
        (f"-{retention_days} days",),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_clip_deleted(db_path: Path, clip_id: int) -> None:
    conn = connect(db_path)
    conn.execute("UPDATE clips SET deleted_at = ? WHERE id = ?", (_now(), clip_id))
    conn.commit()
    conn.close()


def next_unpublished_clip(db_path: Path) -> dict | None:
    """Escolhe aleatoriamente um clipe nao publicado (nao o mais antigo) - evita
    publicar sempre na mesma ordem/sequencia dos videos processados. Devolve
    com a descricao final (hashtags ja anexadas) e tags como lista, pronto pra
    automacao externa (ex.: n8n) usar direto no upload."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, path, title, description, tags, hashtags, category_id FROM clips "
        "WHERE published = 0 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        return None

    clip = dict(row)
    hashtags = json.loads(clip.pop("hashtags") or "[]")
    clip["tags"] = json.loads(clip.pop("tags") or "[]")
    hashtag_line = " ".join(f"#{h}" for h in hashtags)
    description = clip.get("description") or ""
    clip["description"] = f"{description}\n\n{hashtag_line}".strip() if hashtag_line else description
    return clip


def mark_clip_published(db_path: Path, clip_id: int, youtube_video_id: str | None = None) -> bool:
    """Marca como publicado. `youtube_video_id` (quando informado) fica salvo pra
    auditoria - permite conferir manualmente se um clipe ja foi mesmo publicado
    antes de reenviar, caso essa chamada precise ser repetida depois de uma
    falha parcial (upload ok, mark-published falhou)."""
    conn = connect(db_path)
    cursor = conn.execute(
        "UPDATE clips SET published = 1, published_at = ?, youtube_video_id = ? WHERE id = ? AND published = 0",
        (_now(), youtube_video_id, clip_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def get_queue_counts(db_path: Path) -> dict:
    conn = connect(db_path)
    rows = conn.execute("SELECT status, COUNT(*) FROM queue GROUP BY status").fetchall()
    conn.close()
    counts = {"pending": 0, "running": 0, "done": 0, "error": 0}
    counts.update(dict(rows))
    return counts


def get_clips_counts(db_path: Path) -> dict:
    conn = connect(db_path)
    published = conn.execute("SELECT COUNT(*) FROM clips WHERE published = 1").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM clips WHERE published = 0").fetchone()[0]
    conn.close()
    return {"published": published, "pending": pending}


def claim_next_pending(db_path: Path) -> dict | None:
    """Pega o item pendente mais antigo e marca como 'running'. None se a fila estiver vazia."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM queue WHERE status = 'pending' ORDER BY created_at LIMIT 1"
    ).fetchone()
    if row is None:
        conn.close()
        return None
    conn.execute("UPDATE queue SET status = 'running', updated_at = ? WHERE id = ?", (_now(), row["id"]))
    conn.commit()
    conn.close()
    return dict(row)


def claim_item(db_path: Path, item_id: int) -> None:
    """Marca um item especifico (nao 'o proximo') como 'running' - usado quando
    quem enfileirou quer acompanhar aquele item na hora (ex.: TUI)."""
    conn = connect(db_path)
    conn.execute("UPDATE queue SET status = 'running', updated_at = ? WHERE id = ?", (_now(), item_id))
    conn.commit()
    conn.close()


def reset_queue_item_to_pending(db_path: Path, item_id: int) -> None:
    """Volta um item pra 'pending' sem contar como retry - usado quando o usuario
    cancela a execucao de proposito, nao quando ela falha."""
    conn = connect(db_path)
    conn.execute("UPDATE queue SET status = 'pending', updated_at = ? WHERE id = ?", (_now(), item_id))
    conn.commit()
    conn.close()


def mark_queue_done(db_path: Path, item_id: int) -> None:
    conn = connect(db_path)
    conn.execute("UPDATE queue SET status = 'done', updated_at = ? WHERE id = ?", (_now(), item_id))
    conn.commit()
    conn.close()


def _requeue_or_fail(conn: sqlite3.Connection, item_id: int, retry_count: int, message: str, max_retries: int) -> str:
    """Reaplica pra 'pending' (incrementando retry_count) se ainda houver tentativas
    dentro de `max_retries` (contagem total, ex.: 3 = original + 2 retries); senao
    marca 'error' terminal. Retorna o novo status."""
    now = _now()
    if retry_count < max_retries - 1:
        conn.execute(
            "UPDATE queue SET status = 'pending', retry_count = retry_count + 1, "
            "error_message = ?, updated_at = ? WHERE id = ?",
            (message, now, item_id),
        )
        return "pending"
    conn.execute(
        "UPDATE queue SET status = 'error', error_message = ?, updated_at = ? WHERE id = ?",
        (message, now, item_id),
    )
    return "error"


def mark_queue_error(db_path: Path, item_id: int, message: str, max_retries: int) -> str:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT retry_count FROM queue WHERE id = ?", (item_id,)).fetchone()
    new_status = _requeue_or_fail(conn, item_id, row["retry_count"], message, max_retries)
    conn.commit()
    conn.close()
    return new_status


def recover_orphans(db_path: Path, max_retries: int) -> int:
    """Itens travados em 'running' sao de uma execucao anterior interrompida no
    meio (processo morto, queda de energia etc.) - com um worker por vez, nao ha
    ambiguidade. Aplica a mesma politica de retry de `mark_queue_error`. Retorna
    quantos itens foram recuperados."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    orphans = conn.execute("SELECT id, retry_count FROM queue WHERE status = 'running'").fetchall()
    for row in orphans:
        _requeue_or_fail(
            conn, row["id"], row["retry_count"], "Interrompido antes de terminar (processo reiniciado)", max_retries
        )
    conn.commit()
    conn.close()
    return len(orphans)


def retry_queue_item(db_path: Path, item_id: int) -> bool:
    """Reseta manualmente um item 'error' pra 'pending'. False se nao existir ou nao estiver em error."""
    conn = connect(db_path)
    cursor = conn.execute(
        "UPDATE queue SET status = 'pending', updated_at = ? WHERE id = ? AND status = 'error'",
        (_now(), item_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


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
