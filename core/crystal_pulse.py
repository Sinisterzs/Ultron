"""
HoloCrystal — Modelo visual Crystal Pulse para o HUD do Mark LVI.

Conceito aprovado:
    Cristal holográfico vermelho tridimensional com facetas luminosas, rotação suave
    e anel de pulso energético reativo à voz.

Tecnologia:
    PyQt6 + QPainter puro (sem shaders, sem OpenGL, sem QML, ultra-leve).
    Compatível com a API do HoloEye:
        crystal.step(dt, amp, speaking=..., muted=..., state=...)
        crystal.paint(painter, cx, cy, r, primary, accent, bg)
        crystal.glance(dx, dy, hold=...)
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
    QPolygonF,
    QRadialGradient,
    QLinearGradient,
    QImage,
)

SPAN: float = 1.80


def _rate(dt: float, tau: float) -> float:
    """Suavizacao exponencial independente da taxa de quadros."""
    if dt <= 0.0:
        return 0.0
    return 1.0 - math.exp(-dt / max(tau, 1e-6))


def _c(col: QColor, a: float) -> QColor:
    """Copia a cor com alpha ajustado (0..255)."""
    q = QColor(col)
    q.setAlpha(int(max(0.0, min(255.0, a))))
    return q


# ── GEOMETRIA DO CRISTAL PRINCIPAL (10 Vertices, 16 Facetas Triangulares) ────
# ── GEOMETRIA DO CRISTAL PRINCIPAL (10 Vertices, 16 Facetas Triangulares) ────
# O cristal e vertical: eixo Y e a altura (topo negativo=cima, base positiva=baixo).
# Eixos X e Z formam o plano horizontal equatorial.
_H_TIP = 1.82
_R_RING = 0.72
_Y_RING = 0.36

_CRYSTAL_VERTS = np.array([
    [0.0, -_H_TIP, 0.0],  # 0: Topo pontiagudo
    [_R_RING, -_Y_RING, 0.0],  # 1 (0 deg)
    [0.0, -_Y_RING, _R_RING],  # 2 (90 deg)
    [-_R_RING, -_Y_RING, 0.0],  # 3 (180 deg)
    [0.0, -_Y_RING, -_R_RING],  # 4 (270 deg)
    [_R_RING * 0.7071, _Y_RING, _R_RING * 0.7071],  # 5 (45 deg)
    [-_R_RING * 0.7071, _Y_RING, _R_RING * 0.7071],  # 6 (135 deg)
    [-_R_RING * 0.7071, _Y_RING, -_R_RING * 0.7071],  # 7 (225 deg)
    [_R_RING * 0.7071, _Y_RING, -_R_RING * 0.7071],  # 8 (315 deg)
    [0.0, _H_TIP, 0.0],  # 9: Base pontiaguda
], dtype=np.float32)

_CRYSTAL_FACES = [
    # Top cap (4 triangulos)
    (0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
    # Cintura antiprismatica (8 triangulos)
    (1, 5, 2), (2, 5, 6), (2, 6, 3), (3, 6, 7),
    (3, 7, 4), (4, 7, 8), (4, 8, 1), (1, 8, 5),
    # Bottom cap (4 triangulos)
    (9, 6, 5), (9, 7, 6), (9, 8, 7), (9, 5, 8),
]

# ── NUCLEO ENERGETICO INTERNO (Octaedro com 6 Vertices, 8 Facetas) ───────────
_CORE_R = 0.32
_CORE_H = 0.65
_CORE_VERTS = np.array([
    [0.0, -_CORE_H, 0.0],   # 0: Topo core
    [_CORE_R, 0.0, 0.0],    # 1
    [0.0, 0.0, _CORE_R],    # 2
    [-_CORE_R, 0.0, 0.0],   # 3
    [0.0, 0.0, -_CORE_R],   # 4
    [0.0, _CORE_H, 0.0],    # 5: Base core
], dtype=np.float32)

_CORE_FACES = [
    (0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
    (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4),
]


def _compute_face_normals(verts, faces):
    """Pré-computa normais unitárias das faces no espaço do objeto (feito uma vez)."""
    normals = []
    for i0, i1, i2 in faces:
        e1 = verts[i1] - verts[i0]
        e2 = verts[i2] - verts[i0]
        n = np.cross(e1, e2)
        n_len = np.linalg.norm(n)
        if n_len > 1e-6:
            n = n / n_len
        else:
            n = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        normals.append(n)
    return np.array(normals, dtype=np.float32)


# Normais pré-computadas (espaço do objeto) — transformadas pela matriz de rotação
# no paint(), evitando produto vetorial + normalização por frame, por face.
_CRYSTAL_FACE_NORMALS = _compute_face_normals(_CRYSTAL_VERTS, _CRYSTAL_FACES)
_CORE_FACE_NORMALS = _compute_face_normals(_CORE_VERTS, _CORE_FACES)

# Preto transparente reutilizado (evita criar QColor(0,0,0,0) a cada frame)
_TRANSPARENT_BLACK = QColor(0, 0, 0, 0)



def _gaussian_blur_image(image: QImage, sigma: float = 5.0) -> QImage:
    """Fast Gaussian-like bloom via 3 separable box filters (integral sums).

    Three passes of a box filter closely approximate Gaussian softness, but
    avoid the original ~62 full-frame weighted NumPy operations per update.
    The small premultiplied RGBA emission image is the only thing blurred.
    """
    # The emission layer already uses this format: avoid an unnecessary copy.
    if image.format() != QImage.Format.Format_ARGB32_Premultiplied:
        image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    h, w = image.height(), image.width()
    raw = image.constBits().asarray(image.sizeInBytes())
    pixels = np.frombuffer(raw, dtype=np.uint8).reshape(h, image.bytesPerLine())[:, :w * 4]
    data = pixels.reshape(h, w, 4).astype(np.float32)

    # Three odd box widths approximating a normal distribution with sigma.
    n = 3
    ideal = math.sqrt(12.0 * sigma * sigma / n + 1.0)
    lower = max(3, int(math.floor(ideal)))
    if lower % 2 == 0:
        lower -= 1
    upper = lower + 2
    count_lower = round((12.0 * sigma * sigma - n * lower * lower
                         - 4 * n * lower - 3 * n) / (-4.0 * lower - 4.0))
    count_lower = max(0, min(n, count_lower))
    widths = [lower] * count_lower + [upper] * (n - count_lower)

    def box_axis(a: np.ndarray, radius: int, axis: int) -> np.ndarray:
        if radius <= 0:
            return a
        pads = [(0, 0)] * a.ndim
        pads[axis] = (radius, radius)
        # Zero outside the texture, so the light does not smear over boundaries.
        padded = np.pad(a, pads, mode='constant')
        # Prefix with a zero along the filtered dimension to create identical
        # window lengths everywhere, without a Python loop over filter taps.
        origin_shape = list(padded.shape)
        origin_shape[axis] = 1
        sums = np.concatenate((np.zeros(origin_shape, dtype=np.float32),
                               np.cumsum(padded, axis=axis, dtype=np.float32)),
                              axis=axis)
        length = 2 * radius + 1
        if axis == 0:
            return (sums[length:, :, :] - sums[:-length, :, :]) / length
        return (sums[:, length:, :] - sums[:, :-length, :]) / length

    for width in widths:
        radius = width // 2
        data = box_axis(data, radius, 1)
        data = box_axis(data, radius, 0)

    output = np.ascontiguousarray(np.clip(data, 0, 255).astype(np.uint8))
    return QImage(output.data, w, h, w * 4,
                  QImage.Format.Format_ARGB32_Premultiplied).copy()


class HoloCrystal:
    """Visualizador Crystal Pulse: cristal 3D holografico com anel de pulso reativo."""

    SPAN: float = SPAN

    def __init__(self) -> None:
        self._t: float = 0.0
        self._amp: float = 0.0
        self._amp_disp: float = 0.0
        self._amp_fast: float = 0.0

        # Estados logicos
        self._speaking: bool = False
        self._muted: bool = False
        self._state: str = ""

        # Cinematica de rotacao e olhar
        self._yaw: float = 0.0
        self._pitch: float = 0.28  # inclinacao fixa suave para visao 3D
        self._roll: float = 0.0
        self._core_yaw: float = 0.0

        # Dinamica de velocidade e energia
        self._rot_speed: float = 0.38
        self._energy: float = 0.40
        self._breathe: float = 0.0

        # Glance / Tilt interativo
        self._glance_x: float = 0.0
        self._glance_y: float = 0.0
        self._glance_tgt: tuple[float, float, float] = (0.0, 0.0, 0.0)

        # Anel de pulso e ondas concentricas
        self._ring_angle: float = 0.0
        self._sub_ring_angle: float = 0.0
        self._pulse_waves = [
            {"phase": 0.0, "speed": 0.85},
            {"phase": 0.33, "speed": 0.75},
            {"phase": 0.66, "speed": 0.65},
        ]

        # Vetor de luz direcional 3D normalizado
        lv = np.array([0.35, -0.45, 0.82], dtype=np.float32)
        self._light_dir = lv / np.linalg.norm(lv)

        # D19Q: cached diffuse light; sharp crystal and orbital lines still
        # render at the HUD's normal frame rate.
        self._bloom_cache: QImage | None = None
        # D20J: retain the reusable emission surface instead of allocating
        # a fresh QImage on every bloom refresh.
        self._bloom_emission: QImage | None = None
        self._bloom_emission_side: int = 0
        # Warm up the same NumPy blur path before the HUD starts animating.
        # This moves first-use allocations to construction rather than paint.
        self.prewarm_bloom()
        self._bloom_last_t: float = -1.0
        self._bloom_last_size: int = 0
        self._bloom_last_r: float = 0.0
        self._bloom_last_palette: tuple[int, int] | None = None
        self._bloom_last_voice: float = -1.0
        self._bloom_last_energy: float = -1.0

    def prewarm_bloom(self) -> None:
        """Optional warm-up before showing the window (never call in paintEvent).

        Initializes NumPy/Qt processing with a representative bloom-size image.
        This may move first-use overhead into startup, not eliminate OS stalls.
        """
        if getattr(self, "_bloom_preheated", False):
            return
        self._bloom_preheated = True
        sample = QImage(160, 160, QImage.Format.Format_ARGB32_Premultiplied)
        sample.fill(Qt.GlobalColor.transparent)
        _gaussian_blur_image(sample, sigma=4.1)

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Inclina suavemente a orientacao do cristal para olhar em uma direcao."""
        self._glance_tgt = (float(dx), float(dy), self._t + float(hold))

    def step(
        self,
        dt: float,
        amp: float,
        speaking: bool = False,
        muted: bool = False,
        state: str = "",
        **kw,
    ) -> None:
        """Avanca o estado fisico e temporal da animacao."""
        dt = max(0.0, min(0.1, dt))
        self._t += dt
        self._speaking = bool(speaking)
        self._muted = bool(muted)
        self._state = str(state or "").upper()

        # Suavizacao da amplitude de voz com constante temporal independente de FPS
        r_up = _rate(dt, 0.045)
        r_down = _rate(dt, 0.22)
        if amp > self._amp_fast:
            self._amp_fast += (amp - self._amp_fast) * r_up
        else:
            self._amp_fast += (amp - self._amp_fast) * r_down

        r_disp = _rate(dt, 0.12)
        self._amp_disp += (self._amp_fast - self._amp_disp) * r_disp
        self._amp = self._amp_disp

        # Fase de respiracao continua
        self._breathe += dt * 1.8

        # Alvos conforme os estados formais
        if self._muted:
            tgt_speed = 0.15
            tgt_energy = 0.15
        elif self._state in ("THINKING", "PROCESSING"):
            tgt_speed = 1.25
            tgt_energy = 0.85 + 0.15 * math.sin(self._t * 6.0)
        elif self._speaking:
            tgt_speed = 0.65 + 0.55 * self._amp
            tgt_energy = 0.70 + 0.65 * self._amp
        elif self._state == "LISTENING":
            tgt_speed = 0.45
            tgt_energy = 0.55 + 0.25 * math.sin(self._breathe * 1.5)
        else:  # IDLE
            tgt_speed = 0.32
            tgt_energy = 0.38 + 0.18 * math.sin(self._breathe)

        # Transicao suave de velocidade e energia
        self._rot_speed += (tgt_speed - self._rot_speed) * _rate(dt, 0.30)
        self._energy += (tgt_energy - self._energy) * _rate(dt, 0.25)

        # Rotacao do cristal e do miolo interno
        self._yaw += self._rot_speed * dt
        self._core_yaw -= (self._rot_speed * 1.4 + 0.2) * dt

        # Anel de pulso rotacao
        self._ring_angle += (0.45 + 0.3 * self._energy) * dt
        self._sub_ring_angle -= (0.35 + 0.25 * self._energy) * dt

        # Glance decaimento / rastreamento
        gx_tgt, gy_tgt, g_until = self._glance_tgt
        if self._t > g_until:
            gx_tgt, gy_tgt = 0.0, 0.0
        r_g = _rate(dt, 0.25)
        self._glance_x += (gx_tgt - self._glance_x) * r_g
        self._glance_y += (gy_tgt - self._glance_y) * r_g

        # Propagacao de ondas de pulso
        wave_boost = 1.0 + 1.4 * self._amp if self._speaking else 0.8
        for w in self._pulse_waves:
            w["phase"] = (w["phase"] + dt * w["speed"] * wave_boost) % 1.0

    def paint(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        r: float,
        primary: QColor,
        accent: QColor,
        bg: QColor,
    ) -> None:
        """Renderiza o modelo Crystal Pulse no canvas do HUD."""
        if r <= 2.0 or not painter.isActive():
            return

        p = painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # D19I: the HUD provides orange (#ff6b00) when speaking. Crystal Pulse
        # deliberately has a monochromatic red identity in all active states.
        # Preserve the muted grey palette when the microphone is muted.
        pri = QColor(primary)
        acc = QColor(primary)
        if not self._muted:
            acc.setRed(max(190, pri.red()))
            acc.setGreen(min(32, pri.green()))
            acc.setBlue(min(70, pri.blue()))
        energy = max(0.0, min(1.5, self._energy))
        amp = max(0.0, min(1.0, self._amp))

        # 1. Aura Central / Brilho Difuso de Fundo
        aura_r = r * (0.56 + 0.07 * amp + 0.025 * math.sin(self._breathe))
        aura_grad = QRadialGradient(cx, cy, aura_r)
        aura_alpha = int(28 + 40 * energy + 52 * amp)
        aura_grad.setColorAt(0.0, _c(acc, aura_alpha))
        aura_grad.setColorAt(0.35, _c(pri, int(aura_alpha * 0.40)))
        aura_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(aura_grad))
        p.drawEllipse(QRectF(cx - aura_r, cy - aura_r, aura_r * 2.0, aura_r * 2.0))

        # 2. Ondas de Pulso de Voz Expansivas
        self._paint_voice_pulse_waves(p, cx, cy, r, pri, acc, amp, energy)

        # 3. Aneis Tecnologicos / Segmentados de Energia
        self._paint_energy_rings(p, cx, cy, r, pri, acc, amp, energy)

        # 4. Matriz de Transformacao 3D do Cristal
        # Rotacao principal em torno do eixo vertical Y (yaw)
        yaw = self._yaw
        Ry = np.array([
            [math.cos(yaw), 0.0, math.sin(yaw)],
            [0.0, 1.0, 0.0],
            [-math.sin(yaw), 0.0, math.cos(yaw)],
        ], dtype=np.float32)

        # Inclinacao suave em direcao a camera (pitch ~ 12 deg + glance)
        pitch = 0.20 + self._glance_y * 0.22
        Rx = np.array([
            [1.0, 0.0, 0.0],
            [0.0, math.cos(pitch), -math.sin(pitch)],
            [0.0, math.sin(pitch), math.cos(pitch)],
        ], dtype=np.float32)

        # Roll suave com glance
        roll = self._glance_x * 0.18
        Rz = np.array([
            [math.cos(roll), -math.sin(roll), 0.0],
            [math.sin(roll), math.cos(roll), 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)

        R_rot = Rz @ Rx @ Ry

        # Projecao do Cristal Interno (Core em rotacao contrarrotativa)
        core_yaw = self._core_yaw
        core_Ry = np.array([
            [math.cos(core_yaw), 0.0, math.sin(core_yaw)],
            [0.0, 1.0, 0.0],
            [-math.sin(core_yaw), 0.0, math.cos(core_yaw)],
        ], dtype=np.float32)
        core_R = Rz @ Rx @ core_Ry
        core_scale = r * 0.30 * (1.0 + 0.12 * amp)
        self._paint_polyhedron(
            p, cx, cy, r,
            verts_3d=_CORE_VERTS * core_scale,
            faces=_CORE_FACES,
            normals_3d=_CORE_FACE_NORMALS,
            rot_mat=core_R,
            primary=pri,
            accent=acc,
            is_core=True,
            energy=energy,
            amp=amp,
        )

        # Projecao do Cristal Principal
        crystal_scale = r * 0.50 * (1.0 + 0.04 * amp)
        self._paint_polyhedron(
            p, cx, cy, r,
            verts_3d=_CRYSTAL_VERTS * crystal_scale,
            faces=_CRYSTAL_FACES,
            normals_3d=_CRYSTAL_FACE_NORMALS,
            rot_mat=R_rot,
            primary=pri,
            accent=acc,
            is_core=False,
            energy=energy,
            amp=amp,
        )

        # 5. Concentrated ruby energy lens: sharp centre, soft local falloff.
        # The black background outside the crystal remains untouched.
        lens_radius = r * (0.17 + 0.035 * amp)
        lens = QRadialGradient(cx, cy, lens_radius)
        lens.setColorAt(0.0, QColor(255, 48, 80, min(220, int(110 + 75 * energy + 50 * amp))))
        lens.setColorAt(0.19, QColor(255, 18, 47, min(160, int(60 + 50 * energy + 45 * amp))))
        lens.setColorAt(0.58, QColor(154, 0, 23, 22))
        lens.setColorAt(1.0, _TRANSPARENT_BLACK)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(lens))
        p.drawEllipse(QRectF(cx - lens_radius, cy - lens_radius,
                             lens_radius * 2.0, lens_radius * 2.0))

        # Small travelling light glints on the near orbit, not a full glow halo.
        orbit_r = r * 0.84
        for phase in (0.0, 2.094, 4.189):
            ang = self._ring_angle + phase
            sx = cx + math.cos(ang) * orbit_r
            sy = cy + math.sin(ang) * orbit_r
            p.setPen(QPen(QColor(255, 55, 82, int(85 + 85 * energy)), 2.0))
            p.drawPoint(QPointF(sx, sy))

        # 6. Ponto Central de Foco Energetico (Glow Core)
        core_dot_r = r * (0.040 + 0.020 * amp)
        core_glow = QRadialGradient(cx, cy, core_dot_r * 2.0)
        dot_a = min(255, int(155 + 65 * amp + 18 * energy))
        core_glow.setColorAt(0.0, _c(acc, dot_a))
        core_glow.setColorAt(0.38, _c(pri, int(dot_a * 0.58)))
        core_glow.setColorAt(1.0, _TRANSPARENT_BLACK)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core_glow))
        p.drawEllipse(QRectF(cx - core_dot_r * 2.0, cy - core_dot_r * 2.0,
                             core_dot_r * 4.0, core_dot_r * 4.0))

        p.restore()

    def _paint_voice_pulse_waves(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        pri: QColor,
        acc: QColor,
        amp: float,
        energy: float,
    ) -> None:
        """Desenha ondas circulares expansivas que emanam do cristal conforme a voz."""
        base_r = r * 0.55
        max_r = r * 0.98

        p.setBrush(Qt.BrushStyle.NoBrush)
        for wave in self._pulse_waves:
            ph = wave["phase"]
            wr = base_r + (max_r - base_r) * ph
            alpha_fade = math.sin(ph * math.pi)
            alpha = int(alpha_fade * (30 + 130 * amp + 35 * energy))

            if alpha <= 2:
                continue

            pen_w = 1.0 + 1.2 * (1.0 - ph)
            p.setPen(QPen(_c(acc if ph < 0.5 else pri, alpha), pen_w))
            p.drawEllipse(QRectF(cx - wr, cy - wr, wr * 2.0, wr * 2.0))

    def _paint_energy_rings(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        pri: QColor,
        acc: QColor,
        amp: float,
        energy: float,
        _bloom_pass: bool = False,
    ) -> None:
        """D19L: two independent tilted 3D-looking orbital rings.

        Each short arc is projected from a tilted circle. Continuous depth
        lighting avoids abrupt colour/alpha changes as the rings rotate.
        """
        # D19P: render a clean, narrow emissive orbit into an offscreen layer,
        # then apply a true separable Gaussian blur before composite.  Drawing
        # many fat round-capped microsegments caused the visible checker texture.
        if not _bloom_pass:
            extent = r * 1.07
            # Keep the spatial blur radius similar to D19P, while reducing
            # the offscreen pixel count and recalculating at most 10 Hz.
            # D19S: cap bloom texture size in maximized/fullscreen windows.
            # Sharp rings and facets still render at the full widget resolution.
            scale = 0.40
            nominal_side = max(48, int(math.ceil(2.0 * extent * scale)))
            side = min(160, nominal_side)
            palette_key = (pri.rgba(), acc.rgba())
            needs_refresh = (
                self._bloom_cache is None
                or self._bloom_last_size != side
                or abs(self._bloom_last_r - r) > 0.5
                or self._bloom_last_palette != palette_key
                or self._t < self._bloom_last_t
                or self._t - self._bloom_last_t >= 0.20
            )
            if needs_refresh:
                if self._bloom_emission is None or self._bloom_emission_side != side:
                    self._bloom_emission = QImage(
                        side, side, QImage.Format.Format_ARGB32_Premultiplied
                    )
                    self._bloom_emission_side = side
                light = self._bloom_emission
                light.fill(Qt.GlobalColor.transparent)
                gp = QPainter(light)
                gp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                gp.scale(side / (2.0 * extent), side / (2.0 * extent))
                gp.translate(extent - cx, extent - cy)
                self._paint_energy_rings(gp, cx, cy, r, pri, acc, amp, energy, True)
                gp.end()
                # Keep the glow's apparent width when the internal resolution
                # is capped; do not let a fixed pixel sigma shrink fullscreen.
                blur_sigma = max(2.0, 4.1 * side / nominal_side)
                self._bloom_cache = _gaussian_blur_image(light, sigma=blur_sigma)
                self._bloom_last_t = self._t
                self._bloom_last_size = side
                self._bloom_last_r = r
                self._bloom_last_palette = palette_key
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(QRectF(cx - extent, cy - extent, 2.0 * extent, 2.0 * extent),
                        self._bloom_cache)
            p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Reuse the existing smoothed energy/voice signals and ring angles.
        voice = min(1.0, amp)
        radius_pulse = 1.0 + 0.025 * voice

        # (radius, tilt around X, tilt around Y, phase, segment count, line width)
        rings = (
            (0.84, 0.58, -0.36, self._ring_angle, 4, 1.35),
            (0.69, -0.46, 0.51, self._sub_ring_angle, 5, 0.95),
        )
        for ring_idx, (radius, tilt_x, tilt_y, phase, segments, width) in enumerate(rings):
            ring_r = r * radius * radius_pulse
            sx, cx_t = math.sin(tilt_x), math.cos(tilt_x)
            sy, cy_t = math.sin(tilt_y), math.cos(tilt_y)
            # Angular position determines a *moving* series of lit sections.
            # Geometry is fixed in space; pattern moves, no hard on/off edges.
            count = 108 if ring_idx == 0 else 90
            base_alpha = (47 if ring_idx == 0 else 33) + 29 * energy + 44 * voice
            gap = 0.30 if ring_idx == 0 else 0.42
            # One projection per vertex, shared by neighbouring segments.
            # Ring geometry itself is static; only visibility and colour move.
            projected = []
            for j in range(count + 1):
                theta = math.tau * j / count
                x = math.cos(theta)
                y = math.sin(theta) * cx_t
                z = math.sin(theta) * sx
                xx = x * cy_t + z * sy
                zz = -x * sy + z * cy_t
                factor = 1.0 + zz * 0.055
                projected.append((QPointF(cx + ring_r * xx * factor,
                                          cy + ring_r * y * factor), zz))
            for i in range(count):
                tm = math.tau * (i + 0.5) / count
                # Cosine-lobe segmentation: all fades continuous.
                pattern = math.cos(segments * (tm - phase))
                visibility = max(0.0, (pattern + gap) / (1.0 + gap))
                visibility = visibility * visibility * (3.0 - 2.0 * visibility)
                if visibility < 0.014:
                    continue

                pt0, z0 = projected[i]
                pt1, z1 = projected[i + 1]
                depth = 0.5 + 0.5 * (z0 + z1) * 0.5
                # Rear arc quieter; near arc illuminated smoothly.
                alpha = int(base_alpha * visibility * (0.38 + 0.62 * depth))
                if alpha < 2:
                    continue
                filament_w = width * (0.85 + 0.3 * depth)
                if _bloom_pass:
                    # One emission stroke only; the Gaussian kernel supplies
                    # the softness instead of stacked, rounded wide strokes.
                    boost = 1.0 + 0.35 * voice + 0.15 * energy
                    p.setPen(QPen(QColor(255, 12, 46,
                                         min(230, int(alpha * 1.55 * boost))),
                                  filament_w + 4.0,
                                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
                    p.drawLine(pt0, pt1)
                    continue
                # D19U: the cached Gaussian layer supplies the soft halo.
                # Keep just the sharp filament here; the old extra wide stroke
                # doubled draw calls on every short orbit segment.
                p.setPen(QPen(_c(pri, alpha), filament_w,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(pt0, pt1)

            if _bloom_pass:
                continue
            # Tiny orbital marker: slow motion, fades on the far side.
            marker_t = phase + (0.6 if ring_idx == 0 else 2.1)
            xx = math.cos(marker_t)
            yy = math.sin(marker_t) * cx_t
            zz = math.sin(marker_t) * sx
            x_final = xx * cy_t + zz * sy
            z_final = -xx * sy + zz * cy_t
            depth = max(0.0, min(1.0, 0.5 + 0.5 * z_final))
            marker_alpha = int((55 + 95 * voice + 35 * energy) * (0.22 + 0.78 * depth))
            if marker_alpha > 4:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_c(acc, marker_alpha))
                dot_r = 1.6 + 0.7 * voice if ring_idx == 0 else 1.15
                dot_x = cx + ring_r * x_final * (1.0 + z_final * 0.055)
                dot_y = cy + ring_r * yy * (1.0 + z_final * 0.055)
                # Local radial glow gives the orbiting energy bead a halo.
                glow_r = dot_r * (4.2 + 0.5 * voice)
                glow = QRadialGradient(dot_x, dot_y, glow_r)
                glow.setColorAt(0.0, QColor(255, 45, 75, min(135, marker_alpha)))
                glow.setColorAt(0.35, QColor(240, 5, 40, min(48, int(marker_alpha * 0.35))))
                glow.setColorAt(1.0, _TRANSPARENT_BLACK)
                p.setBrush(QBrush(glow))
                p.drawEllipse(QRectF(dot_x - glow_r, dot_y - glow_r,
                                     glow_r * 2.0, glow_r * 2.0))
                p.setBrush(_c(acc, marker_alpha))
                p.drawEllipse(QRectF(dot_x - dot_r, dot_y - dot_r,
                                     dot_r * 2.0, dot_r * 2.0))
                p.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_polyhedron(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        verts_3d: np.ndarray,
        faces: Sequence[tuple[int, int, int]],
        normals_3d: np.ndarray,
        rot_mat: np.ndarray,
        primary: QColor,
        accent: QColor,
        is_core: bool,
        energy: float,
        amp: float,
    ) -> None:
        """Projeta e renderiza um poliedro 3D com iluminacao e ordenacao de profundidade."""
        v_rot = verts_3d @ rot_mat.T

        cam_d = 4.2
        z_norm = v_rot[:, 2] / max(1.0, r * 0.7)
        w = cam_d - z_norm
        np.maximum(w, 0.4, out=w)
        proj = cam_d / w

        px = cx + v_rot[:, 0] * proj
        py = cy + v_rot[:, 1] * proj

        # Transforma todas as normais de uma vez (matriz 3x3 x Nx3) — muito mais
        # barato que produto vetorial + normalizacao por frame, por face.
        n_rot = normals_3d @ rot_mat.T

        face_depths = []
        for idx, (i0, i1, i2) in enumerate(faces):
            avg_z = (v_rot[i0, 2] + v_rot[i1, 2] + v_rot[i2, 2]) / 3.0
            face_depths.append((avg_z, idx, i0, i1, i2))

        face_depths.sort(key=lambda item: item[0])

        for avg_z, f_idx, i0, i1, i2 in face_depths:
            n = n_rot[f_idx]

            diffuse = max(0.08, float(np.dot(n, self._light_dir)))
            is_front = n[2] > -0.05

            poly = QPolygonF([
                QPointF(px[i0], py[i0]),
                QPointF(px[i1], py[i1]),
                QPointF(px[i2], py[i2]),
            ])

            if is_core:
                # Compact, high-energy internal facets: deep scarlet to ruby red.
                shade = max(0.0, float(np.dot(n, self._light_dir)))
                face_alpha = min(235, int(95 + 95 * shade + 35 * amp))
                pen_alpha = min(255, int(125 + 95 * shade + 30 * amp))
                core_col = QColor(accent)
                core_col.setGreen(min(20, core_col.green()))
                core_col.setBlue(min(48, core_col.blue()))
                p.setPen(QPen(_c(core_col, pen_alpha), 1.0))
                p.setBrush(QBrush(_c(core_col, face_alpha)))
                p.drawPolygon(poly)
            else:
                # D19K: continuous orientation fade. Previously the hard
                # n.z > -0.05 branch switched a facet from ~20 alpha to
                # ~150-235 alpha in a single frame as it rotated.
                # Blend opacity, color and edge glow through a broad angular
                # interval instead of switching between front/back materials.
                facing = float(n[2])
                u = max(0.0, min(1.0, (facing + 0.42) / 0.72))
                visibility = u * u * (3.0 - 2.0 * u)  # smoothstep
                lit = max(0.0, float(np.dot(n, self._light_dir)))
                facet_variation = (0.65, 1.0, 0.48, 0.88, 0.60, 0.95, 0.52, 0.83,
                                   0.66, 0.98, 0.54, 0.76, 0.70, 0.93, 0.57, 0.86)[f_idx]
                brightness = min(1.0, (0.24 + 0.51 * lit + 0.25 * max(0.0, facing)) * facet_variation)
                red = min(255, int(125 + 130 * brightness + 20 * amp))
                green = min(36, int(5 + 23 * brightness))
                blue = min(66, int(15 + 39 * brightness))

                back_alpha = 12 + 17 * energy
                front_alpha = min(245, 115 + 100 * brightness + 20 * energy)
                face_alpha = int(back_alpha + (front_alpha - back_alpha) * visibility)
                back_pen_alpha = 28 + 18 * energy
                front_pen_alpha = min(250, 115 + 100 * brightness + 20 * amp)
                pen_alpha = int(back_pen_alpha + (front_pen_alpha - back_pen_alpha) * visibility)
                pen_w = 0.70 + (0.35 + 0.35 * min(1.0, lit / 0.55)) * visibility

                # Avoid color snaps as the facet rotates out of view: hue
                # is always ruby, while opacity and specularity fade smoothly.
                face_grad = QLinearGradient(px[i0], py[i0],
                                            (px[i1] + px[i2]) * 0.5,
                                            (py[i1] + py[i2]) * 0.5)
                face_grad.setColorAt(0.0, _c(QColor(min(255, red + 32),
                                                     min(45, green + 8),
                                                     min(83, blue + 15)),
                                               min(255, face_alpha + int(20 * visibility))))
                face_grad.setColorAt(0.48, _c(QColor(red, green, blue), face_alpha))
                face_grad.setColorAt(1.0, _c(QColor(int(red * 0.38),
                                                     int(green * 0.44),
                                                     int(blue * 0.5)), face_alpha))
                pen_col = _c(QColor(min(255, red + 35), min(42, green + 9),
                                    min(80, blue + 15)), pen_alpha)
                p.setPen(QPen(pen_col, pen_w))
                p.setBrush(QBrush(face_grad))
                p.drawPolygon(poly)
                # Soft edge bloom with smoothly interpolated visibility.
                # Keep it restrained: faces stay sharp, only select lit
                # ridges catch the holographic light.
                if f_idx % 3 == 0:
                    glow_alpha = int((11 + 22 * lit + 12 * amp) * visibility)
                    if glow_alpha > 1:
                        p.setPen(QPen(QColor(255, 20, 55, glow_alpha), 5.0,
                                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        p.drawLine(QPointF(px[i0], py[i0]), QPointF(px[i1], py[i1]))

                # The specular ridge fades with orientation as well, instead
                # of appearing abruptly at lit > 0.35 / front == True.
                if f_idx % 3 == 0:
                    ridge_strength = max(0.0, min(1.0, (lit - 0.15) / 0.45))
                    ridge_strength *= ridge_strength * (3.0 - 2.0 * ridge_strength)
                    ridge_alpha = int((62 + 90 * lit + 55 * amp) * visibility * ridge_strength)
                    if ridge_alpha > 1:
                        p.setPen(QPen(_c(QColor(255, 78, 112), ridge_alpha), 0.8))
                        p.drawLine(QPointF(px[i0], py[i0]), QPointF(px[i1], py[i1]))

        if not is_core:
            # Vertex glints also fade with depth instead of switching on/off.
            for vi in (0, 9):
                depth = float(v_rot[vi, 2]) / max(1.0, r * 0.7)
                u = max(0.0, min(1.0, (depth + 0.24) / 0.48))
                fade = u * u * (3.0 - 2.0 * u)
                alpha = int((150 + 105 * amp) * fade)
                if alpha > 1:
                    p.setPen(QPen(_c(accent, alpha), 2.2))
                    p.drawPoint(QPointF(px[vi], py[vi]))

