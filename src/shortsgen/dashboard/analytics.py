from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.dashboard.components import CATEGORICAL_PALETTE, relative_time
from shortsgen.history import (
    get_clip_analytics_history_bulk,
    get_engagement_rates,
    get_last_analytics_fetch,
    get_score_vs_performance,
    get_top_performing_titles,
)

st.title("Analytics")
last_fetch = get_last_analytics_fetch(settings.db_path)
if last_fetch:
    st.caption(f"🕐 Última leitura de analytics: {relative_time(last_fetch)}")
st.caption(
    "CTR e impressões não aparecem aqui de propósito: a YouTube Analytics API não expõe "
    "esses dois campos para Shorts (confirmado via erro da API — limitação da própria "
    "plataforma, não do dashboard)."
)

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
