import logging
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, ProgressBar, Static

from shortsgen.config import settings
from shortsgen.health import run_checks
from shortsgen.history import (
    get_clips_counts,
    get_current_activity,
    get_daily_stats,
    get_queue_counts,
    get_recent_runs,
)
from shortsgen.logging_setup import configure_logging
from shortsgen.pipeline_runner import STAGE_LABELS

configure_logging(settings.log_dir)
logger = logging.getLogger(__name__)

STATUS_REFRESH_SECONDS = 5
STATS_REFRESH_SECONDS = 5
QUEUE_REFRESH_SECONDS = 5
ACTIVITY_REFRESH_SECONDS = 3

CSS = """
#activity-label {
    height: 1;
    padding: 0 1;
    color: $text-muted;
}

#panels-row, #panels-row-2 {
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

#recent-runs {
    height: 1fr;
    border: round $primary;
    margin: 0 1;
    padding: 0 1;
}
"""


def _elapsed_seconds(iso_ts: str) -> int:
    started = datetime.fromisoformat(iso_ts)
    return max(0, int((datetime.now() - started).total_seconds()))


def _format_elapsed(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m{secs:02d}s"


class BriefandoApp(App):
    """Painel de monitoramento: status dos servicos, estatisticas, fila,
    publicacao e atividade atual do pipeline - tudo alimentado pela fila
    (`shortsgen queue run`, disparado externamente, ex.: n8n). Nao dispara
    execucoes por aqui - so observa o que ja esta rodando via banco de dados."""

    TITLE = "Briefando"
    CSS = CSS
    BINDINGS = [("q", "quit", "Sair")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Nenhuma execucao em andamento", id="activity-label")
        yield ProgressBar(id="activity-progress", show_eta=False)
        with Horizontal(id="panels-row"):
            with Vertical(classes="panel"):
                yield Static("Status dos servicos", classes="panel-title")
                yield Static(id="status-content")
            with Vertical(classes="panel"):
                yield Static("Estatisticas do dia", classes="panel-title")
                yield Static(id="stats-content")
        with Horizontal(id="panels-row-2"):
            with Vertical(classes="panel"):
                yield Static("Fila", classes="panel-title")
                yield Static(id="queue-content")
            with Vertical(classes="panel"):
                yield Static("Publicacao", classes="panel-title")
                yield Static(id="clips-content")
        yield Static("Execucoes recentes", classes="panel-title")
        yield Static(id="recent-runs")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_status()
        self.refresh_stats()
        self.refresh_queue()
        self.refresh_activity()
        self.set_interval(STATUS_REFRESH_SECONDS, self.refresh_status)
        self.set_interval(STATS_REFRESH_SECONDS, self.refresh_stats)
        self.set_interval(QUEUE_REFRESH_SECONDS, self.refresh_queue)
        self.set_interval(ACTIVITY_REFRESH_SECONDS, self.refresh_activity)

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

    def refresh_queue(self) -> None:
        queue = get_queue_counts(settings.db_path)
        queue_lines = [
            f"Pendentes: {queue['pending']}",
            f"Rodando: {queue['running']}",
            f"Concluidos: {queue['done']}",
            f"Com erro: {queue['error']}",
        ]
        self.query_one("#queue-content", Static).update("\n".join(queue_lines))

        clips = get_clips_counts(settings.db_path, settings.min_quality_score)
        clips_lines = [
            f"Aguardando publicar: {clips['pending']}",
            f"Aguardando revisao: {clips['needs_review']}",
            f"Publicados: {clips['published']}",
        ]
        self.query_one("#clips-content", Static).update("\n".join(clips_lines))

        runs = get_recent_runs(settings.db_path)
        run_lines = []
        for run in runs:
            icon = {"success": "[green]OK[/green]", "error": "[red]ERRO[/red]", "running": "[cyan]RODANDO[/cyan]", "cancelled": "[yellow]CANCELADO[/yellow]"}.get(
                run["status"], run["status"]
            )
            run_lines.append(f"{icon}  {run['started_at']}  {run['source']}")
        self.query_one("#recent-runs", Static).update("\n".join(run_lines) if run_lines else "Nenhuma execucao ainda.")

    def refresh_activity(self) -> None:
        activity = get_current_activity(settings.db_path)
        progress_bar = self.query_one("#activity-progress", ProgressBar)

        if activity is None:
            self.query_one("#activity-label", Static).update("Nenhuma execucao em andamento")
            progress_bar.update(total=100, progress=0)
            return

        stage_label = STAGE_LABELS.get(activity["stage"], activity["stage"]) if activity["stage"] else "iniciando"
        stage_reference = activity["stage_started_at"] or activity["started_at"]
        elapsed_seconds = _elapsed_seconds(stage_reference)
        self.query_one("#activity-label", Static).update(
            f"Rodando ha {_format_elapsed(elapsed_seconds)}: {stage_label} - {activity['source']}"
        )

        # Estimativa (nao exata): elapsed da etapa atual / media historica dessa
        # mesma etapa - mesma logica que o pipeline ja usa pra estimar a
        # transcricao, so que aqui olhando o banco em vez de callback em memoria.
        stage_avg = get_daily_stats(settings.db_path)["stage_avgs"].get(activity["stage"])
        percent = min(99.0, elapsed_seconds / stage_avg * 100) if stage_avg else 0.0
        progress_bar.update(total=100, progress=percent)


def main() -> None:
    BriefandoApp().run()


if __name__ == "__main__":
    main()
