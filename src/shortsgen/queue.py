import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from shortsgen.config import settings
from shortsgen.history import (
    claim_next_pending,
    clips_ready_for_cleanup,
    enqueue,
    get_clip,
    mark_clip_deleted,
    mark_queue_done,
    mark_queue_error,
    recover_orphans,
    set_clip_path,
)
from shortsgen.pipeline_runner import ProgressReporter, run_pipeline

logger = logging.getLogger(__name__)

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def compute_dedup_key(source: str) -> str:
    """Chave de deduplicacao: ID do video pra URLs do YouTube (mesmo video com
    dominio/parametros diferentes cai na mesma chave), caminho absoluto
    resolvido pra arquivos locais, ou o source cru como fallback."""
    local_path = Path(source)
    if local_path.exists():
        return str(local_path.resolve())

    parsed = urlparse(source)
    host = parsed.netloc.lower()
    if host in _YOUTUBE_HOSTS:
        video_id = parsed.path.strip("/") if host == "youtu.be" else parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return f"youtube:{video_id}"

    return source


def add_to_queue(source: str) -> int:
    return enqueue(settings.db_path, source, compute_dedup_key(source))


def run_queue(reporter_factory=None) -> tuple[int, int]:
    """Processa a fila ate esvaziar e entao retorna - nao fica esperando novos
    itens aparecerem. A cadencia de chamar de novo fica por conta de quem
    agenda (ex.: n8n). Retorna (concluidos, com_erro_terminal)."""
    recovered = recover_orphans(settings.db_path, settings.queue_max_retries)
    if recovered:
        logger.info("%d item(ns) da fila recuperados apos interrupcao anterior", recovered)

    done = 0
    failed = 0
    while True:
        item = claim_next_pending(settings.db_path)
        if item is None:
            break

        reporter = reporter_factory() if reporter_factory else ProgressReporter()
        try:
            run_pipeline(item["source"], reporter=reporter)
        except Exception as exc:
            new_status = mark_queue_error(settings.db_path, item["id"], str(exc), settings.queue_max_retries)
            if new_status == "error":
                failed += 1
        else:
            mark_queue_done(settings.db_path, item["id"])
            done += 1

    return done, failed


def archive_clip(clip_id: int) -> Path:
    """Move o arquivo do clipe pra output_dir/postado/ e atualiza o caminho no
    banco na mesma operacao - mantem o `cleanup_published_clips` (que confia no
    caminho salvo) funcionando mesmo depois do arquivo ser movido."""
    clip = get_clip(settings.db_path, clip_id)
    if clip is None:
        raise ValueError(f"Clipe {clip_id} nao encontrado")

    current_path = Path(clip["path"])
    archive_dir = settings.output_dir / "postado"
    archive_dir.mkdir(parents=True, exist_ok=True)
    new_path = archive_dir / current_path.name
    current_path.rename(new_path)
    set_clip_path(settings.db_path, clip_id, str(new_path))
    return new_path


def cleanup_published_clips() -> tuple[int, int]:
    """Apaga do disco os clipes publicados ha mais de `settings.clip_retention_days`
    dias (o arquivo ja foi enviado pra plataforma, nao precisa mais dele localmente).
    Retorna (apagados, ja_ausentes_do_disco)."""
    candidates = clips_ready_for_cleanup(settings.db_path, settings.clip_retention_days)
    deleted = 0
    missing = 0
    for clip in candidates:
        path = Path(clip["path"])
        if path.exists():
            path.unlink()
            deleted += 1
        else:
            missing += 1
        mark_clip_deleted(settings.db_path, clip["id"])
    return deleted, missing
