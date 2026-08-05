import subprocess
import urllib.request
from collections import deque
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from shortsgen.config import settings
from shortsgen.exceptions import PipelineCancelled

TARGET_ASPECT = 9 / 16

# Zoom "Ken Burns" continuo e sutil ao longo do clipe inteiro (100% -> 108%).
# So se aplica no foco em 1 pessoa - desativado no split-screen (ver
# reframe_to_vertical), onde o zoom competia com o corte ja mais fechado.
_ZOOM_KENBURNS_MAX = 1.08

# Punch-in extra nos picos de volume/energia da voz: corte seco pro zoom
# (sem transicao suave de entrada/saida), segura por um tempo, corta seco de
# volta - nao uma curva de "vai e volta". Mais leve que uma primeira tentativa
# com transicao suave, que ficou exagerada.
_ZOOM_PUNCH_BUMP = 0.06
_ZOOM_PUNCH_HOLD_S = 1.8

# Deteccao de pico de volume: RMS por janela de 0.1s: pico = maximo local que
# passa de media + 1.5 desvio-padrao do proprio clipe (sem numero "certo"
# medido ainda - primeiro lote real vai dizer se precisa recalibrar). No
# maximo 3 picos por clipe (20-90s) pra nao virar zoom toda hora, com pelo
# menos 1.5s de espacamento entre eles.
_VOLUME_WINDOW_S = 0.1
_VOLUME_PEAK_STD_MULT = 1.5
_VOLUME_PEAK_MIN_GAP_S = 1.5
_VOLUME_PEAK_MAX_COUNT = 3

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

# Split-screen: cada metade recorta uma area proporcional ao tamanho do rosto
# detectado (nao mais a altura inteira da fonte) - deixa as pessoas
# consistentemente "mais pertas" no enquadramento, na mesma proporcao
# independente da distancia real da camera em cada video. Primeiro palpite,
# sem calibracao com video real ainda - K=4 da um enquadramento tipo "busto"
# (rosto ocupando ~25% da altura da metade); ajustar depois com base no
# resultado real.
_SPLIT_FACE_HEIGHT_MULTIPLIER = 4.0
# Nunca recorta mais perto que 28% da altura da fonte, mesmo que a deteccao de
# rosto de um instante saia ruidosa/pequena demais - evita zoom exagerado.
_SPLIT_MIN_CROP_RATIO = 0.28

# Foco em 1 pessoa: mesma ideia do split-screen, mas menos fechado (plano
# medio em vez de busto) - o corte acompanha o TAMANHO do rosto, nao so a
# posicao X. Antes o modo 1 pessoa sempre recortava a altura inteira da fonte;
# quando a gravacao corta pra uma camera mais aberta (plano geral da mesa,
# cutaway do estudio), esse recorte "solto" aparecia sem aviso no meio de uma
# sequencia de rostos em close, quebrando a continuidade visual. Com o corte
# proporcional ao rosto, um plano mais aberto da fonte vira zoom-in em vez de
# um quadro largo. Primeiro palpite, sem calibracao com video real ainda.
_SINGLE_FACE_HEIGHT_MULTIPLIER = 6.0
_SINGLE_MIN_CROP_RATIO = 0.45

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
) -> tuple[list[tuple[float, list[tuple[float, float, float, float]]]], int, int]:
    """Amostra o video e retorna, por instante, os ate 2 maiores rostos detectados
    como (centro_x, centro_y, altura_em_pixels, proporcao_da_area_do_frame),
    ordenados do maior pro menor."""
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
                        center_y = box.origin_y + box.height / 2
                        faces.append((center_x, center_y, box.height, area_ratio))
                    faces.sort(key=lambda f: f[3], reverse=True)
                    samples.append((t, faces[:2]))
                frame_idx += 1
    finally:
        cap.release()

    return samples, src_w, src_h


