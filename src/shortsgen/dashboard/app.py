from pathlib import Path

import streamlit as st

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_PATH = ASSETS_DIR / "logo_horizontal.png"
ICON_PATH = ASSETS_DIR / "icon.png"

EXTERNAL_LINKS = {
    "n8n": ("http://localhost:5678/workflow/8mrmAhHe21H6eEPa", ":material/settings_suggest:"),
    "Google AI Studio": (
        "https://aistudio.google.com/u/1/usage?project=gen-lang-client-0083447221&timeRange=last-1-day&pli=1",
        ":material/smart_toy:",
    ),
    "YouTube Studio": ("https://studio.youtube.com/channel/UC4heRBU1YucVmJzbI9YbaxQ", ":material/video_settings:"),
    "Canal do YouTube": ("https://www.youtube.com/@Briefando", ":material/play_circle:"),
}

st.set_page_config(page_title="Briefando Dashboard", page_icon="🎬", layout="wide")

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: #0F1B33;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 16px 20px;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
    }
    div[data-testid="stMetric"] * {
        color: #FFFFFF !important;
    }
    [data-testid="stSidebarLogo"], [data-testid="stLogoSpacer"], [data-testid="stLogo"] {
        overflow: visible !important;
    }
    [data-testid="stLogo"] img {
        width: 80px !important;
        height: auto !important;
        max-width: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if ICON_PATH.exists():
    st.logo(str(ICON_PATH), icon_image=str(ICON_PATH), size="large")

with st.sidebar:
    st.markdown(
        "<div style='margin-top:-8px; margin-bottom:8px; font-size:1.3rem; font-weight:800;'>"
        "<span style='color:#FDBB11;'>Brief</span><span style='color:#FFFFFF;'>ando</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Links úteis")
    for label, (url, icon) in EXTERNAL_LINKS.items():
        st.link_button(label, url, icon=icon, width="stretch")

pg = st.navigation(
    [
        st.Page("overview.py", title="Visão Geral", icon=":material/dashboard:", default=True),
        st.Page("clips.py", title="Clipes", icon=":material/movie:"),
        st.Page("queue_page.py", title="Fila", icon=":material/list_alt:"),
        st.Page("analytics.py", title="Analytics", icon=":material/monitoring:"),
        st.Page("sources_page.py", title="Fontes", icon=":material/rss_feed:"),
        st.Page("review.py", title="Revisão Manual", icon=":material/fact_check:"),
        st.Page("history_page.py", title="Histórico", icon=":material/history:"),
        st.Page("settings_page.py", title="Configurações", icon=":material/tune:"),
    ]
)
pg.run()
