import logging
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from pathlib import Path

from yt_dlp.utils import DownloadCancelled

from shortsgen.config import settings
from shortsgen.exceptions import PipelineCancelled
from shortsgen.history import RunRecorder, get_transcription_factor
from shortsgen.models import Transcript
from shortsgen.pipeline.captions import build_ass_captions
from shortsgen.pipeline.download import download_video
from shortsgen.pipeline.highlights import DEFAULT_CATEGORY_ID, YOUTUBE_CATEGORIES, find_highlights
from shortsgen.pipeline.reframe import reframe_to_vertical
from shortsgen.pipeline.render import cut_segment, mux_final
from shortsgen.pipeline.transcribe import transcribe

logger = logging.getLogger(__name__)

STAGE_LABELS = {
    "download": "Baixando/localizando video",
    "transcricao": "Transcrevendo audio (faster-whisper)",
    "highlights": "Perguntando ao Gemini quais trechos cortar",
    "render": "Cortando e renderizando clipes",
}


class ProgressReporter:
    """Callbacks pra observar o progresso do pipeline.

    Metodos sao no-op por padrao; cada front-end (CLI, TUI) sobrescreve so o
    que precisa mostrar, sem o `run_pipeline` conhecer nada de apresentacao.
    """

    def message(self, text: str) -> None:
        pass

    def stage_started(self, stage: str) -> None:
        pass

    def download_progress(self, percent: float) -> None:
        pass

    def transcription_progress(self, percent: float) -> None:
        pass

    def clip_progress(self, done: int, total: int) -> None:
        pass

    def run_finished(self, clips: int, output_dir: Path) -> None:
        pass

    def run_failed(self, error: str, run_dir: Path) -> None:
        pass

    def run_cancelled(self, run_dir: Path) -> None:
        pass


def _slugify(text: str, max_len: int = 60) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower()).strip("-")
    return slug[:max_len] or "clip"


def _probe_duration(path: Path) -> float | None:
    """Duracao em segundos de um arquivo de video local, via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _retry(fn, *, attempts: int, delay: float, on_retry=None):
    """Chama `fn()`, tentando de novo ate `attempts` vezes se ela levantar excecao
    (falhas transitorias de rede/API). Repassa a excecao original apos a ultima
    tentativa. `on_retry(attempt, exc)` e chamado antes de cada nova tentativa."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == attempts:
                raise
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(delay)


