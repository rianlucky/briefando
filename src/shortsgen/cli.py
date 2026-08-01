import logging
import os
import re
import shutil
import sqlite3
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from shortsgen.config import settings
from shortsgen.history import RunRecorder, connect as connect_history
from shortsgen.logging_setup import configure_logging
from shortsgen.models import Transcript
from shortsgen.pipeline.captions import build_ass_captions
from shortsgen.pipeline.download import download_video
from shortsgen.pipeline.highlights import find_highlights
from shortsgen.pipeline.reframe import reframe_to_vertical
from shortsgen.pipeline.render import cut_segment, mux_final
from shortsgen.pipeline.transcribe import transcribe

app = typer.Typer(add_completion=False)
console = Console()
configure_logging(settings.log_dir)
logger = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 60) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower()).strip("-")
    return slug[:max_len] or "clip"


def _resolve_source(source: str, work_dir: Path) -> Path:
    local_path = Path(source)
    if local_path.exists():
        console.print(f"[cyan]Usando arquivo local:[/cyan] {local_path}")
        return local_path

    console.print(f"[cyan]Baixando video:[/cyan] {source}")
    video_path = download_video(source, work_dir)
    console.print(f"[green]Download concluido:[/green] {video_path}")
    return video_path


@app.command()
def generate(
    source: str = typer.Argument(..., help="URL do YouTube ou caminho de um arquivo de video local"),
    max_clips: int = typer.Option(None, help="Numero maximo de clipes a gerar"),
    keep_temp: bool = typer.Option(False, help="Nao apagar os arquivos temporarios ao final"),
) -> None:
    """Gera shorts verticais com legenda a partir de um video (URL do YouTube ou arquivo local)."""
    if not settings.gemini_api_key:
        console.print("[red]Erro:[/red] GEMINI_API_KEY nao configurada. Defina-a no arquivo .env antes de rodar.")
        raise typer.Exit(1)

    if max_clips is not None:
        settings.max_clips = max_clips

    run_id = uuid.uuid4().hex[:8]
    run_dir = settings.work_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando run %s para source=%r", run_id, source)
    recorder = RunRecorder(settings.db_path, run_id, source)

    try:
        recorder.start_stage("download")
        video_path = _resolve_source(source, run_dir)
        recorder.end_stage("download")

        console.print("[cyan]Transcrevendo audio (faster-whisper)...[/cyan]")
        recorder.start_stage("transcricao")
        transcript: Transcript = transcribe(video_path)
        recorder.end_stage("transcricao")
        console.print(f"[green]Transcricao concluida.[/green] Idioma detectado: {transcript.language}")
        logger.info("Transcricao concluida (run %s). Idioma: %s", run_id, transcript.language)

        console.print("[cyan]Perguntando ao Gemini quais trechos cortar...[/cyan]")
        recorder.start_stage("highlights")
        highlight_list = find_highlights(transcript)
        recorder.end_stage("highlights")
        console.print(f"[green]{len(highlight_list.highlights)} highlight(s) encontrado(s).[/green]")
        logger.info("%d highlight(s) encontrado(s) (run %s)", len(highlight_list.highlights), run_id)

        recorder.start_stage("render")
        for idx, highlight in enumerate(highlight_list.highlights, start=1):
            console.print(
                f"\n[bold]Clipe {idx}/{len(highlight_list.highlights)}[/bold]: "
                f"{highlight.title} ({highlight.start:.1f}s - {highlight.end:.1f}s)"
            )
            console.print(f"  [dim]{highlight.reason}[/dim]")

            clip_raw = run_dir / f"clip_{idx}_raw.mp4"
            clip_vertical = run_dir / f"clip_{idx}_vertical.mp4"
            clip_ass = run_dir / f"clip_{idx}.ass"

            console.print("  Cortando trecho...")
            cut_segment(video_path, highlight.start, highlight.end, clip_raw)

            console.print("  Reenquadrando para 9:16 (seguindo o rosto)...")
            reframe_to_vertical(clip_raw, clip_vertical)

            console.print("  Gerando legendas...")
            words = transcript.words_between(highlight.start, highlight.end)
            build_ass_captions(words, highlight.start, clip_ass)

            slug = _slugify(highlight.title)
            output_path = settings.output_dir / f"{idx:02d}-{slug}.mp4"
            console.print(f"  Renderizando final -> {output_path}")
            mux_final(clip_vertical, clip_raw, clip_ass, output_path)
        recorder.end_stage("render")

        console.print(f"\n[bold green]Pronto! {len(highlight_list.highlights)} clipe(s) em {settings.output_dir}[/bold green]")
        logger.info("Run %s concluida com sucesso: %d clipe(s)", run_id, len(highlight_list.highlights))
        recorder.mark_success(len(highlight_list.highlights))
    except Exception as exc:
        console.print(f"[red]Erro no processamento.[/red] Arquivos parciais preservados em: {run_dir}")
        logger.exception("Run %s falhou", run_id)
        recorder.mark_error(str(exc))
        raise
    else:
        if not keep_temp:
            shutil.rmtree(run_dir, ignore_errors=True)


@app.command()
def doctor() -> None:
    """Verifica se as dependencias e configuracoes necessarias estao OK, sem rodar o pipeline."""
    ffmpeg_path = shutil.which("ffmpeg")
    checks = [
        ("ffmpeg no PATH", ffmpeg_path is not None, ffmpeg_path or "nao encontrado"),
        (
            "GEMINI_API_KEY configurada",
            bool(settings.gemini_api_key),
            "definida" if settings.gemini_api_key else "ausente no .env",
        ),
        ("work_dir gravavel", os.access(settings.work_dir, os.W_OK), str(settings.work_dir)),
        ("output_dir gravavel", os.access(settings.output_dir, os.W_OK), str(settings.output_dir)),
        ("log_dir gravavel", os.access(settings.log_dir, os.W_OK), str(settings.log_dir)),
    ]

    all_ok = True
    for label, ok, detail in checks:
        icon = "[green]OK[/green]  " if ok else "[red]FALHOU[/red]"
        console.print(f"{icon} {label} ({detail})")
        all_ok = all_ok and ok

    if not all_ok:
        console.print("\n[red]Um ou mais checks falharam.[/red] Corrija antes de rodar o pipeline.")
        raise typer.Exit(1)

    console.print("\n[bold green]Tudo OK.[/bold green]")


@app.command()
def stats() -> None:
    """Mostra estatisticas de execucao: shorts gerados hoje, execucoes com erro hoje e tempo medio por etapa."""
    conn = connect_history(settings.db_path)
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

    console.print(f"Shorts gerados hoje: {clips_today}")
    console.print(f"Execucoes com erro hoje: {errors_today}")

    console.print("\nTempo medio por etapa:")
    rows = conn.execute(
        "SELECT stage, AVG((julianday(finished_at) - julianday(started_at)) * 86400.0) AS avg_seconds "
        "FROM run_stages WHERE finished_at IS NOT NULL GROUP BY stage"
    ).fetchall()
    if not rows:
        console.print("  (sem dados ainda)")
    for row in rows:
        console.print(f"  {row['stage']}: {row['avg_seconds']:.1f}s")

    conn.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
