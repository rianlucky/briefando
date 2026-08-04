from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Sobe a partir deste arquivo ate achar o pyproject.toml (raiz do projeto).

    Evita que temp/output/logs/data (e o .env) sejam resolvidos relativos ao
    cwd de onde o comando foi chamado - por exemplo, rodar o CLI de dentro da
    pasta output/ por engano recriaria toda essa estrutura ali dentro.
    """
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _project_root()


def _anchor(path: Path) -> Path:
    """Ancora um caminho relativo na raiz do projeto; caminhos absolutos (ex:
    o usuario apontando pra outro disco no .env) passam direto."""
    return path if path.is_absolute() else PROJECT_ROOT / path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout_seconds: int = 300

    whisper_model_size: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    whisper_cpu_threads: int = 4

    work_dir: Path = Path("temp")
    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    db_path: Path = Path("data/shortsgen.db")

    max_clips: int = 5
    clip_min_seconds: int = 20
    clip_max_seconds: int = 90

    queue_max_retries: int = 3
    clip_retention_days: int = 10

    pipeline_retry_attempts: int = 3
    pipeline_retry_delay_seconds: float = 5.0
    gemini_retry_delay_seconds: float = 30.0

    min_quality_score: int = 60
    min_history_for_learning: int = 3

    ytdlp_cookies_from_browser: str | None = None
    ytdlp_cookies_file: str | None = None


settings = Settings()
settings.work_dir = _anchor(settings.work_dir)
settings.output_dir = _anchor(settings.output_dir)
settings.log_dir = _anchor(settings.log_dir)
settings.db_path = _anchor(settings.db_path)

settings.work_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
