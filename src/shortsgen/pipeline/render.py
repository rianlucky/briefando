import subprocess
from pathlib import Path

_FFMPEG_TIMEOUT_SECONDS = 300


def _run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    subprocess.run(cmd, check=True, timeout=_FFMPEG_TIMEOUT_SECONDS)


def cut_segment(src: Path, start: float, end: float, dst: Path) -> None:
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
        ]
    )


def _escape_ffmpeg_path(path: Path) -> str:
    # ffmpeg filtergraphs tratam ':' e '\' de forma especial, comum quebrar em paths do Windows.
    return str(path).replace("\\", "/").replace(":", r"\:")


def mux_final(vertical_video: Path, audio_source: Path, subtitles_ass: Path, dst: Path) -> None:
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
        ]
    )
