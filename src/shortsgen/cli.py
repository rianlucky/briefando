import logging

import typer
from rich.console import Console

from shortsgen.config import settings
from shortsgen.health import run_checks
from shortsgen.history import get_daily_stats
from shortsgen.logging_setup import configure_logging
from shortsgen.pipeline_runner import STAGE_LABELS, ProgressReporter, run_pipeline

app = typer.Typer(add_completion=False)
console = Console()
configure_logging(settings.log_dir)
logger = logging.getLogger(__name__)


class RichReporter(ProgressReporter):
    def __init__(self, console: Console) -> None:
        self.console = console

    def message(self, text: str) -> None:
        self.console.print(text)

    def stage_started(self, stage: str) -> None:
        self.console.print(f"[cyan]{STAGE_LABELS.get(stage, stage)}...[/cyan]")

    def run_finished(self, clips: int, output_dir) -> None:
        self.console.print(f"\n[bold green]Pronto! {clips} clipe(s) em {output_dir}[/bold green]")

    def run_failed(self, error: str, run_dir) -> None:
        self.console.print(f"[red]Erro no processamento.[/red] Arquivos parciais preservados em: {run_dir}")


@app.command()
def generate(
    source: str = typer.Argument(..., help="URL do YouTube ou caminho de um arquivo de video local"),
    max_clips: int = typer.Option(None, help="Numero maximo de clipes a gerar"),
    keep_temp: bool = typer.Option(False, help="Nao apagar os arquivos temporarios ao final"),
) -> None:
    """Gera shorts verticais com legenda a partir de um video (URL do YouTube ou arquivo local)."""
    if not settings.gemini_api_key:
        console.print("[red]Erro:[/red] GEMINI_API_KEY nao configurada. Defina-a no arquivo .env antes de rodar.")
        raise typer.Exit(1)

    run_pipeline(source, max_clips=max_clips, keep_temp=keep_temp, reporter=RichReporter(console))


@app.command()
def doctor() -> None:
    """Verifica se as dependencias e configuracoes necessarias estao OK, sem rodar o pipeline."""
    checks = run_checks()

    all_ok = True
    for label, ok, detail in checks:
        icon = "[green]OK[/green]  " if ok else "[red]FALHOU[/red]"
        console.print(f"{icon} {label} ({detail})")
        all_ok = all_ok and ok

    if not all_ok:
        console.print("\n[red]Um ou mais checks falharam.[/red] Corrija antes de rodar o pipeline.")
        raise typer.Exit(1)

    console.print("\n[bold green]Tudo OK.[/bold green]")


@app.command()
def stats() -> None:
    """Mostra estatisticas de execucao: shorts gerados hoje, execucoes com erro hoje e tempo medio por etapa."""
    data = get_daily_stats(settings.db_path)

    console.print(f"Shorts gerados hoje: {data['clips_today']}")
    console.print(f"Execucoes com erro hoje: {data['errors_today']}")

    console.print("\nTempo medio por etapa:")
    if not data["stage_avgs"]:
        console.print("  (sem dados ainda)")
    for stage, avg_seconds in data["stage_avgs"].items():
        console.print(f"  {stage}: {avg_seconds:.1f}s")


@app.command()
def tui() -> None:
    """Abre o painel interativo (Textual): status dos servicos, estatisticas do dia e execucao com progresso ao vivo."""
    from shortsgen.tui import BriefandoApp

    BriefandoApp().run()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
