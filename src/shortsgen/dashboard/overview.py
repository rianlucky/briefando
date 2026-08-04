from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.dashboard.components import CATEGORICAL_PALETTE, stat_card, trend_html
from shortsgen.history import (
    get_clips_counts,
    get_conversion_funnel,
    get_current_activity,
    get_daily_stats,
    get_queue_counts,
    get_resource_usage_for_range,
    get_stats_for_range,
)
from shortsgen.pipeline_runner import STAGE_LABELS

# Ordem fixa = ordem de execucao do pipeline (download -> transcricao ->
# highlights -> render), nao a ordem que o SQL GROUP BY devolve.
STAGE_ORDER = list(STAGE_LABELS.keys())
STAGE_LABELS_PT = {
    "download": "Download",
    "transcricao": "Transcrição",
    "highlights": "Highlights",
    "render": "Render",
}
# Rampa harmoniosa (tons de dourado da marca, claro -> escuro) so pro grafico de
# % por etapa - aqui as 4 fatias sao partes de UM todo (tempo total), nao
# categorias sem relacao, entao uma familia de cor so fica mais coesa que o
# CATEGORICAL_PALETTE (que e pra series realmente distintas, ex.: Analytics).
STAGE_HARMONY_PALETTE = ["#FDE0A0", "#FDBB11", "#F2994A", "#E8871E"]


def _format_seconds(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}m{secs:02d}s"


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return _format_seconds(seconds)


PERIOD_OPTIONS = ["Hoje", "Últimos 7 dias", "Este mês"]
QUEUE_ERROR_ALERT_THRESHOLD = 5


def _period_ranges(period: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """Intervalo atual e o intervalo equivalente imediatamente anterior, pra comparacao."""
    today = date.today()
    if period == "Hoje":
        cur_start = cur_end = today
        prev_start = prev_end = today - timedelta(days=1)
    elif period == "Últimos 7 dias":
        cur_start = today - timedelta(days=6)
        cur_end = today
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)
    else:  # "Este mês" - mes corrente ate hoje, vs mesmo numero de dias do mes anterior
        cur_start = today.replace(day=1)
        cur_end = today
        days_elapsed = (cur_end - cur_start).days
        prev_start = (cur_start - timedelta(days=1)).replace(day=1)
        prev_end = prev_start + timedelta(days=days_elapsed)
    return (cur_start.isoformat(), cur_end.isoformat()), (prev_start.isoformat(), prev_end.isoformat())


st.title("Visão Geral")


@st.fragment(run_every="1s")
def render_activity() -> None:
    activity = get_current_activity(settings.db_path)
    if activity is None:
        st.caption("Nenhuma execução em andamento no momento.")
        return

    stage_reference = activity["stage_started_at"] or activity["started_at"]
    elapsed_seconds = max(0, int((datetime.now() - datetime.fromisoformat(stage_reference)).total_seconds()))
    stage_label = STAGE_LABELS.get(activity["stage"], activity["stage"]) if activity["stage"] else "iniciando"

    stage_avg = get_daily_stats(settings.db_path)["stage_avgs"].get(activity["stage"])
    percent = min(0.99, elapsed_seconds / stage_avg) if stage_avg else 0.0

    st.info(f"**Rodando há {_format_seconds(elapsed_seconds)}:** {stage_label} — {activity['source']}")
    st.progress(percent, text=f"{percent * 100:.0f}%")


render_activity()
st.divider()

stats = get_daily_stats(settings.db_path)
queue = get_queue_counts(settings.db_path)
clips = get_clips_counts(settings.db_path, settings.min_quality_score)

if queue["error"] >= QUEUE_ERROR_ALERT_THRESHOLD:
    st.error(
        f"⚠️ **{queue['error']} itens com erro acumulados na fila.** Vale dar uma olhada na página "
        "Fila antes que vire bola de neve."
    )

