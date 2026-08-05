from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.dashboard.components import CATEGORICAL_PALETTE, relative_time, stat_card
from shortsgen.history import (
    get_analytics_totals,
    get_category_breakdown,
    get_channel_stats_history,
    get_clip_analytics_history_bulk,
    get_engagement_rates,
    get_last_analytics_fetch,
    get_latest_channel_stats,
    get_publishing_cadence,
    get_quality_score_distribution,
    get_retention_summary,
    get_score_vs_performance,
    get_top_performing_titles,
    get_views_last_90_days,
    get_views_over_time_aggregate,
    get_weekday_performance,
)
from shortsgen.pipeline.highlights import YOUTUBE_CATEGORIES

_CATEGORY_NAMES = {v: k for k, v in YOUTUBE_CATEGORIES.items()}


def _fmt(n) -> str:
    return f"{n:,}".replace(",", ".") if n is not None else "—"


st.title("Analytics")
last_fetch = get_last_analytics_fetch(settings.db_path)
if last_fetch:
    st.caption(f"🕐 Última leitura de analytics: {relative_time(last_fetch)}")
st.caption(
    "CTR e impressões não aparecem aqui de propósito: a YouTube Analytics API não expõe "
    "esses dois campos para Shorts (confirmado via erro da API — limitação da própria "
    "plataforma, não do dashboard)."
)

totals = get_analytics_totals(settings.db_path)
channel = get_latest_channel_stats(settings.db_path)

col_totais, col_canal = st.columns(2)
with col_totais:
    stat_card(
        "Totais (todos os clipes)",
        [
            ("Views", _fmt(totals["total_views"])),
            ("Likes", _fmt(totals["total_likes"])),
            ("Comentários", _fmt(totals["total_comments"])),
            ("Clipes com analytics", _fmt(totals["clips_com_analytics"])),
        ],
    )
with col_canal:
    if channel:
        stat_card(
            f"Canal (lido {relative_time(channel['fetched_at'])})",
            [
                ("Inscritos", _fmt(channel["subscriber_count"])),
                ("Views totais do canal", _fmt(channel["total_views"])),
                ("Vídeos publicados", _fmt(channel.get("video_count"))),
            ],
        )
    else:
        stat_card("Canal", [("Inscritos", "sem dado ainda"), ("Views totais do canal", "sem dado ainda")])

st.divider()
st.subheader("🎯 Meta: Monetização (YouTube Partner Program — Shorts)")
st.caption(
    "Requisito real do YouTube: 1.000 inscritos + 10.000.000 de views em Shorts nos "
    "últimos 90 dias. Views já filtrado pra essa janela (aproximado — nossos dados são "
    "leituras periódicas, não views dia-a-dia exatas; ver `get_views_last_90_days`)."
)
_META_INSCRITOS = 1_000
_META_VIEWS = 10_000_000
current_subs = channel["subscriber_count"] if channel else 0
current_views = get_views_last_90_days(settings.db_path)

col_meta_subs, col_meta_views = st.columns(2)
with col_meta_subs:
    pct_subs = min(1.0, current_subs / _META_INSCRITOS)
    st.write(f"**Inscritos:** {_fmt(current_subs)} / {_fmt(_META_INSCRITOS)}")
    st.progress(pct_subs, text=f"{pct_subs * 100:.1f}%")
with col_meta_views:
    pct_views = min(1.0, current_views / _META_VIEWS)
    st.write(f"**Views (últimos 90 dias):** {_fmt(current_views)} / {_fmt(_META_VIEWS)}")
    st.progress(pct_views, text=f"{pct_views * 100:.1f}%")

st.divider()
top10_for_ratios = get_top_performing_titles(settings.db_path, limit=10)
top10_views_sum = sum(c["views"] for c in top10_for_ratios) if top10_for_ratios else 0
avg_views_per_short = (
    totals["total_views"] / totals["clips_com_analytics"] if totals["clips_com_analytics"] else 0
)
subs_per_1000_views = (
    (channel["subscriber_count"] / totals["total_views"]) * 1000
    if channel and totals["total_views"]
    else None
)
pct_views_top10 = (top10_views_sum / totals["total_views"] * 100) if totals["total_views"] else 0

col_avg, col_subs_ratio, col_concentracao = st.columns(3)
with col_avg:
    stat_card("📈 Média de views por Short", [("Média", f"{avg_views_per_short:,.0f}".replace(",", "."))])
with col_subs_ratio:
    stat_card(
        "👥 Inscritos por 1.000 views",
        [("Taxa", f"{subs_per_1000_views:.2f}" if subs_per_1000_views is not None else "sem dado de inscritos")],
    )
with col_concentracao:
    stat_card("📊 % das views vindas do Top 10 Shorts", [("Concentração", f"{pct_views_top10:.1f}%")])

