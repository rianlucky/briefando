import json

from google import genai
from google.genai import types

from shortsgen.config import settings
from shortsgen.models import HighlightList, Transcript
from shortsgen.pipeline.text_clean import clean_for_prompt

_GEMINI_TIMEOUT_MS = 60_000

SYSTEM_PROMPT = """Voce e um editor de video especialista em cortar clipes virais para YouTube Shorts, TikTok e Reels a partir de transcricoes de videos longos (podcasts, entrevistas, palestras, lives).

Sua tarefa: analisar a transcricao com timestamps e apontar os melhores trechos para virar shorts standalone e envolventes.

Criterios para um bom highlight:
- Faz sentido sozinho, sem exigir contexto de outras partes do video
- Tem um gancho forte logo nos primeiros segundos
- Contem uma ideia completa: uma virada, uma piada, um dado surpreendente, uma historia ou um conselho acionavel
- Duracao entre {min_s} e {max_s} segundos
- Os timestamps de inicio e fim devem coincidir com o inicio/fim de frases da transcricao, nunca cortando uma ideia no meio

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
                },
                "required": ["start", "end", "title", "reason"],
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


def find_highlights(transcript: Transcript) -> HighlightList:
    """Manda a transcricao com timestamps para o Gemini e pede os melhores trechos pra cortar."""
    client = genai.Client(api_key=settings.gemini_api_key)

    system = SYSTEM_PROMPT.format(
        min_s=settings.clip_min_seconds,
        max_s=settings.clip_max_seconds,
        max_clips=settings.max_clips,
    )

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
    return HighlightList.model_validate(data)
