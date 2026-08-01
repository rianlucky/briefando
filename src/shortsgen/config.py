from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"

    whisper_model_size: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"

    work_dir: Path = Path("temp")
    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    db_path: Path = Path("data/shortsgen.db")

    max_clips: int = 5
    clip_min_seconds: int = 20
    clip_max_seconds: int = 90


settings = Settings()
settings.work_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