def _build_tracks(samples: list[tuple[float, list[tuple[float, float, float, float]]]], frame_w: int, frame_h: int):
    """Constroi as series temporais de posicao (1 rosto, ou esquerda/direita se
    2 rostos - x, y e altura em pixels de cada lado) mais o 'voto' bruto de
    quantos rostos existem em cada instante."""
    single_track: list[tuple[float, float]] = []
    single_y_track: list[tuple[float, float]] = []
    single_size_track: list[tuple[float, float]] = []
    left_track: list[tuple[float, float]] = []
    right_track: list[tuple[float, float]] = []
    left_y_track: list[tuple[float, float]] = []
    right_y_track: list[tuple[float, float]] = []
    left_size_track: list[tuple[float, float]] = []
    right_size_track: list[tuple[float, float]] = []
    raw_mode: list[tuple[float, int]] = []

    last_single = frame_w / 2
    last_single_y = frame_h / 2
    last_single_size = frame_h * 0.2
    last_left = frame_w * 0.3
    last_right = frame_w * 0.7
    last_left_y = frame_h / 2
    last_right_y = frame_h / 2
    last_left_size = frame_h * 0.15
    last_right_size = frame_h * 0.15

    for t, faces in samples:
        if faces:
            last_single = faces[0][0]
            last_single_y = faces[0][1]
            last_single_size = faces[0][2]
        single_track.append((t, last_single))
        single_y_track.append((t, last_single_y))
        single_size_track.append((t, last_single_size))

        if len(faces) >= 2:
            xa, ya, ha, _ = faces[0]
            xb, yb, hb, _ = faces[1]
            # Atribui cada rosto detectado ao slot (topo/base) mais proximo de
            # onde ele estava no frame anterior, em vez de reordenar por X toda
            # vez - sem isso, quando as duas pessoas se aproximam ou a ordem de
            # deteccao muda de um frame pro outro, os dois lados podem "trocar"
            # de gente do nada, fazendo o crop pular.
            keep = abs(xa - last_left) + abs(xb - last_right)
            swap = abs(xa - last_right) + abs(xb - last_left)
            if keep <= swap:
                last_left, last_left_y, last_left_size = xa, ya, ha
                last_right, last_right_y, last_right_size = xb, yb, hb
            else:
                last_left, last_left_y, last_left_size = xb, yb, hb
                last_right, last_right_y, last_right_size = xa, ya, ha
        left_track.append((t, last_left))
        right_track.append((t, last_right))
        left_y_track.append((t, last_left_y))
        right_y_track.append((t, last_right_y))
        left_size_track.append((t, last_left_size))
        right_size_track.append((t, last_right_size))

        if len(faces) >= 2:
            raw_mode.append((t, 2))
        elif len(faces) == 1:
            raw_mode.append((t, 1))
        else:
            raw_mode.append((t, raw_mode[-1][1] if raw_mode else 1))

    return (
        single_track,
        single_y_track,
        single_size_track,
        left_track,
        right_track,
        left_y_track,
        right_y_track,
        left_size_track,
        right_size_track,
        raw_mode,
    )


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


def _detect_volume_peaks(video_path: Path) -> list[float]:
    """Extrai o audio do clipe e acha os instantes de pico de volume/energia da
    voz - usados pra disparar um punch-in de zoom rapido, dando impacto
    exatamente onde a pessoa fala mais forte. Sem audio decodificavel ou sem
    nenhum pico que se destaque, devolve lista vazia (fica so o Ken Burns
    continuo nesse caso)."""
    sample_rate = 8000
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0 or not result.stdout:
        return []

    samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float64)
    window = max(1, int(sample_rate * _VOLUME_WINDOW_S))
    n_windows = samples.size // window
    if n_windows < 3:
        return []

    rms = np.sqrt(np.mean(samples[: n_windows * window].reshape(n_windows, window) ** 2, axis=1))
    mean, std = rms.mean(), rms.std()
    if std <= 0:
        return []
    threshold = mean + _VOLUME_PEAK_STD_MULT * std

    peak_times: list[float] = []
    last_peak_t = -_VOLUME_PEAK_MIN_GAP_S
    for i in range(1, n_windows - 1):
        if rms[i] < threshold or rms[i] < rms[i - 1] or rms[i] < rms[i + 1]:
            continue
        t = i * _VOLUME_WINDOW_S
        if t - last_peak_t < _VOLUME_PEAK_MIN_GAP_S:
            continue
        peak_times.append(t)
        last_peak_t = t
        if len(peak_times) >= _VOLUME_PEAK_MAX_COUNT:
            break

    return peak_times


