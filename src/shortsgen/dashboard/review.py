from pathlib import Path

import streamlit as st

from shortsgen.config import settings
from shortsgen.history import approve_clip, clips_pending_review, get_next_review_clip, skip_clip_review

st.title("Revisão Manual")
st.caption("Clipes com nota abaixo do mínimo (ou sem nota) esperando aprovação manual.")

pending_count = len(clips_pending_review(settings.db_path, settings.min_quality_score))

if pending_count == 0:
    st.success("Nenhum clipe esperando revisão agora!")
else:
    clip = get_next_review_clip(settings.db_path, settings.min_quality_score)

    st.write(f"**{pending_count}** clipe(s) aguardando revisão")

    col_video, col_info = st.columns([2, 1])
    with col_video:
        st.subheader(clip["title"])
        if Path(clip["path"]).exists():
            st.video(clip["path"])
        else:
            st.warning("Arquivo não encontrado no disco (pode já ter sido limpo/apagado).")
    with col_info:
        score = clip.get("quality_score")
        st.write(f"**Score:** {score if score is not None else 'sem nota'}")
        if clip.get("description"):
            st.write("**Descrição:**")
            st.caption(clip["description"])

        col_a, col_b = st.columns(2)
        if col_a.button("✅ Aprovar", type="primary", width="stretch"):
            approve_clip(settings.db_path, int(clip["id"]))
            st.success("Aprovado!")
            st.rerun()
        if col_b.button("⏭️ Pular", width="stretch"):
            skip_clip_review(settings.db_path, int(clip["id"]))
            st.rerun()
