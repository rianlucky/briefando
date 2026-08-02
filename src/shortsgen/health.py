import os
import shutil
import sys

from shortsgen.config import settings


def run_checks() -> list[tuple[str, bool, str]]:
    """Checks de saude reutilizados pelo `doctor` (CLI) e pelo painel de status do TUI."""
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
    if sys.platform == "win32":
        checks.append(
            (
                "Modo UTF-8 do Python (Windows)",
                bool(sys.flags.utf8_mode),
                "ativo"
                if sys.flags.utf8_mode
                else "inativo - sem isso o SDK do Gemini corrompe titulos acentuados (perda "
                "irreversivel, nao e so exibicao). Rode 'setx PYTHONUTF8 1' e reabra o "
                "terminal (e o processo do n8n) antes de gerar clipes.",
            )
        )
    return checks
