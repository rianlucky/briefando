import logging
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    """Loga em arquivo (persistente, pra depurar execucoes sem terminal aberto)
    junto com o console (rich ja cuida da UX interativa em cli.py)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_dir / "shortsgen.log", encoding="utf-8")],
    )
