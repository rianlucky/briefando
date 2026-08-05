import subprocess
from pathlib import Path

from faster_whisper import WhisperModel

from shortsgen.config import settings
from shortsgen.models import Transcript, TranscriptSegment, Word

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            cpu_threads=settings.whisper_cpu_threads,
        )
    return _model


def _get_duration_seconds(media_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(result.stdout.strip())


def _extract_audio_chunk(media_path: Path, start: float, duration: float, dst: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start}", "-i", str(media_path), "-t", f"{duration}",
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst),
        ],
        check=True,
        timeout=300,
    )


# -30dB nao achou silencio nenhum num video real com ruido de fundo/musica -
# testado -25/-20/-16/-12dB no mesmo trecho, todos acharam o mesmo ponto real
# de pausa. -20dB fica no meio: pega pausa de verdade sem confundir com
# ruido de fundo baixo constante.
_SILENCE_THRESHOLD_DB = -20
_SILENCE_MIN_DURATION_S = 0.3


def _find_silence_cut(media_path: Path, start: float, search_until: float) -> float | None:
    """Acha o meio do primeiro silencio (>= `_SILENCE_MIN_DURATION_S`, mais
    quieto que `_SILENCE_THRESHOLD_DB`) dentro da janela [start, search_until]
    do audio original - devolve o instante ABSOLUTO (no video inteiro) pra
    cortar ali, ou None se nao achar nenhum silencio real nessa janela.
    Limiar/duracao sao um primeiro palpite de engenharia, sem calibracao com
    audio real ainda."""
    duration = search_until - start
    if duration <= 0:
        return None
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-ss", f"{start}", "-i", str(media_path), "-t", f"{duration}",
        "-vn",  # so audio - decodificar o video tambem (sem isso) deixa a busca bem mais lenta
        "-af", f"silencedetect=noise={_SILENCE_THRESHOLD_DB}dB:d={_SILENCE_MIN_DURATION_S}",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(120, duration))
    except subprocess.TimeoutExpired:
        return None

    silence_start = None
    for line in result.stderr.splitlines():
        if "silence_start:" in line:
            try:
                silence_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (IndexError, ValueError):
                silence_start = None
        elif "silence_end:" in line and silence_start is not None:
            try:
                silence_end = float(line.split("silence_end:")[1].split("|")[0].strip())
            except (IndexError, ValueError):
                continue
            return start + (silence_start + silence_end) / 2

    return None


def _transcribe_file(model: WhisperModel, path: Path) -> tuple[list[TranscriptSegment], str]:
    segments_iter, info = model.transcribe(str(path), word_timestamps=True, vad_filter=True)
    segments = [
        TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            words=[Word(start=w.start, end=w.end, text=w.word) for w in (seg.words or [])],
        )
        for seg in segments_iter
    ]
    return segments, info.language


def transcribe(media_path: Path) -> Transcript:
    """Transcreve audio/video com faster-whisper, com timestamps por palavra.

    A extracao de features do faster-whisper faz uma FFT do audio inteiro de
    uma vez so (sem chunking interno) - pra videos muito longos isso estoura
    memoria (medido: um video de 4.74h precisou de 5.1GB so pra esse array
    intermediario, ~1.08GB/hora). Acima de `TRANSCRIBE_CHUNK_MAX_SECONDS`
    (padrao 1h), corta o audio em pedacos antes de transcrever - mas em vez de
    cortar num minuto fechado (arriscando cortar uma palavra ao meio), procura
    o primeiro momento de silencio real a partir de `TRANSCRIBE_CHUNK_MIN_SECONDS`
    (padrao 20min) e corta ali. Se nao achar silencio nenhum ate o limite
    maximo, corta na marca mesmo (raro, e so nesse caso existe risco de
    cortar uma palavra ao meio)."""
    model = _get_model()
    total_duration = _get_duration_seconds(media_path)

    if total_duration <= settings.transcribe_chunk_max_seconds:
        segments, language = _transcribe_file(model, media_path)
        return Transcript(language=language, segments=segments)

    all_segments: list[TranscriptSegment] = []
    language: str | None = None
    chunk_dir = media_path.parent / f"{media_path.stem}_chunks"
    chunk_dir.mkdir(exist_ok=True)
    try:
        current_start = 0.0
        while current_start < total_duration:
            remaining = total_duration - current_start
            if remaining <= settings.transcribe_chunk_max_seconds:
                chunk_end = total_duration
            else:
                search_from = current_start + settings.transcribe_chunk_min_seconds
                search_until = current_start + settings.transcribe_chunk_max_seconds
                cut = _find_silence_cut(media_path, search_from, search_until)
                chunk_end = cut if cut is not None else search_until

            chunk_path = chunk_dir / f"chunk_{int(current_start)}.wav"
            _extract_audio_chunk(media_path, current_start, chunk_end - current_start, chunk_path)
            try:
                segments, chunk_language = _transcribe_file(model, chunk_path)
            finally:
                chunk_path.unlink(missing_ok=True)
            language = language or chunk_language
            for seg in segments:
                all_segments.append(
                    TranscriptSegment(
                        start=seg.start + current_start,
                        end=seg.end + current_start,
                        text=seg.text,
                        words=[
                            Word(start=w.start + current_start, end=w.end + current_start, text=w.text)
                            for w in seg.words
                        ],
                    )
                )
            current_start = chunk_end
    finally:
        try:
            chunk_dir.rmdir()
        except OSError:
            pass

    return Transcript(language=language or "pt", segments=all_segments)
