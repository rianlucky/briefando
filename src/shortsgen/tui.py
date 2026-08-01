import logging
import threading
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, ProgressBar, RichLog, Static

from shortsgen.config import settings
from shortsgen.health import run_checks
from shortsgen.history import get_daily_stats
from shortsgen.logging_setup import configure_logging
from shortsgen.pipeline_runner import STAGE_LABELS, ProgressReporter, run_pipeline

configure_logging(settings.log_dir)
logger = logging.getLogger(__name__)

STATUS_REFRESH_SECONDS = 5
STATS_REFRESH_SECONDS = 5

CSS = """
#input-row {
    height: 3;
    padding: 0 1;
}

#source-input {
    width: 1fr;
}

#run-button, #cancel-button {
    width: auto;
    margin-left: 1;
}

#stage-label {
    height: 1;
    padding: 0 1;
    color: $text-muted;
}

#panels-row {
    height: auto;
    padding: 0 1;
}

.panel {
    border: round $primary;
    width: 1fr;
    padding: 0 1;
    height: auto;
}

.panel-title {
    text-style: bold;
}

#run-log {
    height: 1fr;
    border: round $primary;
    margin: 0 1;
}
"""


class TuiReporter(ProgressReporter):
    """Repassa eventos do pipeline pro app Textual, sempre via `call_from_thread`
    (o pipeline roda numa worker thread; widgets so podem ser tocados dali).

    Reportar pro painel e "melhor esforco": se o app ja foi fechado/desmontado
    (ex: usuario saiu do TUI com o run ainda rodando em background), a chamada
    pro widget falha - isso nunca pode virar o erro registrado no historico do
    pipeline, entao qualquer excecao aqui e so logada e ignorada.
    """

    def __init__(self, app: "BriefandoApp") -> None:
        self._app = app

    def _safe_call(self, callback, *args) -> None:
        try:
            self._app.call_from_thread(callback, *args)
        except Exception:
            logger.warning("Falha ao atualizar o painel (provavelmente ja fechado)", exc_info=True)

    def message(self, text: str) -> None:
        self._safe_call(self._app.append_log, text)

    def stage_started(self, stage: str) -> None:
        self._safe_call(self._app.set_stage, stage)

    def download_progress(self, percent: float) -> None:
        self._safe_call(self._app.set_percent_progress, percent)

    def transcription_progress(self, percent: float) -> None:
        self._safe_call(self._app.set_percent_progress, percent)

    def clip_progress(self, done: int, total: int) -> None:
        self._safe_call(self._app.set_clip_progress, done, total)

    def run_finished(self, clips: int, output_dir: Path) -> None:
        self._safe_call(self._app.handle_run_finished, clips, output_dir)

    def run_failed(self, error: str, run_dir: Path) -> None:
        self._safe_call(self._app.handle_run_failed, error, run_dir)

    def run_cancelled(self, run_dir: Path) -> None:
        self._safe_call(self._app.handle_run_cancelled, run_dir)