period = st.selectbox("Período", PERIOD_OPTIONS, key="overview_period")
(cur_start, cur_end), (prev_start, prev_end) = _period_ranges(period)
current_period = get_stats_for_range(settings.db_path, cur_start, cur_end)
previous_period = get_stats_for_range(settings.db_path, prev_start, prev_end)
usage = get_resource_usage_for_range(settings.db_path, cur_start, cur_end)
compare_label = "vs período anterior" if period != "Hoje" else "vs ontem"

# Maior card (Fila, 4 linhas) define a altura - os demais sao preenchidos com
# linhas invisiveis ate bater nesse numero, pra ficarem todos do mesmo tamanho.
MAX_CARD_ROWS = 4

col_hoje, col_fila, col_pub, col_consumo = st.columns(4)
with col_hoje:
    stat_card(
        period,
        [
            (
                "Shorts gerados",
                current_period["clips"],
                trend_html(current_period["clips"], previous_period["clips"], True, compare_label),
            ),
            (
                "Execuções com erro",
                current_period["errors"],
                trend_html(current_period["errors"], previous_period["errors"], False, compare_label),
            ),
        ],
        min_rows=MAX_CARD_ROWS,
    )
with col_fila:
    stat_card(
        "Fila",
        [
            ("Pendentes", queue["pending"]),
            ("Rodando", queue["running"]),
            ("Com erro", queue["error"]),
            ("Concluídos", queue["done"]),
        ],
        min_rows=MAX_CARD_ROWS,
    )
with col_pub:
    stat_card(
        "Publicação",
        [
            ("Aguardando publicar", clips["pending"]),
            ("Aguardando revisão", clips["needs_review"]),
            ("Publicados", clips["published"]),
        ],
        min_rows=MAX_CARD_ROWS,
    )
with col_consumo:
    stat_card(
        f"Consumo ({period})",
        [
            ("Tokens Gemini (entrada)", f"{usage['input_tokens']:,}".replace(",", ".")),
            ("Tokens Gemini (saída)", f"{usage['output_tokens']:,}".replace(",", ".")),
            ("Tempo de máquina", _format_duration(usage["machine_seconds"])),
        ],
        min_rows=MAX_CARD_ROWS,
    )

st.divider()
st.subheader("Tempo médio por etapa")

