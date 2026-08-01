from pathlib import Path

from shortsgen.models import Word

# MarginV subiu de 160 para 256 (+5% da altura de 1920px) para nao ficar coberto
# pelos botoes/legendas nativas do TikTok/Reels/Shorts. WrapStyle 0 (em vez de 2)
# quebra a linha automaticamente em vez de cortar o texto que passa da largura.
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,0,2,60,60,256,1

[Events]
Format: Layer, Start, End, Style, Text
"""

# Cores no formato ASS sao BGR (nao RGB). Branco = cor padrao do Style.
_HIGHLIGHT_COLOR = r"&H00FFFF&"  # amarelo
_DEFAULT_COLOR = r"&HFFFFFF&"  # branco


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    centiseconds = round(seconds * 100)
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _group_words(words: list[Word], max_words: int = 5, max_duration: float = 2.5) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    current: list[Word] = []
    chunk_start = 0.0
    for w in words:
        if not current:
            chunk_start = w.start
        current.append(w)
        duration = w.end - chunk_start
        if len(current) >= max_words or duration >= max_duration:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _render_chunk_text(chunk: list[Word], active_index: int) -> str:
    tokens = []
    for i, w in enumerate(chunk):
        token = w.text.strip().upper()
        if i == active_index:
            token = f"{{\\c{_HIGHLIGHT_COLOR}}}{token}{{\\c{_DEFAULT_COLOR}}}"
        tokens.append(token)
    return " ".join(tokens)


def _chunk_events(chunk: list[Word]) -> list[str]:
    """Um evento por palavra do chunk, pintando a palavra ativa de amarelo
    (efeito karaoke) enquanto o resto do texto do trecho fica visivel em branco."""
    events = []
    for i, w in enumerate(chunk):
        start = w.start
        end = chunk[i + 1].start if i + 1 < len(chunk) else chunk[-1].end
        if end <= start:
            end = start + 0.05
        text = _render_chunk_text(chunk, i)
        if not text.strip():
            continue
        events.append(f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,{text}")
    return events


def build_ass_captions(words: list[Word], clip_start: float, dst_path: Path) -> None:
    """Gera um arquivo .ass com legendas agrupadas, com tempos relativos ao inicio do clipe.

    Cada trecho de palavras aparece inteiro na tela, e a palavra sendo falada
    naquele instante fica destacada em amarelo (estilo karaoke)."""
    shifted = [
        Word(start=w.start - clip_start, end=w.end - clip_start, text=w.text) for w in words
    ]
    chunks = _group_words(shifted)

    lines = [ASS_HEADER]
    for chunk in chunks:
        clean_chunk = [w for w in chunk if w.text.strip()]
        if not clean_chunk:
            continue
        lines.extend(_chunk_events(clean_chunk))

    dst_path.write_text("\n".join(lines), encoding="utf-8")