def _make_zoom_at(duration: float, peak_times: list[float]):
    """Zoom continuo (Ken Burns) + punch-in somado por cima nos picos de volume.

    O punch-in e um corte seco: pula pro zoom extra assim que entra na janela
    do pico e volta ao normal assim que sai dela, sem rampa de subida/descida -
    imita um corte de camera, nao uma animacao suave de zoom."""

    def zoom_at(t: float) -> float:
        kenburns = 1.0 + (_ZOOM_KENBURNS_MAX - 1.0) * min(1.0, t / duration) if duration > 0 else 1.0
        in_punch = any(0 <= t - peak_t < _ZOOM_PUNCH_HOLD_S for peak_t in peak_times)
        return kenburns + (_ZOOM_PUNCH_BUMP if in_punch else 0.0)

    return zoom_at


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
    frame,
    center_x: float,
    crop_w: int,
    crop_h: int,
    out_w: int,
    out_h: int,
    src_w: int,
    src_h: int,
    zoom: float = 1.0,
    center_y: float | None = None,
):
    # Zoom encolhe a area recortada mantendo a proporcao (evita distorcer a
    # imagem); com zoom=1.0 isso da exatamente o mesmo tamanho de recorte de
    # antes. Sem center_y explicito, ancora no centro vertical do frame (modo
    # 1 pessoa); no split-screen, quem chama passa o centro do rosto detectado.
    zoom_w = max(1, round(crop_w / zoom))
    zoom_h = max(1, round(crop_h / zoom))
    x0 = round(center_x - zoom_w / 2)
    x0 = max(0, min(x0, src_w - zoom_w))
    cy = center_y if center_y is not None else src_h / 2
    y0 = max(0, min(round(cy - zoom_h / 2), src_h - zoom_h))
    cropped = frame[y0 : y0 + zoom_h, x0 : x0 + zoom_w]
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
    (
        single_track,
        single_y_track,
        single_size_track,
        left_track,
        right_track,
        left_y_track,
        right_y_track,
        left_size_track,
        right_size_track,
        raw_mode,
    ) = _build_tracks(samples, src_w, src_h)
    mode_track = _debounce_mode(raw_mode)

    single_at = _make_x_at(_smooth(single_track))
    single_y_at = _make_x_at(_smooth(single_y_track))
    single_size_at = _make_x_at(_smooth(single_size_track))
    left_at = _make_x_at(_smooth(left_track))
    right_at = _make_x_at(_smooth(right_track))
    left_y_at = _make_x_at(_smooth(left_y_track))
    right_y_at = _make_x_at(_smooth(right_y_track))
    left_size_at = _make_x_at(_smooth(left_size_track))
    right_size_at = _make_x_at(_smooth(right_size_track))
    mode_at = _make_mode_at(mode_track)

    cap = cv2.VideoCapture(str(src_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if frame_count else 0.0

    if cancel_event is not None and cancel_event.is_set():
        raise PipelineCancelled("Cancelado durante o reenquadramento")
    peak_times = _detect_volume_peaks(src_path)
    zoom_at = _make_zoom_at(duration, peak_times)

    min_crop_h_single = src_h * _SINGLE_MIN_CROP_RATIO

    half_h = target_h // 2
    other_half_h = target_h - half_h
    half_aspect = target_w / half_h
    min_crop_h_half = src_h * _SPLIT_MIN_CROP_RATIO

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
                # Zoom desativado no split-screen - o corte ja fica mais fechado
                # (proporcional ao rosto), zoom em cima so deixaria "louco".
                crop_h_top = max(min_crop_h_half, left_size_at(t) * _SPLIT_FACE_HEIGHT_MULTIPLIER)
                crop_h_top = min(crop_h_top, src_h)
                crop_w_top = min(src_w, round(crop_h_top * half_aspect))
                top = _crop_and_resize(
                    frame, left_at(t), crop_w_top, crop_h_top, target_w, half_h, src_w, src_h,
                    center_y=left_y_at(t),
                )

                crop_h_bottom = max(min_crop_h_half, right_size_at(t) * _SPLIT_FACE_HEIGHT_MULTIPLIER)
                crop_h_bottom = min(crop_h_bottom, src_h)
                crop_w_bottom = min(src_w, round(crop_h_bottom * half_aspect))
                bottom = _crop_and_resize(
                    frame, right_at(t), crop_w_bottom, crop_h_bottom, target_w, other_half_h, src_w, src_h,
                    center_y=right_y_at(t),
                )
                combined = cv2.vconcat([top, bottom])
            else:
                # Corte proporcional ao tamanho do rosto detectado, igual ao
                # split-screen - se a fonte cortar pra uma camera mais aberta
                # (plano geral, cutaway), o rosto fica menor e o crop aperta
                # pra compensar, em vez de mostrar o quadro largo cru.
                crop_h_single = max(min_crop_h_single, single_size_at(t) * _SINGLE_FACE_HEIGHT_MULTIPLIER)
                crop_h_single = min(crop_h_single, src_h)
                crop_w_single = min(src_w, round(crop_h_single * TARGET_ASPECT))
                zoom = zoom_at(t)
                combined = _crop_and_resize(
                    frame, single_at(t), crop_w_single, crop_h_single, target_w, target_h, src_w, src_h, zoom,
                    center_y=single_y_at(t),
                )

            writer.write(combined)
            frame_idx += 1
    finally:
        writer.release()
        cap.release()

    return mode_track