if stats["stage_avgs"]:
    ordered_stages = [s for s in STAGE_ORDER if s in stats["stage_avgs"]]
    ordered_labels = [STAGE_LABELS_PT.get(s, s) for s in ordered_stages]
    seconds = [stats["stage_avgs"][s] for s in ordered_stages]

    df = pd.DataFrame({"Etapa": ordered_labels, "Segundos": seconds})
    df["Rótulo"] = df["Segundos"].apply(_format_seconds)

    bars = alt.Chart(df).mark_bar(color="#FDBB11", cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=48).encode(
        x=alt.X("Etapa:N", sort=ordered_labels, axis=alt.Axis(labelAngle=0, title=None)),
        y=alt.Y("Segundos:Q", axis=alt.Axis(title="Segundos", grid=True)),
        tooltip=[alt.Tooltip("Etapa:N"), alt.Tooltip("Segundos:Q", format=".0f")],
    )
    labels = alt.Chart(df).mark_text(dy=-10, color="#FFFFFF", fontWeight="bold").encode(
        x=alt.X("Etapa:N", sort=ordered_labels),
        y=alt.Y("Segundos:Q"),
        text="Rótulo:N",
    )
    chart = (
        (bars + labels)
        .properties(height=300)
        .configure_view(strokeWidth=0)
        .configure_axis(gridColor="rgba(128,128,128,0.2)", domainColor="rgba(128,128,128,0.4)")
    )
    st.altair_chart(chart, width="stretch")

    st.caption("% do tempo total gasto em cada etapa")
    total = sum(seconds)
    cumulative = 0.0
    rows = []
    # Pequeno respiro visual entre segmentos (arredondados nao ficam "colados").
    GAP = 0.4
    for label, s in zip(ordered_labels, seconds):
        pct = s / total * 100
        rows.append(
            {
                "Etapa": label,
                "Início": cumulative,
                "Fim": max(cumulative, cumulative + pct - GAP),
                "Percentual": pct,
                "Segundos": s,
            }
        )
        cumulative += pct
    df_pct = pd.DataFrame(rows)
    df_pct["Meio"] = (df_pct["Início"] + df_pct["Fim"]) / 2
    df_pct["Rótulo %"] = df_pct["Percentual"].apply(lambda p: f"{p:.0f}%")
    # Segmento estreito demais pro numero caber dentro - rotulo vai por cima em
    # vez de escondido (sem eixo embaixo, sobra espaço em cima pra isso).
    df_pct["Estreito"] = df_pct["Percentual"] < 8

    pct_bars = alt.Chart(df_pct).mark_bar(cornerRadius=6, height=40).encode(
        x=alt.X("Início:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=None),
        x2="Fim:Q",
        color=alt.Color(
            "Etapa:N",
            scale=alt.Scale(domain=ordered_labels, range=CATEGORICAL_PALETTE[: len(ordered_labels)]),
            sort=ordered_labels,
            legend=alt.Legend(orient="bottom", title=None),
        ),
        tooltip=[
            alt.Tooltip("Etapa:N"),
            alt.Tooltip("Percentual:Q", format=".1f", title="%"),
            alt.Tooltip("Segundos:Q", format=".0f"),
        ],
    )
    labels_inside = (
        alt.Chart(df_pct[~df_pct["Estreito"]])
        .mark_text(color="#030811", fontWeight="bold", align="center", baseline="middle")
        .encode(x=alt.X("Meio:Q"), text="Rótulo %:N")
    )
    labels_outside = (
        alt.Chart(df_pct[df_pct["Estreito"]])
        .mark_text(color="#FFFFFF", fontWeight="bold", align="center", dy=-14)
        .encode(x=alt.X("Meio:Q"), text="Rótulo %:N")
    )
    pct_chart = (
        (pct_bars + labels_inside + labels_outside)
        .properties(height=70)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(pct_chart, width="stretch")
else:
    st.info("Sem dados suficientes ainda.")

st.divider()
st.subheader(f"Funil de conversão ({period})")
st.caption(
    "Enfileirado → Processado → Aprovado → Publicado. Não inclui \"Descoberto\" (RSS) — "
    "vídeos filtrados antes de entrar na fila não ficam registrados neste banco."
)
funnel = get_conversion_funnel(settings.db_path, cur_start, cur_end, settings.min_quality_score)
funnel_stages = [f["stage"] for f in funnel]
df_funnel = pd.DataFrame(funnel)
df_funnel["Conversão"] = df_funnel["count"].apply(
    lambda c: f"{c / funnel[0]['count'] * 100:.0f}%" if funnel[0]["count"] else "—"
)

funnel_chart = (
    alt.Chart(df_funnel)
    .mark_bar(color="#FDBB11", cornerRadiusTopRight=4, cornerRadiusBottomRight=4, height=36)
    .encode(
        y=alt.Y("stage:N", sort=funnel_stages, title=None),
        x=alt.X("count:Q", title="Vídeos"),
        tooltip=[
            alt.Tooltip("stage:N", title="Etapa"),
            alt.Tooltip("count:Q", title="Vídeos"),
            alt.Tooltip("Conversão:N", title="% do enfileirado"),
        ],
    )
)
funnel_labels = (
    alt.Chart(df_funnel)
    .mark_text(align="left", dx=6, color="#FFFFFF", fontWeight="bold")
    .encode(
        y=alt.Y("stage:N", sort=funnel_stages),
        x=alt.X("count:Q"),
        text="Conversão:N",
    )
)
st.altair_chart(
    (funnel_chart + funnel_labels).properties(height=220).configure_view(strokeWidth=0),
    width="stretch",
)
