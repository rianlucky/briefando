import json
import sqlite3
from datetime import datetime, timedelta
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

CREATE TABLE IF NOT EXISTS clip_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    fetched_at TEXT NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    impressions INTEGER,
    ctr REAL,
    average_view_duration_seconds REAL,
    average_view_percentage REAL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL UNIQUE,
    delay_hours INTEGER NOT NULL DEFAULT 24,
    min_duration_seconds INTEGER NOT NULL DEFAULT 180,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
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
    _ensure_column(conn, "runs", "gemini_input_tokens", "INTEGER")
    _ensure_column(conn, "runs", "gemini_output_tokens", "INTEGER")
    _ensure_column(conn, "clips", "description", "TEXT")
    _ensure_column(conn, "clips", "tags", "TEXT")
    _ensure_column(conn, "clips", "hashtags", "TEXT")
    _ensure_column(conn, "clips", "category_id", "TEXT")
    _ensure_column(conn, "clips", "deleted_at", "TEXT")
    _ensure_column(conn, "clips", "youtube_video_id", "TEXT")
    _ensure_column(conn, "clips", "quality_score", "INTEGER")
    _ensure_column(conn, "clips", "approved", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "clips", "review_skipped_at", "TEXT")
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

    def add_gemini_usage(self, input_tokens: int, output_tokens: int) -> None:
        self._conn.execute(
            "UPDATE runs SET "
            "gemini_input_tokens = COALESCE(gemini_input_tokens, 0) + ?, "
            "gemini_output_tokens = COALESCE(gemini_output_tokens, 0) + ? "
            "WHERE run_id = ?",
            (input_tokens, output_tokens, self._run_id),
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
        quality_score: int,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO clips (run_id, path, title, description, tags, hashtags, category_id, quality_score, created_at, published) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                self._run_id,
                path,
                title,
                description,
                json.dumps(tags),
                json.dumps(hashtags),
                category_id,
                quality_score,
                _now(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid


def get_current_activity(db_path: Path) -> dict | None:
    """Run 'running' agora (se houver) e a etapa ativa dele - le direto do
    banco, entao funciona pra qualquer processo que estiver rodando o
    pipeline (TUI, `queue run` via CLI ou disparado pelo n8n), nao so jobs
    iniciados pela propria TUI."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    run = conn.execute(
        "SELECT run_id, source, started_at FROM runs WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if run is None:
        conn.close()
        return None
    stage = conn.execute(
        "SELECT stage, started_at FROM run_stages WHERE run_id = ? AND finished_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (run["run_id"],),
    ).fetchone()
    conn.close()
    return {
        "run_id": run["run_id"],
        "source": run["source"],
        "started_at": run["started_at"],
        "stage": stage["stage"] if stage else None,
        "stage_started_at": stage["started_at"] if stage else None,
    }


def get_recent_runs(db_path: Path, limit: int = 8) -> list[dict]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT run_id, source, status, started_at, finished_at, clips_generated, error_message "
        "FROM runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_daily_stats(db_path: Path, target_date: str | None = None) -> dict:
    """Shorts gerados e execucoes com erro no dia (default hoje), e tempo medio por etapa.

    Fonte unica reutilizada pelo comando `stats` (CLI), pelo painel de
    estatisticas do TUI e pela tendencia dia-a-dia do dashboard.
    """
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    day = target_date or datetime.now().strftime("%Y-%m-%d")

    clips_today = conn.execute(
        "SELECT COALESCE(SUM(clips_generated), 0) FROM runs WHERE status = 'success' AND started_at LIKE ?",
        (f"{day}%",),
    ).fetchone()[0]
    errors_today = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE status = 'error' AND started_at LIKE ?",
        (f"{day}%",),
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


def get_stats_for_range(db_path: Path, start_date: str, end_date: str) -> dict:
    """Shorts gerados e execucoes com erro num intervalo [start_date, end_date] (inclusive, YYYY-MM-DD).

    Usado pelo seletor de periodo do dashboard (Hoje / Ultimos 7 dias / Este mes).
    """
    conn = connect(db_path)
    end_exclusive = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    clips = conn.execute(
        "SELECT COALESCE(SUM(clips_generated), 0) FROM runs "
        "WHERE status = 'success' AND started_at >= ? AND started_at < ?",
        (start_date, end_exclusive),
    ).fetchone()[0]
    errors = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE status = 'error' AND started_at >= ? AND started_at < ?",
        (start_date, end_exclusive),
    ).fetchone()[0]
    conn.close()

    return {"clips": clips, "errors": errors}


def get_conversion_funnel(db_path: Path, start_date: str, end_date: str, min_quality_score: int) -> list[dict]:
    """Funil de conversao Enfileirado -> Processado -> Aprovado -> Publicado no
    intervalo [start_date, end_date] (inclusive, YYYY-MM-DD).

    "Aprovado"/"Publicado" contam videos distintos (run_id), nao clipes, pra
    manter o funil monotonicamente decrescente mesmo quando um video vira
    varios clipes. Nao inclui o estagio "Descoberto" (RSS) - videos filtrados
    antes de chegar na fila nunca tocam esse banco.
    """
    conn = connect(db_path)
    end_exclusive = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    enfileirado = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE created_at >= ? AND created_at < ?",
        (start_date, end_exclusive),
    ).fetchone()[0]
    processado = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE status = 'done' AND created_at >= ? AND created_at < ?",
        (start_date, end_exclusive),
    ).fetchone()[0]
    aprovado = conn.execute(
        "SELECT COUNT(DISTINCT run_id) FROM clips WHERE created_at >= ? AND created_at < ? "
        "AND (approved = 1 OR quality_score >= ?)",
        (start_date, end_exclusive, min_quality_score),
    ).fetchone()[0]
    publicado = conn.execute(
        "SELECT COUNT(DISTINCT run_id) FROM clips WHERE created_at >= ? AND created_at < ? AND published = 1",
        (start_date, end_exclusive),
    ).fetchone()[0]
    conn.close()

    return [
        {"stage": "Enfileirado", "count": enfileirado},
        {"stage": "Processado", "count": processado},
        {"stage": "Aprovado", "count": aprovado},
        {"stage": "Publicado", "count": publicado},
    ]


def get_resource_usage_for_range(db_path: Path, start_date: str, end_date: str) -> dict:
    """Tokens do Gemini e tempo de maquina gastos no intervalo [start_date, end_date]
    (inclusive, YYYY-MM-DD) - visibilidade de custo/consumo, sem conversao pra $."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    end_exclusive = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    row = conn.execute(
        "SELECT COALESCE(SUM(gemini_input_tokens), 0) AS input_tokens, "
        "COALESCE(SUM(gemini_output_tokens), 0) AS output_tokens, "
        "COALESCE(SUM((julianday(COALESCE(finished_at, datetime('now'))) - julianday(started_at)) * 86400.0), 0) "
        "AS machine_seconds "
        "FROM runs WHERE started_at >= ? AND started_at < ?",
        (start_date, end_exclusive),
    ).fetchone()
    conn.close()

    return {
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "machine_seconds": row["machine_seconds"],
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


def has_ever_been_queued(db_path: Path, dedup_key: str) -> bool:
    """True se ja existe QUALQUER linha (independente do status) com essa
    dedup_key - diferente do indice unico da fila, que so olha pendente/rodando.
    Usado pela descoberta automatica (RSS) pra nao reenfileirar o que ja foi
    processado antes, mesmo que o feed continue trazendo o mesmo vídeo antigo."""
    conn = connect(db_path)
    row = conn.execute("SELECT 1 FROM queue WHERE dedup_key = ? LIMIT 1", (dedup_key,)).fetchone()
    conn.close()
    return row is not None


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


def set_clip_youtube_video_id(db_path: Path, clip_id: int, youtube_video_id: str) -> bool:
    """Preenche/corrige o `youtube_video_id` de um clipe ja publicado (o
    `mark_clip_published` normal so aceita isso na hora de marcar como
    publicado - isso aqui e pra backfill de clipes publicados antes do
    `--video-id` existir, ou correcao manual). False se o clipe nao existir."""
    conn = connect(db_path)
    cursor = conn.execute(
        "UPDATE clips SET youtube_video_id = ? WHERE id = ?", (youtube_video_id, clip_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def clips_for_analytics(db_path: Path) -> list[dict]:
    """Clipes publicados com `youtube_video_id` conhecido - a lista que a
    automacao externa (n8n) percorre pra buscar metricas atualizadas na API do
    YouTube (Data API pra views/likes/comments, Analytics API pra CTR/retencao)."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, youtube_video_id, title FROM clips "
        "WHERE published = 1 AND youtube_video_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def record_clip_analytics(
    db_path: Path,
    clip_id: int,
    *,
    views: int | None = None,
    likes: int | None = None,
    comments: int | None = None,
    impressions: int | None = None,
    ctr: float | None = None,
    average_view_duration_seconds: float | None = None,
    average_view_percentage: float | None = None,
) -> int:
    """Registra uma nova leitura de metricas pra um clipe (uma linha por
    chamada - forma uma serie temporal, nao sobrescreve a anterior)."""
    conn = connect(db_path)
    cursor = conn.execute(
        "INSERT INTO clip_analytics "
        "(clip_id, fetched_at, views, likes, comments, impressions, ctr, "
        " average_view_duration_seconds, average_view_percentage) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            clip_id,
            _now(),
            views,
            likes,
            comments,
            impressions,
            ctr,
            average_view_duration_seconds,
            average_view_percentage,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_clip_analytics_history(db_path: Path, clip_id: int) -> list[dict]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM clip_analytics WHERE clip_id = ? ORDER BY fetched_at, id", (clip_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_analytics_fetch(db_path: Path) -> str | None:
    """Timestamp da leitura de analytics mais recente (qualquer clipe) - usado pra
    mostrar 'atualizado ha X' no dashboard, ja que a leitura roda so 1x/dia."""
    conn = connect(db_path)
    row = conn.execute("SELECT MAX(fetched_at) FROM clip_analytics").fetchone()
    conn.close()
    return row[0]


def get_clip_analytics_history_bulk(db_path: Path, clip_ids: list[int]) -> dict[int, list[dict]]:
    """Historico de analytics de varios clipes numa unica query (evita N+1 quando
    quem chama precisa da serie temporal de vários clipes, ex.: grafico de coorte)."""
    if not clip_ids:
        return {}
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in clip_ids)
    rows = conn.execute(
        f"SELECT * FROM clip_analytics WHERE clip_id IN ({placeholders}) ORDER BY clip_id, fetched_at, id",
        clip_ids,
    ).fetchall()
    conn.close()

    history_by_clip: dict[int, list[dict]] = {clip_id: [] for clip_id in clip_ids}
    for row in rows:
        history_by_clip[row["clip_id"]].append(dict(row))
    return history_by_clip


def get_latest_analytics(db_path: Path, clip_id: int) -> dict | None:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM clip_analytics WHERE clip_id = ? ORDER BY fetched_at DESC, id DESC LIMIT 1", (clip_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_top_performing_titles(db_path: Path, limit: int = 5) -> list[dict]:
    """Titulos com mais views (usando a leitura mais recente de cada clipe) -
    usado como referencia de estilo/gancho no prompt do Gemini, pra aprender
    com o que ja performou bem no canal."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.id AS clip_id, c.title, c.published_at, a.views
        FROM clips c
        JOIN (
            SELECT clip_id, MAX(id) AS latest_id FROM clip_analytics GROUP BY clip_id
        ) latest ON latest.clip_id = c.id
        JOIN clip_analytics a ON a.id = latest.latest_id
        WHERE a.views IS NOT NULL
        ORDER BY a.views DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_score_vs_performance(db_path: Path) -> list[dict]:
    """Score de qualidade (Gemini) x views reais (leitura mais recente) - pra
    comparar visualmente se a nota realmente prevê performance."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.title, c.quality_score, a.views
        FROM clips c
        JOIN (
            SELECT clip_id, MAX(id) AS latest_id FROM clip_analytics GROUP BY clip_id
        ) latest ON latest.clip_id = c.id
        JOIN clip_analytics a ON a.id = latest.latest_id
        WHERE c.quality_score IS NOT NULL AND a.views IS NOT NULL
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_engagement_rates(db_path: Path, limit: int = 10) -> list[dict]:
    """Taxa de engajamento ((likes + comentarios) / views, leitura mais recente) por
    clipe - views cru e puxado pelo algoritmo, taxa de engajamento e mais diagnostico
    de qualidade real do conteudo."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.title, a.views, a.likes, a.comments
        FROM clips c
        JOIN (
            SELECT clip_id, MAX(id) AS latest_id FROM clip_analytics GROUP BY clip_id
        ) latest ON latest.clip_id = c.id
        JOIN clip_analytics a ON a.id = latest.latest_id
        WHERE a.views IS NOT NULL AND a.views > 0
        """
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        likes = row["likes"] or 0
        comments = row["comments"] or 0
        result.append(
            {
                "title": row["title"],
                "views": row["views"],
                "likes": likes,
                "comments": comments,
                "engagement_rate": (likes + comments) / row["views"],
            }
        )
    result.sort(key=lambda r: r["engagement_rate"], reverse=True)
    return result[:limit]


def build_youtube_feed_url(channel_id: str | None = None, playlist_id: str | None = None) -> str:
    """Monta a URL do feed RSS do YouTube pra um canal ou playlist - usado tanto
    pela CLI (`sources add`) quanto pelo dashboard, pra nao duplicar o formato."""
    param = f"channel_id={channel_id}" if channel_id else f"playlist_id={playlist_id}"
    return f"https://www.youtube.com/feeds/videos.xml?{param}"


def clips_pending_review(db_path: Path, min_quality_score: int) -> list[dict]:
    """Clipes nao publicados que ficaram abaixo do `min_quality_score` (ou nunca
    foram avaliados - `quality_score IS NULL`, ex.: gerados antes dessa
    funcionalidade existir) e ainda nao foram aprovados manualmente."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, quality_score FROM clips "
        "WHERE published = 0 AND approved = 0 "
        "AND (quality_score IS NULL OR quality_score < ?) "
        "ORDER BY quality_score IS NOT NULL, quality_score DESC",
        (min_quality_score,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_next_review_clip(db_path: Path, min_quality_score: int) -> dict | None:
    """Proximo clipe a revisar (fluxo um-a-um do dashboard) - clipes nunca pulados
    vem primeiro (mais antigo primeiro); clipes ja pulados voltam pro fim da fila,
    em rodizio, ordenados por quando foram pulados. Identidade por ID (nao por
    posicao), entao a fila fica estavel mesmo se um clipe novo chegar no meio."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM clips WHERE published = 0 AND approved = 0 "
        "AND (quality_score IS NULL OR quality_score < ?) "
        "ORDER BY (review_skipped_at IS NOT NULL), review_skipped_at, created_at "
        "LIMIT 1",
        (min_quality_score,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def skip_clip_review(db_path: Path, clip_id: int) -> None:
    """Manda o clipe pro fim do rodizio de revisao (persistido - sobrevive a reload)."""
    conn = connect(db_path)
    conn.execute("UPDATE clips SET review_skipped_at = ? WHERE id = ?", (_now(), clip_id))
    conn.commit()
    conn.close()


def approve_clip(db_path: Path, clip_id: int) -> bool:
    """Aprova manualmente um clipe que ficou abaixo do quality_score minimo,
    liberando ele pro fluxo normal de publicacao. False se nao existir."""
    conn = connect(db_path)
    cursor = conn.execute("UPDATE clips SET approved = 1 WHERE id = ?", (clip_id,))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def next_unpublished_clip(db_path: Path, min_quality_score: int) -> dict | None:
    """Escolhe aleatoriamente um clipe nao publicado (nao o mais antigo) - evita
    publicar sempre na mesma ordem/sequencia dos videos processados. So
    considera clipes com `quality_score >= min_quality_score` OU ja aprovados
    manualmente (`approved = 1`) - os demais ficam esperando revisao (ver
    `clips_pending_review`/`approve_clip`). Devolve com a descricao final
    (hashtags ja anexadas) e tags como lista, pronto pra automacao externa
    (ex.: n8n) usar direto no upload."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, path, title, description, tags, hashtags, category_id FROM clips "
        "WHERE published = 0 AND (quality_score >= ? OR approved = 1) "
        "ORDER BY RANDOM() LIMIT 1",
        (min_quality_score,),
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


def get_clips_counts(db_path: Path, min_quality_score: int) -> dict:
    conn = connect(db_path)
    published = conn.execute("SELECT COUNT(*) FROM clips WHERE published = 1").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM clips WHERE published = 0").fetchone()[0]
    needs_review = conn.execute(
        "SELECT COUNT(*) FROM clips WHERE published = 0 AND approved = 0 AND quality_score < ?",
        (min_quality_score,),
    ).fetchone()[0]
    conn.close()
    return {"published": published, "pending": pending, "needs_review": needs_review}


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
    ambiguidade. Aplica a mesma politica de retry de `mark_queue_error`. Tambem
    marca como 'cancelled' qualquer linha de `runs` ainda em 'running' (senao a
    TUI, que le essa tabela pro painel de Atividade Atual, fica mostrando uma
    execucao morta pra sempre). Retorna quantos itens da fila foram recuperados."""
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    orphans = conn.execute("SELECT id, retry_count FROM queue WHERE status = 'running'").fetchall()
    for row in orphans:
        _requeue_or_fail(
            conn, row["id"], row["retry_count"], "Interrompido antes de terminar (processo reiniciado)", max_retries
        )
    conn.execute("UPDATE runs SET status = 'cancelled', finished_at = ? WHERE status = 'running'", (_now(),))
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


def add_source(db_path: Path, name: str, feed_url: str, delay_hours: int, min_duration_seconds: int) -> int:
    conn = connect(db_path)
    cursor = conn.execute(
        "INSERT INTO sources (name, feed_url, delay_hours, min_duration_seconds, active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (name, feed_url, delay_hours, min_duration_seconds, _now()),
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def list_sources(db_path: Path, active_only: bool = True) -> list[dict]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM sources"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY id"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def remove_source(db_path: Path, source_id: int) -> bool:
    conn = connect(db_path)
    cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.commit()
    removed = cursor.rowcount > 0
    conn.close()
    return removed