st.divider()
col_views_tempo, col_inscritos_tempo = st.columns(2)
with col_views_tempo:
    st.subheader("Views totais ao longo do tempo")
    views_over_time = get_views_over_time_aggregate(settings.db_path)
    if views_over_time:
        df_vt = pd.DataFrame(views_over_time)
        chart = (
            alt.Chart(df_vt)
            .mark_line(point=True, color="#FDBB11", strokeWidth=2)
            .encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("total_views:Q", title="Views totais"),
                tooltip=[alt.Tooltip("date:T", title="Data"), alt.Tooltip("total_views:Q", title="Views")],
            )
            .properties(height=280)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Sem dados de analytics ainda.")
with col_inscritos_tempo:
    st.subheader("Inscritos ao longo do tempo")
    channel_history = get_channel_stats_history(settings.db_path)
    if channel_history:
        df_ch = pd.DataFrame(channel_history)
        chart = (
            alt.Chart(df_ch)
            .mark_line(point=True, color="#FDBB11", strokeWidth=2)
            .encode(
                x=alt.X("fetched_at:T", title=None),
                y=alt.Y("subscriber_count:Q", title="Inscritos"),
                tooltip=[alt.Tooltip("fetched_at:T", title="Data"), alt.Tooltip("subscriber_count:Q", title="Inscritos")],
            )
            .properties(height=280)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info(
            "Sem dados ainda — precisa de um passo no n8n chamando `shortsgen channel record-stats "
            "<inscritos> <views>` com o resultado da YouTube Data API (`channels.list`)."
        )

st.divider()
st.subheader("Melhores títulos (por views)")
top = get_top_performing_titles(settings.db_path, limit=10)
if top:
    df_top = pd.DataFrame(top)
    chart = (
        alt.Chart(df_top)
        .mark_bar(color="#FDBB11", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            y=alt.Y("title:N", sort="-x", title=None),
            x=alt.X("views:Q", title="Views"),
            tooltip=[alt.Tooltip("title:N", title="Título"), alt.Tooltip("views:Q", title="Views")],
        )
        .properties(height=max(200, 32 * len(df_top)))
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, width="stretch")
else:
    st.info("Sem dados de analytics ainda.")

st.divider()
st.subheader("Taxa de engajamento (likes + comentários / views)")
st.caption("Views é puxado pelo algoritmo — taxa de engajamento diz mais sobre a qualidade real do conteúdo.")
engagement = get_engagement_rates(settings.db_path, limit=10)
if engagement:
    df_eng = pd.DataFrame(engagement)
    df_eng["engagement_pct"] = df_eng["engagement_rate"] * 100
    chart = (
        alt.Chart(df_eng)
        .mark_bar(color="#FDBB11", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            y=alt.Y("title:N", sort="-x", title=None),
            x=alt.X("engagement_pct:Q", title="Taxa de engajamento (%)"),
            tooltip=[
                alt.Tooltip("title:N", title="Título"),
                alt.Tooltip("engagement_pct:Q", title="Taxa", format=".2f"),
                alt.Tooltip("views:Q", title="Views"),
                alt.Tooltip("likes:Q", title="Likes"),
                alt.Tooltip("comments:Q", title="Comentários"),
            ],
        )
        .properties(height=max(200, 32 * len(df_eng)))
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, width="stretch")
else:
    st.info("Sem dados de analytics ainda.")

st.divider()
st.subheader("Score do Gemini × Views reais")
st.caption("Cada ponto é um clipe — ajuda a ver se a nota prevê performance de verdade.")
score_perf = get_score_vs_performance(settings.db_path)
if score_perf:
    df_sp = pd.DataFrame(score_perf)
    points = alt.Chart(df_sp).mark_circle(color="#FDBB11", size=120, opacity=0.75).encode(
        x=alt.X("quality_score:Q", title="Quality Score", scale=alt.Scale(domain=[70, 100])),
        y=alt.Y("views:Q", title="Views"),
        tooltip=[
            alt.Tooltip("title:N", title="Título"),
            alt.Tooltip("quality_score:Q", title="Score"),
            alt.Tooltip("views:Q", title="Views"),
        ],
    )
    layers = points
    if df_sp["quality_score"].nunique() >= 2:
        trend = (
            alt.Chart(df_sp)
            .transform_regression("quality_score", "views")
            .mark_line(color="#FFFFFF", strokeDash=[4, 4], strokeWidth=2)
            .encode(x="quality_score:Q", y="views:Q")
        )
        layers = points + trend

        correlation = df_sp["quality_score"].corr(df_sp["views"])
        st.caption(f"Correlação (Pearson) entre score e views: **{correlation:.2f}**")

    chart = layers.properties(height=350).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
else:
    st.info("Sem clipes com score e métricas suficientes ainda.")

st.divider()
st.subheader("Views por dias desde a publicação (top 5)")
st.caption(
    "Eixo X = dias desde que o clipe foi publicado (analise de coorte) — assim um clipe "
    "publicado hoje e um publicado ha semanas ficam comparaveis no mesmo grafico."
)
top5 = get_top_performing_titles(settings.db_path, limit=5)
if top5:
    history_by_clip = get_clip_analytics_history_bulk(settings.db_path, [clip["clip_id"] for clip in top5])
    frames = []
    for clip in top5:
        if not clip["published_at"]:
            continue
        published_at = datetime.fromisoformat(clip["published_at"])
        for row in history_by_clip[clip["clip_id"]]:
            if row["views"] is not None:
                days_since = (datetime.fromisoformat(row["fetched_at"]) - published_at).days
                frames.append({"Título": clip["title"], "Dias desde publicação": max(0, days_since), "Views": row["views"]})

    if frames:
        df_hist = pd.DataFrame(frames)
        chart = (
            alt.Chart(df_hist)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                x=alt.X("Dias desde publicação:Q", title="Dias desde publicação"),
                y=alt.Y("Views:Q"),
                color=alt.Color("Título:N", scale=alt.Scale(range=CATEGORICAL_PALETTE), legend=alt.Legend(orient="bottom")),
                tooltip=["Título", "Dias desde publicação", "Views"],
            )
            .properties(height=350)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Ainda só tem uma leitura de métricas por clipe — volte aqui depois de mais dias de histórico.")
else:
    st.info("Sem dados suficientes ainda.")

st.divider()
col_categoria, col_score_dist = st.columns(2)
with col_categoria:
    st.subheader("Clipes por categoria")
    categories = get_category_breakdown(settings.db_path)
    if categories:
        df_cat = pd.DataFrame(categories)
        df_cat["Categoria"] = df_cat["category_id"].apply(lambda c: _CATEGORY_NAMES.get(c, c))
        chart = (
            alt.Chart(df_cat)
            .mark_bar(color="#FDBB11", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
            .encode(
                y=alt.Y("Categoria:N", sort="-x", title=None),
                x=alt.X("total:Q", title="Clipes"),
                tooltip=[alt.Tooltip("Categoria:N"), alt.Tooltip("total:Q", title="Clipes")],
            )
            .properties(height=max(150, 32 * len(df_cat)))
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Sem clipes ainda.")
with col_score_dist:
    st.subheader("Distribuição de Quality Score")
    scores = get_quality_score_distribution(settings.db_path)
    if scores:
        df_scores = pd.DataFrame(scores)
        chart = (
            alt.Chart(df_scores)
            .mark_bar(color="#FDBB11")
            .encode(
                x=alt.X("quality_score:Q", bin=alt.Bin(step=5), title="Score"),
                y=alt.Y("count():Q", title="Clipes"),
                tooltip=[alt.Tooltip("count():Q", title="Clipes")],
            )
            .properties(height=280)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Sem clipes com score ainda.")

st.divider()
st.subheader("Retenção média (top 10)")
st.caption("% médio do clipe assistido — visto por quem publica como sinal mais forte de qualidade real do que views.")
retention = get_retention_summary(settings.db_path, limit=10)
if retention:
    df_ret = pd.DataFrame(retention)
    chart = (
        alt.Chart(df_ret)
        .mark_bar(color="#FDBB11", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            y=alt.Y("title:N", sort="-x", title=None),
            x=alt.X("average_view_percentage:Q", title="Retenção média (%)"),
            tooltip=[
                alt.Tooltip("title:N", title="Título"),
                alt.Tooltip("average_view_percentage:Q", title="Retenção", format=".1f"),
                alt.Tooltip("views:Q", title="Views"),
            ],
        )
        .properties(height=max(200, 32 * len(df_ret)))
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, width="stretch")
else:
    st.info("Sem dado de retenção ainda (vem da YouTube Analytics API).")

st.divider()
col_weekday, col_cadence = st.columns(2)
_WEEKDAY_NAMES = {"0": "Domingo", "1": "Segunda", "2": "Terça", "3": "Quarta", "4": "Quinta", "5": "Sexta", "6": "Sábado"}
with col_weekday:
    st.subheader("Performance por dia da semana")
    st.caption("Views médias (leitura mais recente) dos clipes publicados em cada dia da semana.")
    weekday = get_weekday_performance(settings.db_path)
    if weekday:
        df_wd = pd.DataFrame(weekday)
        df_wd["Dia"] = df_wd["weekday"].map(_WEEKDAY_NAMES)
        order = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
        chart = (
            alt.Chart(df_wd)
            .mark_bar(color="#FDBB11", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("Dia:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("avg_views:Q", title="Views médias"),
                tooltip=[
                    alt.Tooltip("Dia:N"),
                    alt.Tooltip("avg_views:Q", title="Views médias", format=".0f"),
                    alt.Tooltip("n:Q", title="Clipes"),
                ],
            )
            .properties(height=280)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Sem dados suficientes ainda.")
with col_cadence:
    st.subheader("Ritmo de publicação")
    st.caption("Quantos clipes foram publicados por dia.")
    cadence = get_publishing_cadence(settings.db_path)
    if cadence:
        df_cad = pd.DataFrame(cadence)
        chart = (
            alt.Chart(df_cad)
            .mark_bar(color="#FDBB11", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("dia:T", title=None),
                y=alt.Y("total:Q", title="Clipes publicados"),
                tooltip=[alt.Tooltip("dia:T", title="Dia"), alt.Tooltip("total:Q", title="Clipes")],
            )
            .properties(height=280)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Sem clipes publicados ainda.")
