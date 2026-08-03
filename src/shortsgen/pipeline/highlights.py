import json

from google import genai
from google.genai import types

from shortsgen.config import settings
from shortsgen.history import get_top_performing_titles
from shortsgen.models import HighlightList, Transcript
from shortsgen.pipeline.text_clean import clean_for_prompt

_GEMINI_TIMEOUT_MS = 60_000

YOUTUBE_CATEGORIES = {
    "Comédia": "23",
    "Entretenimento": "24",
    "Pessoas e Blogs": "22",
    "Esportes": "17",
    "Educação": "27",
    "Notícias e Política": "25",
    "Jogos": "20",
    "Música": "10",
    "Ciência e Tecnologia": "28",
    "Como Fazer e Estilo": "26",
}
DEFAULT_CATEGORY_ID = YOUTUBE_CATEGORIES["Pessoas e Blogs"]

SYSTEM_PROMPT = """Voce e um editor de video especialista em cortar clipes virais para YouTube Shorts, TikTok e Reels a partir de transcricoes de videos longos (podcasts, entrevistas, palestras, lives).

Sua tarefa: analisar a transcricao com timestamps e apontar os melhores trechos para virar shorts standalone e envolventes.

Criterios para um bom highlight:
- Faz sentido sozinho, sem exigir contexto de outras partes do video
- Tem um gancho forte logo nos primeiros segundos
- Contem uma ideia completa: uma virada, uma piada, um dado surpreendente, uma historia ou um conselho acionavel
- Duracao entre {min_s} e {max_s} segundos
- Os timestamps de inicio e fim devem coincidir com o inicio/fim de frases da transcricao, nunca cortando uma ideia no meio

Alem do corte, gere tambem os metadados de publicacao de cada clipe:
- description: 2-3 frases descrevendo o clipe pro YouTube, sem hashtags (elas vao a parte)
- tags: 5-8 palavras-chave de busca relacionadas ao conteudo, sem o caractere #
- hashtags: 2-4 hashtags relevantes, sem o caractere #, sempre incluindo "shorts"
- category: a categoria do YouTube mais adequada, escolhida entre as opcoes fornecidas
- quality_score: nota de 0 a 100 do potencial viral desse clipe especifico como Short standalone. Considere: forca do gancho nos primeiros 3 segundos, se faz sentido sozinho sem contexto, presenca de uma virada/piada/dado surpreendente/emocao clara, e ritmo (sem trechos mortos). Seja criterioso e use a faixa toda -- nem todo highlight enviado merece nota alta.

A transcricao abaixo teve vicios de linguagem e repeticoes removidos para ficar mais enxuta -- isso e so limpeza de texto, ignore pequenas quebras no fraseado.

Responda apenas com os melhores trechos, no maximo {max_clips}, ordenados do mais forte para o mais fraco."""

HIGHLIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "highlights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "number",
                        "description": "timestamp de inicio em segundos, igual ao da transcricao",
                    },
                    "end": {
                        "type": "number",
                        "description": "timestamp de fim em segundos, igual ao da transcricao",
                    },
                    "title": {
                        "type": "string",
                        "description": "titulo curto e chamativo para o clipe (para usar como nome do arquivo/legenda)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "por que esse trecho funciona bem como short",
                    },
                    "description": {
                        "type": "string",
                        "description": "descricao do clipe pro YouTube, 2-3 frases, sem hashtags",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "5-8 palavras-chave de busca, sem #",
                    },
                    "hashtags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 hashtags relevantes, sem #, sempre incluindo 'shorts'",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(YOUTUBE_CATEGORIES.keys()),
                        "description": "categoria do YouTube mais adequada pra esse clipe",
                    },
                    "quality_score": {
                        "type": "integer",
                        "description": "nota de 0 a 100 do potencial viral desse clipe como Short standalone",
                    },
                },
                "required": [
                    "start",
                    "end",
                    "title",
                    "reason",
                    "description",
                    "tags",
                    "hashtags",
                    "category",
                    "quality_score",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["highlights"],
    "additionalProperties": False,
}


def _build_prompt_transcript(transcript: Transcript) -> str:
    """Monta a transcricao com timestamps, limpando vicios de linguagem para
    encolher a quantidade de tokens mandados ao Gemini (a transcricao original
    usada pra cortar/legendar os clipes continua intacta)."""
    lines = []
    for seg in transcript.segments:
        cleaned = clean_for_prompt(seg.text)
        if not cleaned:
            continue
        lines.append(f"[{seg.start:.1f}-{seg.end:.1f}] {cleaned}")
    return "\n".join(lines)


def _build_top_performers_section() -> str:
    """Referencia de titulos que ja performaram bem no canal, pra puxar o
    estilo/gancho do Gemini na direcao do que ja funcionou de verdade. So
    entra no prompt com historico suficiente (`MIN_HISTORY_FOR_LEARNING`)
    pra nao induzir a partir de 1-2 amostras sem significado estatistico."""
    top = get_top_performing_titles(settings.db_path, limit=5)
    if len(top) < settings.min_history_for_learning:
        return ""

    lines = "\n".join(f'- "{t["title"]}" ({t["views"]} views)' for t in top)
    return (
        "\n\nTitulos que ja tiveram bom desempenho neste canal (referencia de "
        "estilo/gancho - nao copie literalmente, adapte o que funciona pro "
        "conteudo atual):\n" + lines
    )


def find_highlights(transcript: Transcript) -> tuple[HighlightList, dict]:
    """Manda a transcricao com timestamps para o Gemini e pede os melhores trechos pra cortar.

    Retorna tambem o uso de tokens da chamada (`{"input_tokens", "output_tokens"}"), pra
    dar visibilidade de custo/consumo de API no dashboard sem precisar estimar nada.
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    system = SYSTEM_PROMPT.format(
        min_s=settings.clip_min_seconds,
        max_s=settings.clip_max_seconds,
        max_clips=settings.max_clips,
    ) + _build_top_performers_section()

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=f"Transcricao com timestamps:\n\n{_build_prompt_transcript(transcript)}",
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=HIGHLIGHT_SCHEMA,
            http_options=types.HttpOptions(timeout=_GEMINI_TIMEOUT_MS),
        ),
    )

    data = json.loads(response.text)
    usage = response.usage_metadata
    token_usage = {
        "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
        "output_tokens": (usage.candidates_token_count or 0) if usage else 0,
    }
    return HighlightList.model_validate(data), token_usage
