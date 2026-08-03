from pathlib import Path

import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.history import approve_clip, list_clips

st.title("Clipes")

items = list_clips(settings.db_path)

if not items:
    st.info("Nenhum clipe encontrado ainda.")
else:
    df = pd.DataFrame(items)

    def _status_label(row) -> str:
        if row["published"]:
            return "🟢 Publicado"
        score = row.get("quality_score")
        if row.get("approved") or (score is not None and score >= settings.min_quality_score):
            return "🔵 Pendente de publicar"
        return "🟡 Aguardando revisão"

    df["status_label"] = df.apply(_status_label, axis=1)
    df = df.sort_values("created_at", ascending=False).reset_index(drop=True)

    col_search, col_status = st.columns([2, 1])
    search = col_search.text_input("Buscar por título", placeholder="Digite parte do título...")
    status_options = ["Todos", "🟢 Publicado", "🔵 Pendente de publicar", "🟡 Aguardando revisão"]
    status_filter = col_status.selectbox("Filtrar por status", status_options)

    view = df
    if status_filter != "Todos":
        view = view[view["status_label"] == status_filter]
    if search:
        view = view[view["title"].str.contains(search, case=False, na=False)]
    view = view.reset_index(drop=True)

    st.caption("👆 Clique numa linha da tabela pra ver o preview do clipe.")
    event = st.dataframe(
        view[["id", "title", "quality_score", "status_label", "created_at"]],
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "id": "ID",
            "title": "Título",
            "quality_score": st.column_config.NumberColumn("Score"),
            "status_label": "Status",
            "created_at": "Criado em",
        },
    )

    selected_rows = event.selection.rows if event.selection else []
    if selected_rows:
        clip = view.iloc[selected_rows[0]]
        st.divider()
        col_video, col_info = st.columns([1, 2])
        with col_video:
            st.subheader(clip["title"])
            if Path(clip["path"]).exists():
                # Clipes sao verticais (9:16) - largura fixa pra nao esticar
                # gigante numa coluna larga.
                st.video(clip["path"], width=300)
            else:
                st.warning("Arquivo do clipe não encontrado no disco (pode já ter sido limpo/apagado).")
        with col_info:
            st.write(f"**Status:** {clip['status_label']}")
            score = clip["quality_score"]
            st.write(f"**Score:** {score if score is not None else 'sem nota'}")
            if clip.get("description"):
                st.write("**Descrição:**")
                st.caption(clip["description"])
            if clip["status_label"] == "🟡 Aguardando revisão":
                if st.button("✅ Aprovar pra publicação", type="primary", width="stretch"):
                    approve_clip(settings.db_path, int(clip["id"]))
                    st.success("Clipe aprovado!")
                    st.rerun()
