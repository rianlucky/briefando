from pathlib import Path

from shortsgen.models import Word

# MarginV subiu de 160 para 256 (+5% da altura de 1920px) e depois pra 448
# (+10% adicional) para nao ficar coberto pelos botoes/descricao nativos do
# TikTok/Reels/Shorts. WrapStyle 0 (em vez de 2) quebra a linha automaticamente
# em vez de cortar o texto que passa da largura.
#
# Dois estilos porque a posicao da legenda depende do enquadramento do
# instante (ver reframe.py): "Bottom" pro foco em 1 pessoa, "Middle" pro
# split-screen (Alignment 5 centraliza verticalmente em PlayResY=1920, ou
# seja, cai exatamente na linha de divisao entre as duas metades).
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bottom,Poppins ExtraBold,72,&H00FFFFFF,&H000000FF,&H00110803,&H00000000,1,0,0,0,100,100,0,0,1,5,0,2,60,60,448,1
Style: Middle,Poppins ExtraBold,72,&H00FFFFFF,&H000000FF,&H00110803,&H00000000,1,0,0,0,100,100,0,0,1,5,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Text
"""

# Cores no formato ASS sao BGR (nao RGB). Branco = cor padrao do Style.
_HIGHLIGHT_COLOR = r"&H00FFFF&"  # amarelo
_DEFAULT_COLOR = r"&HFFFFFF&"  # branco
_HIGHLIGHT_SCALE = 130  # % - a palavra ativa cresce (efeito "pop"), mais dinamico


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
            token = (
                f"{{\\c{_HIGHLIGHT_COLOR}\\fscx{_HIGHLIGHT_SCALE}\\fscy{_HIGHLIGHT_SCALE}}}"
                f"{token}{{\\c{_DEFAULT_COLOR}\\fscx100\\fscy100}}"
            )
        tokens.append(token)
    return " ".join(tokens)


def _mode_at(mode_track: list[tuple[float, int]] | None, t: float) -> int:
    """1 = foco em 1 pessoa, 2 = split-screen. Sem mode_track, assume 1 (mesmo
    comportamento de antes dessa mudanca)."""
    if not mode_track:
        return 1
    mode = mode_track[0][1]
    for ts, m in mode_track:
        if ts > t:
            break
        mode = m
    return mode


def _chunk_events(chunk: list[Word], mode_track: list[tuple[float, int]] | None) -> list[str]:
    """Um evento por palavra do chunk, pintando a palavra ativa de amarelo e
    maior (efeito karaoke) enquanto o resto do texto do trecho fica visivel em
    branco. O estilo (posicao vertical) segue o enquadramento naquele instante:
    "Middle" (linha de divisao) durante split-screen, "Bottom" caso contrario."""
    events = []
    for i, w in enumerate(chunk):
        start = w.start
        end = chunk[i + 1].start if i + 1 < len(chunk) else chunk[-1].end
        if end <= start:
            end = start + 0.05
        text = _render_chunk_text(chunk, i)
        if not text.strip():
            continue
        style = "Middle" if _mode_at(mode_track, start) == 2 else "Bottom"
        events.append(f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},{style},{text}")
    return events


def build_ass_captions(
    words: list[Word],
    clip_start: float,
    dst_path: Path,
    mode_track: list[tuple[float, int]] | None = None,
) -> None:
    """Gera um arquivo .ass com legendas agrupadas, com tempos relativos ao inicio do clipe.

    Cada trecho de palavras aparece inteiro na tela, e a palavra sendo falada
    naquele instante fica destacada em amarelo e maior (estilo karaoke). A
    posicao vertical acompanha o `mode_track` de `reframe_to_vertical` (mesma
    janela de tempo do clipe): linha de divisao no split-screen, mais alta no
    foco em 1 pessoa."""
    shifted = [
        Word(start=w.start - clip_start, end=w.end - clip_start, text=w.text) for w in words
    ]
    chunks = _group_words(shifted)

    lines = [ASS_HEADER]
    for chunk in chunks:
        clean_chunk = [w for w in chunk if w.text.strip()]
        if not clean_chunk:
            continue
        lines.extend(_chunk_events(clean_chunk, mode_track))

    dst_path.write_text("\n".join(lines), encoding="utf-8")
