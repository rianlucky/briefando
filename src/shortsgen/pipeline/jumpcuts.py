import subprocess
from pathlib import Path

from shortsgen.models import Word

# Remove pausas/vicios de linguagem acima de 1.2s dentro do trecho do
# highlight, deixando o corte com ritmo mais dinamico (jump-cut). So corte
# seco por enquanto (sem transicao no ponto de corte) - mais simples de
# calibrar primeiro; pode virar um zoom rapido depois se fizer sentido.
# 0.6s (primeiro palpite) testado contra audio real e ficou picotado demais -
# 21 cortes num clipe de 51s. 1.2s deu 8 cortes no mesmo clipe (~1 a cada 4-5s
# de fala), ritmo bem mais natural.
_SILENCE_THRESHOLD_DB = -20
_MIN_PAUSE_S = 1.2
# Mantém um respiro pequeno em volta de cada pausa removida em vez de colar
# fala direto na fala - fica menos abrupto que cortar o silencio inteiro fora.
_PAUSE_BUFFER_S = 0.15


def _detect_silence_spans(video_path: Path, start: float, end: float) -> list[tuple[float, float]]:
    """Acha TODOS os trechos de silencio (>= `_MIN_PAUSE_S`) dentro de
    [start, end] do video original - devolve como (inicio, fim) absolutos
    (mesma referencia de tempo do video inteiro, nao do clipe)."""
    duration = end - start
    if duration <= 0:
        return []
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-ss", f"{start}", "-i", str(video_path), "-t", f"{duration}",
        "-vn",
        "-af", f"silencedetect=noise={_SILENCE_THRESHOLD_DB}dB:d={_MIN_PAUSE_S}",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(60, duration))
    except subprocess.TimeoutExpired:
        return []
    if result.returncode not in (0, 1):
        return []

    spans = []
    pending_start = None
    for line in result.stderr.splitlines():
        if "silence_start:" in line:
            try:
                pending_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (IndexError, ValueError):
                pending_start = None
        elif "silence_end:" in line and pending_start is not None:
            try:
                silence_end = float(line.split("silence_end:")[1].split("|")[0].strip())
            except (IndexError, ValueError):
                continue
            spans.append((start + pending_start, start + silence_end))
            pending_start = None
    return spans


def build_keep_segments(
    start: float, end: float, silence_spans: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Devolve os trechos a MANTER (start/end do highlight menos as pausas
    detectadas, com um pequeno respiro em volta de cada corte) - cada um como
    (inicio, fim) absolutos. Sem nenhuma pausa, devolve o highlight inteiro
    como um unico segmento (comportamento identico ao corte simples de antes)."""
    if not silence_spans:
        return [(start, end)]

    segments = []
    cursor = start
    for s_start, s_end in sorted(silence_spans):
        cut_start = max(cursor, s_start + _PAUSE_BUFFER_S)
        cut_end = min(end, s_end - _PAUSE_BUFFER_S)
        if cut_end <= cut_start:
            continue
        if cut_start > cursor:
            segments.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if cursor < end:
        segments.append((cursor, end))

    return segments if segments else [(start, end)]


def cut_with_jumpcuts(
    src: Path, keep_segments: list[tuple[float, float]], dst: Path, cancel_event=None
) -> None:
    """Corta cada trecho mantido separado e concatena na ordem - remove as
    pausas do meio, deixando so a fala. Com 1 segmento so, e identico a um
    corte simples (mesmo resultado de antes de existir jump-cut)."""
    from shortsgen.pipeline.render import _run_ffmpeg, cut_segment

    work_dir = dst.parent
    part_paths = []
    try:
        for i, (seg_start, seg_end) in enumerate(keep_segments):
            part_path = work_dir / f"{dst.stem}_part{i}.mp4"
            cut_segment(src, seg_start, seg_end, part_path, cancel_event=cancel_event)
            part_paths.append(part_path)

        if len(part_paths) == 1:
            part_paths[0].replace(dst)
            return

        concat_list = work_dir / f"{dst.stem}_concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.name}'" for p in part_paths), encoding="utf-8"
        )
        _run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(dst)],
            cancel_event=cancel_event,
        )
    finally:
        for p in part_paths:
            p.unlink(missing_ok=True)
        concat_list_path = work_dir / f"{dst.stem}_concat.txt"
        concat_list_path.unlink(missing_ok=True)


def remap_words(words: list[Word], keep_segments: list[tuple[float, float]]) -> list[Word]:
    """Reposiciona os timestamps (absolutos, do video original) das palavras
    pra linha do tempo do clipe FINAL (depois das pausas removidas e os
    trechos colados) - comeca em 0. Uma palavra que caia dentro de um trecho
    removido (nao deveria acontecer, ja que so corta em pausas) e grudada no
    limite mais proximo em vez de descartada."""
    cumulative_starts = []
    acc = 0.0
    for seg_start, seg_end in keep_segments:
        cumulative_starts.append(acc)
        acc += seg_end - seg_start

    def _remap(t: float) -> float:
        for (seg_start, seg_end), offset in zip(keep_segments, cumulative_starts):
            if seg_start <= t <= seg_end:
                return offset + (t - seg_start)
        # fora de qualquer segmento mantido (dentro de uma pausa removida) -
        # gruda no limite mantido mais proximo em vez de descartar a palavra.
        before = [(seg_end, off + (seg_end - seg_start)) for (seg_start, seg_end), off in zip(keep_segments, cumulative_starts) if seg_end <= t]
        if before:
            return max(before, key=lambda x: x[0])[1]
        return 0.0

    return [Word(start=_remap(w.start), end=_remap(w.end), text=w.text) for w in words]
