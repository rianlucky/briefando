import re

import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.dashboard.components import run_status_badge
from shortsgen.history import get_recent_runs

_RECORD_START = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} (\w+) ")


def _filter_out_errors(lines: list[str]) -> list[str]:
    """Remove registros de nivel ERROR (e as linhas de traceback logo abaixo,
    que nao tem o prefixo de timestamp/nivel proprio) - so sobra log normal."""
    kept: list[str] = []
    skipping = False
    for line in lines:
        match = _RECORD_START.match(line)
        if match:
            skipping = match.group(1) == "ERROR"
            if not skipping:
                kept.append(line)
        elif not skipping:
            kept.append(line)
    return kept

st.title("Histórico")

st.subheader("Execuções")
limit = st.slider("Quantas execuções mostrar", 10, 200, 50, step=10)
runs = get_recent_runs(settings.db_path, limit=limit)

if runs:
    df = pd.DataFrame(runs)
    df["status_label"] = df["status"].apply(run_status_badge)
    st.dataframe(
        df[["run_id", "source", "status_label", "started_at", "finished_at", "clips_generated", "error_message"]],
        hide_index=True,
        width="stretch",
        column_config={
            "run_id": "Run ID",
            "source": "Fonte",
            "status_label": "Status",
            "started_at": "Início",
            "finished_at": "Fim",
            "clips_generated": st.column_config.NumberColumn("Clipes"),
            "error_message": "Erro",
        },
    )
else:
    st.info("Nenhuma execução registrada ainda.")

st.divider()
st.subheader("Log (últimas linhas)")
log_path = settings.log_dir / "shortsgen.log"
n_lines = st.slider("Quantas linhas", 20, 500, 100, step=20)

if log_path.exists():
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    info_lines = _filter_out_errors(lines)
    tail = "".join(info_lines[-n_lines:])
    st.code(tail or "(vazio)", language=None, wrap_lines=True)
else:
    st.info("Arquivo de log ainda não existe.")
