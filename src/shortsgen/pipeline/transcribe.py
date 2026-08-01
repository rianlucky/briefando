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
        )
    return _model


def transcribe(media_path: Path) -> Transcript:
    """Transcreve audio/video com faster-whisper, com timestamps por palavra."""
    model = _get_model()
    segments_iter, info = model.transcribe(
        str(media_path),
        word_timestamps=True,
        vad_filter=True,
    )

    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        words = [Word(start=w.start, end=w.end, text=w.word) for w in (seg.words or [])]
        segments.append(
            TranscriptSegment(start=seg.start, end=seg.end, text=seg.text, words=words)
        )

    return Transcript(language=info.language, segments=segments)
