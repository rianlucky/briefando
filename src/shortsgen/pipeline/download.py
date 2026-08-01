from pathlib import Path

import yt_dlp


def download_video(url: str, out_dir: Path) -> Path:
    """Baixa um video do YouTube (ou qualquer site suportado pelo yt-dlp) como mp4."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
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
    return video_path
