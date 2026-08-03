import pandas as pd
import streamlit as st

from shortsgen.config import settings
from shortsgen.history import add_source, build_youtube_feed_url, list_sources, remove_source

st.title("Fontes")
st.caption("Canais e playlists do YouTube monitorados pra descoberta automática de vídeos novos.")

sources = list_sources(settings.db_path, active_only=False)

if sources:
    df = pd.DataFrame(sources)
    st.dataframe(
        df[["id", "name", "feed_url", "delay_hours", "min_duration_seconds"]],
        hide_index=True,
        width="stretch",
        column_config={
            "id": "ID",
            "name": "Nome",
            "feed_url": "Feed RSS",
            "delay_hours": st.column_config.NumberColumn("Atraso (h)"),
            "min_duration_seconds": st.column_config.NumberColumn("Duração mín. (s)"),
        },
    )
else:
    st.info("Nenhuma fonte cadastrada ainda.")

st.divider()
st.subheader("Adicionar fonte")

with st.form("add_source_form", clear_on_submit=True):
    name = st.text_input("Nome (só pra identificar)")
    source_type = st.radio("Tipo", ["Canal", "Playlist"], horizontal=True)
    source_id_value = st.text_input(
        "ID do canal (UC...)" if source_type == "Canal" else "ID da playlist (PL...)"
    )
    col1, col2 = st.columns(2)
    delay_hours = col1.number_input("Atraso mínimo (horas)", min_value=0, value=24, step=1)
    min_duration = col2.number_input("Duração mínima (segundos)", min_value=0, value=180, step=10)

    submitted = st.form_submit_button("➕ Adicionar", type="primary")
    if submitted:
        if not name or not source_id_value:
            st.error("Preencha nome e ID.")
        else:
            feed_url = (
                build_youtube_feed_url(channel_id=source_id_value)
                if source_type == "Canal"
                else build_youtube_feed_url(playlist_id=source_id_value)
            )
            add_source(settings.db_path, name, feed_url, int(delay_hours), int(min_duration))
            st.success(f"Fonte '{name}' adicionada!")
            st.rerun()

if sources:
    st.divider()
    st.subheader("Remover fonte")
    options = {f"[{s['id']}] {s['name']}": s["id"] for s in sources}
    chosen_label = st.selectbox("Escolha a fonte", list(options.keys()))
    if st.button("🗑️ Remover", type="secondary"):
        remove_source(settings.db_path, options[chosen_label])
        st.success("Fonte removida.")
        st.rerun()
