import urllib.request
from collections import deque
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from shortsgen.config import settings
from shortsgen.exceptions import PipelineCancelled

TARGET_ASPECT = 9 / 16

# Ignora rostos muito pequenos em relacao ao frame (plateia, fundo, reflexo) pra
# nao disparar split-screen por engano.
# Medido em video real de podcast 1920x1080 com 2 pessoas dividindo o frame
# (2026-08-01): rostos de verdade ficam entre ~0.007 e ~0.014 da area do
# frame; falsos positivos de fundo ficaram em ~0.004-0.005. 0.01 cortava boa
# parte dos rostos reais por estar bem no meio dessa faixa.
_MIN_FACE_AREA_RATIO = 0.006

# Janela deslizante (em segundos) usada pra decidir entre split-screen e
# foco-em-1-pessoa -- evita "piscar" entre os dois modos.
_MODE_CONFIRM_SECONDS = 1.2

# Fracao das amostras dentro da janela que precisa concordar com um modo pra
# ele ser confirmado. Antes exigiamos 100% (qualquer soluco de deteccao -
# pessoa vira o rosto, gesticula na frente, confianca cai um instante -
# reiniciava a contagem do zero, e na pratica o split-screen quase nunca
# disparava). Com maioria (nao unanimidade), soluços isolados nao acabam
# mais com a janela inteira.
_MODE_MAJORITY_RATIO = 0.65

# API antiga (mp.solutions.face_detection) foi removida em mediapipe >= 1.0 --
# a partir dela usamos a API nova "Tasks", que exige baixar o modelo .tflite.
# "full_range" (em vez de "short_range") detecta melhor rostos mais distantes da
# camera, cenario tipico de podcast/entrevista com a pessoa sentada mais longe.
_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/latest/blaze_face_full_range.tflite"
_MODEL_PATH = settings.work_dir / "mediapipe_models" / "blaze_face_full_range.tflite"


def _ensure_model() -> Path:
    if not _MODEL_PATH.exists():
        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
    return _MODEL_PATH


def _detect_face_samples(
    video_path: Path, sample_every_s: float = 0.2, cancel_event=None
) -> tuple[list[tuple[float, list[tuple[float, float]]]], int, int]:
    """Amostra o video e retorna, por instante, os ate 2 maiores rostos detectados
    como (centro_x, proporcao_da_area_do_frame), ordenados do maior pro menor."""
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_area = max(1, src_w * src_h)
    step = max(1, round(fps * sample_every_s))

    options = vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(_ensure_model())),
        running_mode=vision.RunningMode.VIDEO,
        min_detection_confidence=0.5,
    )

    samples: list[tuple[float, list[tuple[float, float]]]] = []
    frame_idx = 0

    try:
        with vision.FaceDetector.create_from_options(options) as detector:
            while True:
                if frame_idx % step == 0 and cancel_event is not None and cancel_event.is_set():
                    raise PipelineCancelled("Cancelado durante a deteccao de rosto")
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx % step == 0:
                    t = frame_idx / fps
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = detector.detect_for_video(mp_image, int(t * 1000))
                    faces = []
                    for det in result.detections:
                        box = det.bounding_box
                        area_ratio = (box.width * box.height) / frame_area
                        if area_ratio < _MIN_FACE_AREA_RATIO:
                            continue
                        center_x = box.origin_x + box.width / 2
                        faces.append((center_x, area_ratio))
                    faces.sort(key=lambda f: f[1], reverse=True)
                    samples.append((t, faces[:2]))
                frame_idx += 1
    finally:
        cap.release()

    return samples, src_w, src_h


def _build_tracks(samples: list[tuple[float, list[tuple[float, float]]]], frame_w: int):
    """Constroi 3 series temporais (posicao se 1 rosto, posicao esquerda/direita se
    2 rostos) mais o 'voto' bruto de quantos rostos existem em cada instante."""
    single_track: list[tuple[float, float]] = []
    left_track: list[tuple[float, float]] = []
    right_track: list[tuple[float, float]] = []
    raw_mode: list[tuple[float, int]] = []

    last_single = frame_w / 2
    last_left = frame_w * 0.3
    last_right = frame_w * 0.7

    for t, faces in samples:
        if faces:
            last_single = faces[0][0]
        single_track.append((t, last_single))

        if len(faces) >= 2:
            last_left, last_right = sorted(x for x, _ in faces[:2])
        left_track.append((t, last_left))
        right_track.append((t, last_right))

        if len(faces) >= 2:
            raw_mode.append((t, 2))
        elif len(faces) == 1:
            raw_mode.append((t, 1))
        else:
            raw_mode.append((t, raw_mode[-1][1] if raw_mode else 1))

    return single_track, left_track, right_track, raw_mode


