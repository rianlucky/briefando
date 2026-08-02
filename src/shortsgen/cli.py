import logging

import typer
from rich.console import Console

from shortsgen.config import settings
from shortsgen.health import run_checks
from shortsgen.history import (
    DuplicateQueueItem,
    get_daily_stats,
    list_clips,
    list_queue,
    mark_clip_published,
    next_unpublished_clip,
    retry_queue_item,
)
from shortsgen.logging_setup import configure_logging
from shortsgen.pipeline_runner import STAGE_LABELS, ProgressReporter, run_pipeline
from shortsgen.queue import add_to_queue, archive_clip, cleanup_published_clips, run_queue

app = typer.Typer(add_completion=False)
queue_app = typer.Typer(add_completion=False, help="Fila de processamento: evita duplicatas e retoma apos interrupcao.")
app.add_typer(queue_app, name="queue")
clips_app = typer.Typer(add_completion=False, help="Clipes gerados e status de publicacao (marcado externamente, ex.: n8n).")
app.add_typer(clips_app, name="clips")
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
    """Abre o painel interativo (Textual), subindo n8n e o servidor de arquivos do output/ antes, se ainda nao estiverem rodando."""
    from shortsgen.services import ensure_http_server_running, ensure_n8n_running
    from shortsgen.tui import BriefandoApp

    if ensure_n8n_running():
        console.print("[cyan]Subindo n8n (janela propria)...[/cyan]")
    if ensure_http_server_running():
        console.print("[cyan]Subindo servidor de arquivos de output/ (janela propria)...[/cyan]")

    BriefandoApp().run()


@queue_app.command("add")
def queue_add(
    source: str = typer.Argument(..., help="URL do YouTube ou caminho de um arquivo de video local"),
) -> None:
    """Adiciona um source a fila de processamento."""
    try:
        item_id = add_to_queue(source)
    except DuplicateQueueItem as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1)
    console.print(f"[green]Adicionado a fila (id={item_id}).[/green]")


@queue_app.command("list")
def queue_list() -> None:
    """Lista os itens da fila (pendentes, rodando, concluidos e com erro)."""
    items = list_queue(settings.db_path)
    if not items:
        console.print("Fila vazia.")
        return
    for item in items:
        console.print(f"[{item['id']}] {item['status']:8} retries={item['retry_count']}  {item['source']}")


@queue_app.command("run")
def queue_run() -> None:
    """Processa a fila ate esvaziar (nao fica esperando novos itens - roda uma vez e sai)."""
    if not settings.gemini_api_key:
        console.print("[red]Erro:[/red] GEMINI_API_KEY nao configurada. Defina-a no arquivo .env antes de rodar.")
        raise typer.Exit(1)

    done, failed = run_queue(reporter_factory=lambda: RichReporter(console))
    console.print(f"\n[bold]Fila processada:[/bold] {done} concluido(s), {failed} com erro.")


@queue_app.command("retry")
def queue_retry(item_id: int = typer.Argument(..., help="ID do item na fila (ver 'queue list')")) -> None:
    """Reseta manualmente um item com erro terminal de volta pra pendente."""
    if retry_queue_item(settings.db_path, item_id):
        console.print(f"[green]Item {item_id} voltou pra fila.[/green]")
    else:
        console.print(f"[yellow]Item {item_id} nao encontrado ou nao esta em erro.[/yellow]")


@clips_app.command("list")
def clips_list(
    unpublished: bool = typer.Option(False, "--unpublished", help="Mostra so os clipes ainda nao publicados"),
) -> None:
    """Lista os clipes gerados e se ja foram marcados como publicados."""
    items = list_clips(settings.db_path, published=False if unpublished else None)
    if not items:
        console.print("Nenhum clipe encontrado.")
        return
    for item in items:
        status = "publicado" if item["published"] else "pendente"
        console.print(f"[{item['id']}] {status:10} {item['title']}  ({item['path']})")


@clips_app.command("next-pending")
def clips_next_pending() -> None:
    """Imprime o proximo clipe nao publicado em JSON puro (nada, se nao houver nenhum). Uso: automacao externa (n8n)."""
    clip = next_unpublished_clip(settings.db_path)
    if clip is not None:
        console.print_json(data=clip)


@clips_app.command("mark-published")
def clips_mark_published(
    clip_id: int = typer.Argument(..., help="ID do clipe (ver 'clips list')"),
    youtube_video_id: str = typer.Option(None, "--video-id", help="ID do video no YouTube, pra auditoria"),
) -> None:
    """Marca um clipe como publicado."""
    if mark_clip_published(settings.db_path, clip_id, youtube_video_id):
        console.print(f"[green]Clipe {clip_id} marcado como publicado.[/green]")
    else:
        console.print(f"[yellow]Clipe {clip_id} nao encontrado ou ja estava publicado.[/yellow]")


@clips_app.command("archive")
def clips_archive(clip_id: int = typer.Argument(..., help="ID do clipe (ver 'clips list')")) -> None:
    """Move o arquivo do clipe pra output/postado/ e atualiza o caminho no banco."""
    try:
        new_path = archive_clip(clip_id)
    except (ValueError, OSError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]Movido para {new_path}[/green]")


@clips_app.command("cleanup")
def clips_cleanup() -> None:
    """Apaga do disco os clipes publicados ha mais de CLIP_RETENTION_DAYS dias (padrao 10)."""
    deleted, missing = cleanup_published_clips()
    console.print(f"[green]{deleted} clipe(s) apagado(s).[/green] {missing} ja nao estavam no disco.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
