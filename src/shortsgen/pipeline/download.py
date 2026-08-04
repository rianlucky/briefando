from pathlib import Path
from typing import Callable

import yt_dlp

from shortsgen.config import settings


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
        # "quiet" so suprime mensagens - a barra de progresso interna do
        # yt-dlp e um mecanismo separado e continuava tentando escrever no
        # stream do processo. Quando isso roda sem um console de verdade (via
        # n8n/Execute Command), essa escrita quebra com "OSError: [Errno 22]
        # Invalid argument" e derruba o download inteiro. Progresso real ja
        # vem do nosso proprio `on_progress` hook, entao a barra do yt-dlp nao
        # faz falta nenhuma.
        "noprogress": True,
        "socket_timeout": 30,
        # Sempre um video so - sem isso, uma URL com "&list=" (ex.: copiada de
        # dentro de uma playlist) baixa a playlist inteira antes de falhar,
        # porque o "video_id" resolvido vira o ID da playlist, nao do video.
        "noplaylist": True,
        "progress_hooks": [on_progress] if on_progress else [],
        # YouTube exige resolver um desafio anti-throttling (n-challenge) via
        # JS pra liberar a maioria dos formatos - sem isso, so sobra thumbnail.
        # Node ja esta instalado nesta maquina (usado tambem pelo n8n).
        "js_runtimes": {"node": {}},
    }
    if settings.ytdlp_cookies_file:
        ydl_opts["cookiefile"] = settings.ytdlp_cookies_file
    elif settings.ytdlp_cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (settings.ytdlp_cookies_from_browser,)
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