def _debounce_mode(raw_mode: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """Confirma a troca de modo por maioria numa janela deslizante de
    _MODE_CONFIRM_SECONDS, em vez de exigir unanimidade -- uma detecção
    perdida isolada não derruba mais a janela inteira."""
    if not raw_mode:
        return raw_mode

    committed = raw_mode[0][1]
    window: deque[tuple[float, int]] = deque()
    out = []

    for t, mode in raw_mode:
        window.append((t, mode))
        while window and t - window[0][0] > _MODE_CONFIRM_SECONDS:
            window.popleft()

        twos_ratio = sum(1 for _, m in window if m == 2) / len(window)
        if twos_ratio >= _MODE_MAJORITY_RATIO:
            committed = 2
        elif (1 - twos_ratio) >= _MODE_MAJORITY_RATIO:
            committed = 1
        # sem maioria clara na janela: mantem o modo ja confirmado

        out.append((t, committed))

    return out


def _smooth(centers: list[tuple[float, float]], alpha: float = 0.35) -> list[tuple[float, float]]:
    if not centers:
        return centers
    smoothed = [centers[0]]
    ema = centers[0][1]
    for t, x in centers[1:]:
        ema = alpha * x + (1 - alpha) * ema
        smoothed.append((t, ema))
    return smoothed


def _make_x_at(keyframes: list[tuple[float, float]]):
    def x_at(t: float) -> float:
        if t <= keyframes[0][0]:
            return keyframes[0][1]
        if t >= keyframes[-1][0]:
            return keyframes[-1][1]
        for (t0, x0), (t1, x1) in zip(keyframes, keyframes[1:]):
            if t0 <= t <= t1:
                if t1 == t0:
                    return x0
                ratio = (t - t0) / (t1 - t0)
                return x0 + (x1 - x0) * ratio
        return keyframes[-1][1]

    return x_at


def _make_mode_at(mode_track: list[tuple[float, int]]):
    def mode_at(t: float) -> int:
        prev = mode_track[0][1]
        for ts, m in mode_track:
            if ts > t:
                break
            prev = m
        return prev

    return mode_at


def _crop_and_resize(
    frame, center_x: float, crop_w: int, crop_h: int, out_w: int, out_h: int, src_w: int
):
    x0 = round(center_x - crop_w / 2)
    x0 = max(0, min(x0, src_w - crop_w))
    cropped = frame[0:crop_h, x0 : x0 + crop_w]
    return cv2.resize(cropped, (out_w, out_h))


def reframe_to_vertical(
    src_path: Path,
    dst_path: Path,
    target_w: int = 1080,
    target_h: int = 1920,
    cancel_event=None,
) -> list[tuple[float, int]]:
    """Recorta o video horizontal em 9:16. Segue o rosto de quem fala quando ha
    1 pessoa em cena; quando ha 2 pessoas estaveis, alterna pra split-screen
    (uma em cima, outra embaixo). Saida sem audio.

    Retorna o `mode_track` (instante -> 1 pessoa/2 split-screen) pra quem gerar
    a legenda saber, em cada instante do clipe, onde posicionar o texto (linha
    de divisao no split-screen, mais alto no foco em 1 pessoa)."""
    samples, src_w, src_h = _detect_face_samples(src_path, cancel_event=cancel_event)
    single_track, left_track, right_track, raw_mode = _build_tracks(samples, src_w)
    mode_track = _debounce_mode(raw_mode)

    single_at = _make_x_at(_smooth(single_track))
    left_at = _make_x_at(_smooth(left_track))
    right_at = _make_x_at(_smooth(right_track))
    mode_at = _make_mode_at(mode_track)

    cap = cv2.VideoCapture(str(src_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    crop_w_single = min(src_w, round(src_h * TARGET_ASPECT))
    crop_h_single = src_h

    half_h = target_h // 2
    other_half_h = target_h - half_h
    crop_w_half = min(src_w, round(src_h * (target_w / half_h)))
    crop_h_half = src_h

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(dst_path), fourcc, fps, (target_w, target_h))

    try:
        frame_idx = 0
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise PipelineCancelled("Cancelado durante o reenquadramento")
            ok, frame = cap.read()
            if not ok:
                break
            t = frame_idx / fps

            if mode_at(t) == 2:
                top = _crop_and_resize(
                    frame, left_at(t), crop_w_half, crop_h_half, target_w, half_h, src_w
                )
                bottom = _crop_and_resize(
                    frame, right_at(t), crop_w_half, crop_h_half, target_w, other_half_h, src_w
                )
                combined = cv2.vconcat([top, bottom])
            else:
                combined = _crop_and_resize(
                    frame, single_at(t), crop_w_single, crop_h_single, target_w, target_h, src_w
                )

            writer.write(combined)
            frame_idx += 1
    finally:
        writer.release()
        cap.release()

    return mode_track