class BriefandoApp(App):
    """Painel interativo: status dos servicos, estatisticas do dia e execucao com progresso ao vivo."""

    TITLE = "Briefando"
    CSS = CSS
    BINDINGS = [("q", "quit", "Sair")]

    def __init__(self) -> None:
        super().__init__()
        self._job_running = False
        self._cancel_event: threading.Event | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="input-row"):
            yield Input(placeholder="URL do YouTube ou caminho de video local...", id="source-input")
            yield Button("Gerar", id="run-button", variant="primary")
            yield Button("Cancelar", id="cancel-button", variant="error", disabled=True)
        yield Static("Nenhuma execucao em andamento", id="stage-label")
        yield ProgressBar(id="clip-progress", show_eta=False)
        with Horizontal(id="panels-row"):
            with Vertical(classes="panel"):
                yield Static("Status dos servicos", classes="panel-title")
                yield Static(id="status-content")
            with Vertical(classes="panel"):
                yield Static("Estatisticas do dia", classes="panel-title")
                yield Static(id="stats-content")
        yield RichLog(id="run-log", wrap=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_status()
        self.refresh_stats()
        self.set_interval(STATUS_REFRESH_SECONDS, self.refresh_status)
        self.set_interval(STATS_REFRESH_SECONDS, self.refresh_stats)

    def refresh_status(self) -> None:
        lines = []
        for label, ok, detail in run_checks():
            icon = "[green]OK[/green]" if ok else "[red]FALHOU[/red]"
            lines.append(f"{icon} {label} ({detail})")
        self.query_one("#status-content", Static).update("\n".join(lines))

    def refresh_stats(self) -> None:
        data = get_daily_stats(settings.db_path)
        lines = [
            f"Shorts gerados hoje: {data['clips_today']}",
            f"Execucoes com erro hoje: {data['errors_today']}",
            "",
            "Tempo medio por etapa:",
        ]
        if not data["stage_avgs"]:
            lines.append("  (sem dados ainda)")
        else:
            lines.extend(f"  {stage}: {avg_seconds:.1f}s" for stage, avg_seconds in data["stage_avgs"].items())
        self.query_one("#stats-content", Static).update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-button":
            self._start_job()
        elif event.button.id == "cancel-button":
            self._cancel_job()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "source-input":
            self._start_job()

    def _start_job(self) -> None:
        if self._job_running:
            self.append_log("[yellow]Ja existe uma execucao em andamento.[/yellow]")
            return

        if not settings.gemini_api_key:
            self.append_log("[red]GEMINI_API_KEY nao configurada. Defina-a no .env antes de rodar.[/red]")
            return

        source = self.query_one("#source-input", Input).value.strip()
        if not source:
            return

        self._job_running = True
        self._cancel_event = threading.Event()
        self.query_one("#run-button", Button).disabled = True
        self.query_one("#cancel-button", Button).disabled = False
        self.query_one("#clip-progress", ProgressBar).update(total=100, progress=0)
        self.append_log(f"[bold]Iniciando:[/bold] {source}")
        self._run_job(source, self._cancel_event)

    def _cancel_job(self) -> None:
        if not self._job_running or self._cancel_event is None:
            return
        self._cancel_event.set()
        self.query_one("#cancel-button", Button).disabled = True
        self.append_log(
            "[yellow]Cancelamento solicitado - para no proximo ponto seguro "
            "(se estiver transcrevendo, so para quando a transcricao atual terminar).[/yellow]"
        )

    @work(thread=True)
    def _run_job(self, source: str, cancel_event: threading.Event) -> None:
        try:
            run_pipeline(source, reporter=TuiReporter(self), cancel_event=cancel_event)
        except Exception:
            logger.exception("Run disparado pelo TUI falhou")

    def append_log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.query_one("#run-log", RichLog).write(f"[dim]{timestamp}[/dim] {text}")

    def set_stage(self, stage: str) -> None:
        self.query_one("#stage-label", Static).update(f"Etapa atual: {STAGE_LABELS.get(stage, stage)}")

    def set_percent_progress(self, percent: float) -> None:
        self.query_one("#clip-progress", ProgressBar).update(total=100, progress=percent)

    def set_clip_progress(self, done: int, total: int) -> None:
        self.query_one("#clip-progress", ProgressBar).update(total=max(total, 1), progress=done)

    def _reset_job_state(self) -> None:
        self._job_running = False
        self._cancel_event = None
        self.query_one("#run-button", Button).disabled = False
        self.query_one("#cancel-button", Button).disabled = True
        self.query_one("#stage-label", Static).update("Nenhuma execucao em andamento")

    def handle_run_finished(self, clips: int, output_dir: Path) -> None:
        self.append_log(f"[bold green]Pronto! {clips} clipe(s) em {output_dir}[/bold green]")
        self._reset_job_state()
        self.refresh_stats()

    def handle_run_failed(self, error: str, run_dir: Path) -> None:
        self.append_log(f"[red]Erro: {error}[/red] (arquivos preservados em {run_dir})")
        self._reset_job_state()
        self.refresh_stats()

    def handle_run_cancelled(self, run_dir: Path) -> None:
        self.append_log(f"[yellow]Execucao cancelada.[/yellow] Arquivos parciais em {run_dir}")
        self._reset_job_state()
        self.refresh_stats()


def main() -> None:
    BriefandoApp().run()


if __name__ == "__main__":
    main()