def _run_with_progress_ticks(work, on_tick, interval: float = 2.0):
    """Roda `work()` numa thread separada, chamando `on_tick(elapsed_seconds)`
    periodicamente ate ela terminar.

    Usado pra estimar progresso de chamadas bloqueantes que nao reportam nada
    incremental (ex: faster-whisper transcreve tudo de uma vez so).
    """
    result: dict = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            result["value"] = work()
        except BaseException as exc:  # noqa: BLE001 - repassado pro chamador abaixo
            result["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    start = time.monotonic()
    while not done.wait(timeout=interval):
        on_tick(time.monotonic() - start)
    thread.join()

    if "error" in result:
        raise result["error"]
    return result["value"]


def _resolve_source(
    source: str,
    work_dir: Path,
    reporter: ProgressReporter,
    cancel_event: threading.Event | None,
) -> tuple[Path, float | None]:
    local_path = Path(source)
    if local_path.exists():
        reporter.message(f"Usando arquivo local: {local_path}")
        return local_path, _probe_duration(local_path)

    reporter.message(f"Baixando video: {source}")

    def _on_progress(status: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled("Cancelado durante o download")
        if status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        downloaded = status.get("downloaded_bytes")
        if total:
            reporter.download_progress(min(100.0, downloaded / total * 100))

    video_path, duration = download_video(source, work_dir, on_progress=_on_progress)
    reporter.message(f"Download concluido: {video_path}")
    return video_path, duration


def run_pipeline(
    source: str,
    *,
    max_clips: int | None = None,
    keep_temp: bool = False,
    reporter: ProgressReporter | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Roda o pipeline completo (download -> transcricao -> highlights -> render).

    Registra o historico da execucao em SQLite e reporta progresso via
    `reporter`. Levanta a excecao original em caso de falha real; quem chamou
    decide como mostrar isso ao usuario. Cancelamento (via `cancel_event`) nao
    e tratado como erro: e checado em pontos de parada limpos (entre etapas,
    entre clipes, dentro do ffmpeg/reframe) - a transcricao em si e uma
    chamada bloqueante do faster-whisper sem ponto de interrupcao, entao um
    cancelamento pedido durante ela so surte efeito assim que ela terminar.
    """
    reporter = reporter or ProgressReporter()

    if max_clips is not None:
        settings.max_clips = max_clips

    run_id = uuid.uuid4().hex[:8]
    run_dir = settings.work_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando run %s para source=%r", run_id, source)
    recorder = RunRecorder(settings.db_path, run_id, source)

    def _check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise PipelineCancelled("Cancelado pelo usuario")

    try:
        reporter.stage_started("download")
        recorder.start_stage("download")
        video_path, duration = _resolve_source(source, run_dir, reporter, cancel_event)
        recorder.end_stage("download")
        if duration:
            recorder.set_source_duration(duration)

        _check_cancelled()
        reporter.stage_started("transcricao")
        recorder.start_stage("transcricao")

        factor = get_transcription_factor(settings.db_path)

        def _on_transcribe_tick(elapsed: float) -> None:
            if duration:
                estimated_total = max(duration * factor, 1.0)
                reporter.transcription_progress(min(99.0, elapsed / estimated_total * 100))

        def _on_transcribe_retry(attempt: int, exc: Exception) -> None:
            reporter.message(f"  Transcricao falhou (tentativa {attempt}): {exc}. Tentando de novo...")
            logger.warning("Transcricao falhou (run %s, tentativa %d): %s", run_id, attempt, exc)

        transcript: Transcript = _run_with_progress_ticks(
            lambda: _retry(
                lambda: transcribe(video_path),
                attempts=settings.pipeline_retry_attempts,
                delay=settings.pipeline_retry_delay_seconds,
                on_retry=_on_transcribe_retry,
            ),
            _on_transcribe_tick,
            interval=2.0,
        )
        recorder.end_stage("transcricao")
        reporter.transcription_progress(100.0)
        reporter.message(f"Transcricao concluida. Idioma detectado: {transcript.language}")
        logger.info("Transcricao concluida (run %s). Idioma: %s", run_id, transcript.language)

        _check_cancelled()
        reporter.stage_started("highlights")
        recorder.start_stage("highlights")
        def _on_highlights_retry(attempt: int, exc: Exception) -> None:
            reporter.message(f"  Gemini falhou (tentativa {attempt}): {exc}. Tentando de novo...")
            logger.warning("Gemini falhou (run %s, tentativa %d): %s", run_id, attempt, exc)

        highlight_list = _retry(
            lambda: find_highlights(transcript),
            attempts=settings.pipeline_retry_attempts,
            delay=settings.pipeline_retry_delay_seconds,
            on_retry=_on_highlights_retry,
        )
        recorder.end_stage("highlights")
        reporter.message(f"{len(highlight_list.highlights)} highlight(s) encontrado(s).")
        logger.info("%d highlight(s) encontrado(s) (run %s)", len(highlight_list.highlights), run_id)

        _check_cancelled()
        total = len(highlight_list.highlights)
        reporter.stage_started("render")
        recorder.start_stage("render")
        for idx, highlight in enumerate(highlight_list.highlights, start=1):
            _check_cancelled()
            reporter.clip_progress(idx - 1, total)
            reporter.message(
                f"Clipe {idx}/{total}: {highlight.title} "
                f"({highlight.start:.1f}s - {highlight.end:.1f}s)"
            )
            reporter.message(f"  {highlight.reason}")

            clip_raw = run_dir / f"clip_{idx}_raw.mp4"
            clip_vertical = run_dir / f"clip_{idx}_vertical.mp4"
            clip_ass = run_dir / f"clip_{idx}.ass"

            reporter.message("  Cortando trecho...")
            cut_segment(video_path, highlight.start, highlight.end, clip_raw, cancel_event=cancel_event)

            reporter.message("  Reenquadrando para 9:16 (seguindo o rosto)...")
            reframe_to_vertical(clip_raw, clip_vertical, cancel_event=cancel_event)

            reporter.message("  Gerando legendas...")
            words = transcript.words_between(highlight.start, highlight.end)
            build_ass_captions(words, highlight.start, clip_ass)

            slug = _slugify(highlight.title)
            output_path = settings.output_dir / f"{idx:02d}-{slug}.mp4"
            reporter.message(f"  Renderizando final -> {output_path}")
            mux_final(clip_vertical, clip_raw, clip_ass, output_path, cancel_event=cancel_event)
            recorder.record_clip(
                str(output_path),
                highlight.title,
                highlight.description,
                highlight.tags,
                highlight.hashtags,
                YOUTUBE_CATEGORIES.get(highlight.category, DEFAULT_CATEGORY_ID),
            )
        recorder.end_stage("render")
        reporter.clip_progress(total, total)

        reporter.message(f"Pronto! {total} clipe(s) em {settings.output_dir}")
        logger.info("Run %s concluida com sucesso: %d clipe(s)", run_id, total)
        recorder.mark_success(total)
        reporter.run_finished(total, settings.output_dir)
    except (PipelineCancelled, DownloadCancelled) as exc:
        logger.info("Run %s cancelada: %s", run_id, exc)
        recorder.mark_cancelled()
        reporter.run_cancelled(run_dir)
    except Exception as exc:
        logger.exception("Run %s falhou", run_id)
        recorder.mark_error(str(exc))
        reporter.run_failed(str(exc), run_dir)
        raise
    else:
        if not keep_temp:
            shutil.rmtree(run_dir, ignore_errors=True)
