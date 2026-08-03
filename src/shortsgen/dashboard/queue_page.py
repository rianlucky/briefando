import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.dashboard.components import queue_status_badge, stat_card
from shortsgen.history import list_queue, retry_queue_item

st.title("Fila")

items = list_queue(settings.db_path)

if not items:
    st.info("Fila vazia.")
else:
    df = pd.DataFrame(items)
    status_counts = df["status"].value_counts().to_dict()

    stat_card(
        "Status da fila",
        [
            ("Pendentes", status_counts.get("pending", 0)),
            ("Rodando", status_counts.get("running", 0)),
            ("Concluídos", status_counts.get("done", 0)),
            ("Com erro", status_counts.get("error", 0)),
        ],
    )

    st.divider()

    df["status_label"] = df["status"].apply(queue_status_badge)

    status_options = ["Todos", "pending", "running", "done", "error"]
    status_filter = st.selectbox(
        "Filtrar por status",
        status_options,
        format_func=lambda s: "Todos" if s == "Todos" else queue_status_badge(s),
    )
    view = df if status_filter == "Todos" else df[df["status"] == status_filter]

    st.dataframe(
        view[["id", "status_label", "retry_count", "source", "error_message"]],
        hide_index=True,
        width="stretch",
        column_config={
            "id": "ID",
            "status_label": "Status",
            "retry_count": "Tentativas",
            "source": "Fonte",
            "error_message": "Erro",
        },
    )

    error_items = df[df["status"] == "error"]
    if not error_items.empty:
        st.divider()
        st.subheader("Reenfileirar item com erro")
        chosen = st.selectbox("ID do item", error_items["id"].tolist())
        if st.button("🔁 Tentar de novo", type="primary"):
            retry_queue_item(settings.db_path, int(chosen))
            st.success(f"Item {chosen} voltou pra fila.")
            st.rerun()
