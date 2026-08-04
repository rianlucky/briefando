"""Componentes visuais compartilhados entre as paginas do dashboard - um vocabulario
visual so (card HTML com fundo navy/borda sutil), em vez de misturar com st.metric
nativo em paginas diferentes."""

from datetime import datetime

import streamlit as st

# Paleta categorica (ordem fixa, validada pra distincao em daltonismo) -
# compartilhada entre paginas pra nao duplicar/divergir (ex.: 4 cores num
# lugar, 5 em outro). Cada consumidor fatia so quantas cores precisa.
CATEGORICAL_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def trend_html(current: int, previous: int, higher_is_better: bool, compare_label: str) -> str:
    delta = current - previous
    if delta == 0:
        return f"<span style='color:rgba(255,255,255,0.45); font-size:0.8rem;'>— {compare_label}</span>"
    is_good = (delta > 0) == higher_is_better
    color = "#1baf7a" if is_good else "#e5484d"
    arrow = "▲" if delta > 0 else "▼"
    return f"<span style='color:{color}; font-size:0.8rem;'>{arrow}{abs(delta)} {compare_label}</span>"


def stat_row(label: str, value, trend: str | None = None) -> str:
    # Sempre reserva a altura da linha de tendencia, mesmo vazia - senao uma
    # linha com tendencia fica mais alta que uma sem, e cards com/sem trend
    # deixam de bater em altura mesmo tendo a mesma quantidade de linhas.
    trend_block = f"<div style='text-align:right; min-height:1.1em;'>{trend or '&nbsp;'}</div>"
    return (
        "<div style='display:flex; justify-content:space-between; align-items:center; "
        "padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.08);'>"
        f"<span style='color:rgba(255,255,255,0.75);'>{label}</span>"
        "<div>"
        f"<span style='color:#FDBB11; font-weight:700; font-size:1.05rem;'>{value}</span>"
        f"{trend_block}"
        "</div>"
        "</div>"
    )


def _blank_stat_row() -> str:
    """Linha invisivel, com a MESMA estrutura de uma stat_row real (rotulo +
    valor + linha de tendencia) - usada so pra preencher cards mais curtos ate
    a mesma quantidade de linhas dos outros da mesma fileira, garantindo altura
    igual mesmo quando algumas linhas tem tendencia e outras nao."""
    return f"<div style='visibility:hidden;'>{stat_row('&nbsp;', '&nbsp;')}</div>"


def stat_card(title: str, rows: list[tuple], min_rows: int = 0) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        html = "".join(stat_row(*row) for row in rows)
        html += _blank_stat_row() * max(0, min_rows - len(rows))
        st.markdown(html, unsafe_allow_html=True)


QUEUE_STATUS_BADGES = {
    "pending": "⚪ Pendente",
    "running": "🟡 Rodando",
    "done": "🟢 Concluído",
    "error": "🔴 Erro",
}


def queue_status_badge(status: str) -> str:
    return QUEUE_STATUS_BADGES.get(status, status)


RUN_STATUS_BADGES = {
    "running": "🟡 Rodando",
    "success": "🟢 Sucesso",
    "error": "🔴 Erro",
    "cancelled": "⚫ Cancelado",
}


def run_status_badge(status: str) -> str:
    return RUN_STATUS_BADGES.get(status, status)


def relative_time(iso_timestamp: str) -> str:
    """'ha Xh'/'ha X min'/'ha X dia(s)' a partir de um timestamp ISO - usado pra
    indicar quando um dado que atualiza com pouca frequencia foi lido por ultimo."""
    elapsed = datetime.now() - datetime.fromisoformat(iso_timestamp)
    minutes = int(elapsed.total_seconds() // 60)
    if minutes < 1:
        return "agora mesmo"
    if minutes < 60:
        return f"há {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"há {hours}h"
    days = hours // 24
    return f"há {days} dia{'s' if days != 1 else ''}"
