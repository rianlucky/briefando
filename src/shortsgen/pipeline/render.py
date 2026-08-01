import subprocess
import time
from pathlib import Path

from shortsgen.exceptions import PipelineCancelled

_FFMPEG_TIMEOUT_SECONDS = 300
_POLL_INTERVAL_SECONDS = 0.25


def _run_ffmpeg(args: list[str], cancel_event=None) -> None:
    """Roda o ffmpeg via Popen (nao subprocess.run) pra poder verificar
    `cancel_event` periodicamente e matar o processo na hora se cancelado."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    process = subprocess.Popen(cmd)
    start = time.monotonic()
    try:
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                process.terminate()
                process.wait(timeout=10)
                raise PipelineCancelled("Cancelado durante o ffmpeg")
            if time.monotonic() - start > _FFMPEG_TIMEOUT_SECONDS:
                process.kill()
                process.wait(timeout=10)
                raise TimeoutError(f"ffmpeg excedeu {_FFMPEG_TIMEOUT_SECONDS}s")
            time.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        if process.poll() is None:
            process.kill()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)


def cut_segment(src: Path, start: float, end: float, dst: Path, cancel_event=None) -> None:
    """Corta um trecho do video original, re-codificando para garantir precisao no corte."""
    duration = max(0.1, end - start)
    _run_ffmpeg(
        [
            "-ss",
            f"{start}",
            "-i",
            str(src),
            "-t",
            f"{duration}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-avoid_negative_ts",
            "make_zero",
            str(dst),
        ],
        cancel_event=cancel_event,
    )


def _escape_ffmpeg_path(path: Path) -> str:
    # ffmpeg filtergraphs tratam ':' e '\' de forma especial, comum quebrar em paths do Windows.
    return str(path).replace("\\", "/").replace(":", r"\:")


def mux_final(
    vertical_video: Path, audio_source: Path, subtitles_ass: Path, dst: Path, cancel_event=None
) -> None:
    """Junta o video vertical (sem audio) + audio do clipe original + legendas queimadas."""
    ass_path = _escape_ffmpeg_path(subtitles_ass)
    _run_ffmpeg(
        [
            "-i",
            str(vertical_video),
            "-i",
            str(audio_source),
            "-filter_complex",
            f"[0:v]ass='{ass_path}'[v]",
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(dst),
        ],
        cancel_event=cancel_event,
    )
