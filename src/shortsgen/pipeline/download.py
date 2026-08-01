from pathlib import Path
from typing import Callable

import yt_dlp


def download_video(
    url: str,
    out_dir: Path,
    on_progress: Callable[[dict], None] | None = None,
) -> tuple[Path, float | None]:
    """Baixa um video do YouTube (ou qualquer site suportado pelo yt-dlp) como mp4.

    `on_progress`, se dado, recebe o dict de status bruto do yt-dlp a cada
    atualizacao (ver `YoutubeDL` progress_hooks) - pode levantar
    `yt_dlp.utils.DownloadCancelled` pra abortar o download no meio.

    Retorna o caminho do video e a duracao em segundos (None se o yt-dlp nao
    souber informar).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "progress_hooks": [on_progress] if on_progress else [],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id = info["id"]
    video_path = out_dir / f"{video_id}.mp4"
    if not video_path.exists():
        candidates = list(out_dir.glob(f"{video_id}.*"))
        if not candidates:
            raise FileNotFoundError(f"yt-dlp nao produziu um arquivo para o video {video_id}")
        video_path = candidates[0]
    return video_path, info.get("duration")
