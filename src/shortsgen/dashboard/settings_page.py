import pandas as pd
import streamlit as st

from shortsgen.config import settings

st.title("Configurações")
st.caption(
    "Somente leitura — os valores reais ficam no `.env` do projeto. Pra mudar algo, edite o "
    "arquivo e reinicie o pipeline/dashboard."
)


def _table(rows: list[tuple[str, object]]) -> None:
    df = pd.DataFrame([(label, str(value)) for label, value in rows], columns=["Parâmetro", "Valor"])
    st.dataframe(df, hide_index=True, width="stretch")


st.subheader("Gemini / IA")
_table(
    [
        ("Chave de API", "✅ configurada" if settings.gemini_api_key else "❌ não configurada"),
        ("Modelo", settings.gemini_model),
        ("Máx. clipes por vídeo", settings.max_clips),
        ("Duração mín. do clipe (s)", settings.clip_min_seconds),
        ("Duração máx. do clipe (s)", settings.clip_max_seconds),
        ("Score mínimo p/ publicar direto", settings.min_quality_score),
        ("Histórico mín. p/ aprendizado", settings.min_history_for_learning),
    ]
)

st.subheader("Transcrição (Whisper)")
_table(
    [
        ("Tamanho do modelo", settings.whisper_model_size),
        ("Dispositivo", settings.whisper_device),
        ("Tipo de computação", settings.whisper_compute_type),
        ("Threads de CPU", settings.whisper_cpu_threads),
    ]
)

st.subheader("Fila & Publicação")
_table(
    [
        ("Tentativas máx. da fila", settings.queue_max_retries),
        ("Retenção de clipes publicados (dias)", settings.clip_retention_days),
        ("Tentativas de retry do pipeline", settings.pipeline_retry_attempts),
        ("Delay entre retries (s)", settings.pipeline_retry_delay_seconds),
    ]
)

st.subheader("yt-dlp / Autenticação")
_table(
    [
        ("Cookies de arquivo", settings.ytdlp_cookies_file or "—"),
        ("Cookies do navegador", settings.ytdlp_cookies_from_browser or "—"),
    ]
)

st.subheader("Caminhos")
_table(
    [
        ("Diretório de trabalho", str(settings.work_dir)),
        ("Diretório de saída", str(settings.output_dir)),
        ("Diretório de logs", str(settings.log_dir)),
        ("Banco de dados", str(settings.db_path)),
    ]
)
