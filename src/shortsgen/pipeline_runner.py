import logging
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from shortsgen.config import settings
from shortsgen.history import RunRecorder
from shortsgen.models import Transcript
from shortsgen.pipeline.captions import build_ass_captions
from shortsgen.pipeline.download import download_video
from shortsgen.pipeline.highlights import find_highlights
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

    def clip_progress(self, done: int, total: int) -> None:
        pass

    def run_finished(self, clips: int, output_dir: Path) -> None:
        pass

    def run_failed(self, error: str, run_dir: Path) -> None:
        pass


def _slugify(text: str, max_len: int = 60) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower()).strip("-")
    return slug[:max_len] or "clip"


def _resolve_source(source: str, work_dir: Path, reporter: ProgressReporter) -> Path:
    local_path = Path(source)
    if local_path.exists():
        reporter.message(f"Usando arquivo local: {local_path}")
        return local_path

    reporter.message(f"Baixando video: {source}")
    video_path = download_video(source, work_dir)
    reporter.message(f"Download concluido: {video_path}")
    return video_path


def run_pipeline(
    source: str,
    *,
    max_clips: int | None = None,
    keep_temp: bool = False,
    reporter: ProgressReporter | None = None,
) -> None:
    """Roda o pipeline completo (download -> transcricao -> highlights -> render).

    Registra o historico da execucao em SQLite e reporta progresso via
    `reporter`. Levanta a excecao original em caso de falha; quem chamou
    decide como mostrar isso ao usuario.
    """
    reporter = reporter or ProgressReporter()

    if max_clips is not None:
        settings.max_clips = max_clips

    run_id = uuid.uuid4().hex[:8]
    run_dir = settings.work_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando run %s para source=%r", run_id, source)
    recorder = RunRecorder(settings.db_path, run_id, source)

    try:
        reporter.stage_started("download")
        recorder.start_stage("download")
        video_path = _resolve_source(source, run_dir, reporter)
        recorder.end_stage("download")

        reporter.stage_started("transcricao")
        recorder.start_stage("transcricao")
        transcript: Transcript = transcribe(video_path)
        recorder.end_stage("transcricao")
        reporter.message(f"Transcricao concluida. Idioma detectado: {transcript.language}")
        logger.info("Transcricao concluida (run %s). Idioma: %s", run_id, transcript.language)

        reporter.stage_started("highlights")
        recorder.start_stage("highlights")
        highlight_list = find_highlights(transcript)
        recorder.end_stage("highlights")
        reporter.message(f"{len(highlight_list.highlights)} highlight(s) encontrado(s).")
        logger.info("%d highlight(s) encontrado(s) (run %s)", len(highlight_list.highlights), run_id)

        total = len(highlight_list.highlights)
        reporter.stage_started("render")
        recorder.start_stage("render")
        for idx, highlight in enumerate(highlight_list.highlights, start=1):
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
            cut_segment(video_path, highlight.start, highlight.end, clip_raw)

            reporter.message("  Reenquadrando para 9:16 (seguindo o rosto)...")
            reframe_to_vertical(clip_raw, clip_vertical)

            reporter.message("  Gerando legendas...")
            words = transcript.words_between(highlight.start, highlight.end)
            build_ass_captions(words, highlight.start, clip_ass)

            slug = _slugify(highlight.title)
            output_path = settings.output_dir / f"{idx:02d}-{slug}.mp4"
            reporter.message(f"  Renderizando final -> {output_path}")
            mux_final(clip_vertical, clip_raw, clip_ass, output_path)
        recorder.end_stage("render")
        reporter.clip_progress(total, total)

        reporter.message(f"Pronto! {total} clipe(s) em {settings.output_dir}")
        logger.info("Run %s concluida com sucesso: %d clipe(s)", run_id, total)
        recorder.mark_success(total)
        reporter.run_finished(total, settings.output_dir)
    except Exception as exc:
        logger.exception("Run %s falhou", run_id)
        recorder.mark_error(str(exc))
        reporter.run_failed(str(exc), run_dir)
        raise
    else:
        if not keep_temp:
            shutil.rmtree(run_dir, ignore_errors=True)
