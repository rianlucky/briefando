import os
import shutil

from shortsgen.config import settings


def run_checks() -> list[tuple[str, bool, str]]:
    """Checks de saude reutilizados pelo `doctor` (CLI) e pelo painel de status do TUI."""
    ffmpeg_path = shutil.which("ffmpeg")
    return [
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
