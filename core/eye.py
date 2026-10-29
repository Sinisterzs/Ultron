"""Holographic dark-eye avatar for the MARK LVI HUD.

Software-rendered single eye avatar with:
- Dark sclera with subtle vessels
- Radial iris gradient (deep dark red outer to bright inner)
- Fine radial striations and subtle concentric rings using numpy
- Deep black pupil with live dilation / audio-reactive pulse
- Specular / light reflection catchlights
- Pulsing atmospheric outer glow (QRadialGradient)
- Eyelid blink, saccades, wander, glance tracking, and sleeping/muted/thinking states
"""

import math
import random
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


def _rate(dt: float, tau: float) -> float:
    """Frame-rate independent exponential smoothing coefficient."""
    if dt <= 0.0:
        return 0.0
    return 1.0 - math.exp(-dt / tau)


def _c(col: QColor, a: float) -> QColor:
    """Copy of `col` at alpha `a` (0-255, clamped)."""
    q = QColor(col)
    q.setAlpha(int(max(0.0, min(255.0, a))))
    return q


def _blend(bg: QColor, col: QColor, a: float) -> QColor:
    """`col` at alpha `a` pre-mixed onto `bg`, returned fully opaque."""
    f = max(0.0, min(1.0, a / 255.0))
    return QColor(
        int(bg.red() + (col.red() - bg.red()) * f),
        int(bg.green() + (col.green() - bg.green()) * f),
        int(bg.blue() + (col.blue() - bg.blue()) * f),
    )


# 12 edges of a unit cube connecting the 8 vertices
_CUBE_VERTS = np.array([
    [-1, -1, -1],
    [ 1, -1, -1],
    [ 1,  1, -1],
    [-1,  1, -1],
    [-1, -1,  1],
    [ 1, -1,  1],
    [ 1,  1,  1],
    [-1,  1,  1],
], dtype=np.float32)

_CUBE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),  # back face
    (4, 5), (5, 6), (6, 7), (7, 4),  # front face
    (0, 4), (1, 5), (2, 6), (3, 7),  # connecting edges
]


class HoloEye:
    """Animated holographic single dark eye. Drop-in replacement for HoloAvatar.

    Lifecycle:
        eye = HoloEye()
        eye.step(dt, amp, speaking=..., muted=...)
        eye.paint(painter, cx, cy, r, primary, accent, bg)
        eye.glance(dx, dy, hold=1.1)
    """

    # Head-half-heights span. Set to 1.80 so sizing matches the HUD band identically
    SPAN: float = 1.80

    # Tech overlay effects toggle (can be toggled per-instance or class-wide)
    fx: bool = True

    def __init__(self) -> None:
        self._t: float = 0.0

        # Gaze / saccade tracking
        self._gaze: list[float] = [0.0, 0.0]
        self._gaze_tgt: list[float] = [0.0, 0.0]
        self._gaze_at: float = 0.0

        self._gaze_bias: list[float] = [0.0, 0.0]
        self._bias_tgt: list[float] = [0.0, 0.0]
        self._bias_at: float = 0.0

        self._glance: tuple[float, float, float] | None = None  # (dx, dy, until_t)

        # Lids and blinking (0.0 = fully open, 1.0 = fully shut)
        self._blink: float = 0.0
        self._blink_at: float = 2.5
        self._cur_lid: float = 1.0  # smoothed lid level

        # Audio energy & breathing
        self._glow: float = 0.0       # audio-smoothed glow 0..1
        self._amp_slow: float = 0.0   # lazy audio envelope
        self._breathe: float = 0.0    # cyclic slow breathing phase

        # Pupil dynamics
        self._pupil_scale: float = 1.0

        # ── Tech FX Parameters ──────────────────────────────────────────────
        self._state_str: str = ""
        self._is_speaking: bool = False
        self._is_muted: bool = False

        self._fx_energy: float = 0.2     # smoothed visual energy / brightness
        self._orbit_speed: float = 0.4   # smoothed orbit rotation speed
        self._orbit_dist_fac: float = 1.0 # smoothed orbit radius multiplier

        # 6 cubes orbiting parameters:
        # [base_angle, inclination_x, inclination_y, self_rot_x, self_rot_y, self_rot_z]
        self._cube_angles = [i * (2.0 * math.pi / 6.0) for i in range(6)]
        self._cube_incls = [
            (0.35, 0.20),
            (-0.45, 0.50),
            (0.60, -0.30),
            (-0.30, -0.55),
            (0.50, 0.40),
            (-0.60, -0.25),
        ]
        self._cube_spin = [0.0] * 6

        # Background data ring and scanlines phase
        self._data_ring_angle: float = 0.0
        self._scan_phase: float = 0.0

        # Pre-computed radial striation noise for iris (360 samples)
        rng = np.random.RandomState(42)
        n_rays = 360
        base_noise = rng.uniform(0.65, 1.35, n_rays)
        kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
        self._iris_rays = np.convolve(np.tile(base_noise, 3), kernel, mode="same")[
            n_rays : 2 * n_rays
        ]

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Look deliberately somewhere for `hold` seconds, then return to wandering."""
        self._glance = (
            max(-1.0, min(1.0, float(dx))),
            max(-1.0, min(1.0, float(dy))),
            self._t + max(0.1, float(hold)),
        )

    def step(
        self,
        dt: float,
        amp: float,
        speaking: bool = False,
        muted: bool = False,
        state: str = "",
        v_open: float | None = None,
        v_wide: float = 0.0,
        v_level: float | None = None,
        v_seq: list | None = None,
        v_hop: float = 0.02,
    ) -> None:
        """Advance eye dynamics. Frame-rate independent using dt."""
        self._t += dt
        t = self._t
        live = speaking and not muted
        self._state_str = state
        self._is_speaking = speaking
        self._is_muted = muted

        # Slow breathing cycle
        self._breathe += dt * 1.5

        # Audio envelope smoothing
        env = amp if live else 0.0
        self._amp_slow += (env - self._amp_slow) * _rate(
            dt, 0.12 if env > self._amp_slow else 0.35
        )

        glow_tgt = 0.0 if muted else (amp if live else 0.0)
        self._glow += (glow_tgt - self._glow) * _rate(
            dt, 0.15 if glow_tgt > self._glow else 0.45
        )

        # ── State expression ────────────────────────────────────────────────
        st = (state or "").upper()
        thinking = st in ("THINKING", "PROCESSING")
        asleep = st in ("SLEEPING", "STANDBY", "OFFLINE")

        if muted:
            lid_tgt = 0.18
            self._bias_tgt = [0.0, -0.3]
        elif asleep:
            lid_tgt = 0.15
            self._bias_tgt = [0.0, -0.4]
        elif thinking:
            lid_tgt = 0.88
            if t >= self._bias_at:
                self._bias_tgt = [
                    random.choice((-1.0, 1.0)) * random.uniform(0.45, 0.85),
                    random.uniform(0.3, 0.65),
                ]
                self._bias_at = t + 1.5 + 1.8 * random.random()
        elif st == "LISTENING":
            lid_tgt = 1.05
            self._bias_tgt = [0.0, 0.0]
            self._bias_at = 0.0
        else:
            lid_tgt = 1.0
            self._bias_tgt = [0.0, 0.0]
            self._bias_at = 0.0

        # ── Tech FX Step ────────────────────────────────────────────────────
        if muted:
            target_fx_speed = 0.05
            target_fx_dist = 1.05
            target_fx_energy = 0.05
        elif thinking:
            target_fx_speed = 2.4
            target_fx_dist = 0.78  # orbit closer
            target_fx_energy = 0.95
        elif st == "LISTENING":
            target_fx_speed = 1.15
            target_fx_dist = 0.95
            target_fx_energy = 0.55
        elif live:
            target_fx_speed = 0.8 + 1.0 * amp
            target_fx_dist = 1.0
            target_fx_energy = 0.45 + 0.55 * amp
        else:
            target_fx_speed = 0.45
            target_fx_dist = 1.0
            target_fx_energy = 0.22

        self._orbit_speed += (target_fx_speed - self._orbit_speed) * _rate(dt, 0.25)
        self._orbit_dist_fac += (target_fx_dist - self._orbit_dist_fac) * _rate(dt, 0.30)
        self._fx_energy += (target_fx_energy - self._fx_energy) * _rate(dt, 0.20)

        # Advance orbits & cube spins
        orbit_delta = dt * self._orbit_speed
        for i in range(6):
            self._cube_angles[i] += orbit_delta * (1.0 + 0.12 * i)
            self._cube_spin[i] += dt * (1.8 + 0.5 * i) * (0.2 if muted else (1.8 if thinking else 1.0))

        # Advance data ring and scan lines
        ring_rate = 0.2 if muted else (1.5 if thinking else (0.8 if st == "LISTENING" else 0.4))
        self._data_ring_angle += dt * ring_rate
        self._scan_phase = (self._scan_phase + dt * 0.18) % 1.0

        for i in (0, 1):
            self._gaze_bias[i] += (self._bias_tgt[i] - self._gaze_bias[i]) * _rate(
                dt, 0.30
            )

        self._cur_lid += (lid_tgt - self._cur_lid) * _rate(dt, 0.18)

        # ── Saccades and organic wander ──────────────────────────────────────
        if t >= self._gaze_at:
            if live:
                reach = 0.75
                self._gaze_tgt = [
                    random.uniform(-1.0, 1.0) * reach,
                    random.uniform(-1.0, 1.0) * reach * 0.65,
                ]
                self._gaze_at = t + 0.6 + 1.5 * random.random()
            elif thinking:
                reach = 0.40
                self._gaze_tgt = [
                    random.uniform(-1.0, 1.0) * reach,
                    random.uniform(-1.0, 1.0) * reach * 0.4,
                ]
                self._gaze_at = t + 2.0 + 2.5 * random.random()
            else:
                reach = 0.50
                self._gaze_tgt = [
                    random.uniform(-1.0, 1.0) * reach,
                    random.uniform(-1.0, 1.0) * reach * 0.45,
                ]
                self._gaze_at = t + 1.4 + 2.6 * random.random()

        if self._glance is not None:
            gx, gy, until = self._glance
            if t < until:
                self._gaze_tgt = [gx, gy]
            else:
                self._glance = None

        wander_x = math.sin(t * 0.8) * 0.06
        wander_y = math.cos(t * 0.6) * 0.04
        for i, b in enumerate(self._gaze_bias):
            offset = wander_x if i == 0 else wander_y
            tgt = max(-1.0, min(1.0, self._gaze_tgt[i] + b + offset))
            self._gaze[i] += (tgt - self._gaze[i]) * _rate(dt, 0.09)

        # ── Blinking ────────────────────────────────────────────────────────
        if self._blink > 0.0:
            self._blink = max(0.0, self._blink - dt * 9.0)
        elif t >= self._blink_at:
            if asleep or muted:
                self._blink_at = t + 8.0
            else:
                self._blink = 1.0
                gap = 5.0 if thinking else 3.2
                self._blink_at = t + gap + 3.5 * random.random()

        # ── Pupil dilation / constriction ───────────────────────────────────
        if live:
            tgt_pupil = 0.88 + 0.42 * (self._amp_slow ** 0.7)
        elif muted or asleep:
            tgt_pupil = 0.72
        else:
            tgt_pupil = 0.95 + 0.08 * math.sin(self._breathe * 0.8)

        self._pupil_scale += (tgt_pupil - self._pupil_scale) * _rate(dt, 0.12)

    def paint(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        primary: QColor,
        accent: QColor,
        bg: QColor | None = None,
    ) -> None:
        """Render the holographic dark eye centered at (cx, cy)."""
        if bg is None:
            bg = QColor(0, 0, 0)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        amp = self._glow
        breath = 0.5 + 0.5 * math.sin(self._breathe)

        r_eye = max(10.0, r * 0.92)
        r_iris = r_eye * 0.54
        r_pupil = r_iris * 0.42 * self._pupil_scale

        g_range_x = r_eye * 0.36
        g_range_y = r_eye * 0.24
        iris_cx = cx + self._gaze[0] * g_range_x
        iris_cy = cy + self._gaze[1] * g_range_y

        vis = max(0.0, min(1.0, (1.0 - self._blink) * self._cur_lid))

        # ── 0. Back FX (Scanlines, Data Ring, Behind Eye) ───────────────────
        if self.fx:
            self._paint_back_fx(p, cx, cy, r_eye, primary, accent, bg, amp)

        # ── 1. Atmosphere / Outer Aura ──────────────────────────────────────
        aura_r = r_eye * (1.85 + 0.30 * amp + 0.08 * breath)
        aura_grad = QRadialGradient(cx, cy, aura_r)
        aura_alpha_core = int(22 + 75 * amp + 15 * breath)
        aura_alpha_mid = int(10 + 38 * amp + 6 * breath)
        aura_grad.setColorAt(0.00, _c(primary, aura_alpha_core))
        aura_grad.setColorAt(0.40, _c(primary, aura_alpha_mid))
        aura_grad.setColorAt(0.80, _c(primary, max(0, aura_alpha_mid // 3)))
        aura_grad.setColorAt(1.00, _c(primary, 0))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(aura_grad))
        p.drawEllipse(QRectF(cx - aura_r, cy - aura_r, aura_r * 2.0, aura_r * 2.0))

        # ── 2. Outer Eye Contour / Orbit Rings ──────────────────────────────
        orbit_pen = QPen(_c(primary, 45 + 50 * amp), 1.0)
        p.setPen(orbit_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - r_eye * 1.14, cy - r_eye * 1.14, r_eye * 2.28, r_eye * 2.28))

        tick_pen = QPen(_c(accent, 70 + 80 * amp), 1.2)
        p.setPen(tick_pen)
        for ang in (-45, 45, 135, 225):
            rad = math.radians(ang)
            p1x = cx + math.cos(rad) * (r_eye * 1.10)
            p1y = cy + math.sin(rad) * (r_eye * 1.10)
            p2x = cx + math.cos(rad) * (r_eye * 1.22)
            p2y = cy + math.sin(rad) * (r_eye * 1.22)
            p.drawLine(QPointF(p1x, p1y), QPointF(p2x, p2y))

        # ── 3. Eyeball Aperture Path (Eyeball Shape with Lids) ───────────────
        c_left = QPointF(cx - r_eye * 1.08, cy)
        c_right = QPointF(cx + r_eye * 1.08, cy)

        lid_h_up = r_eye * 0.95 * vis
        lid_h_dn = r_eye * 0.85 * vis

        eye_path = QPainterPath()
        eye_path.moveTo(c_left)
        eye_path.cubicTo(
            QPointF(cx - r_eye * 0.55, cy - lid_h_up * 1.15),
            QPointF(cx + r_eye * 0.55, cy - lid_h_up * 1.15),
            c_right,
        )
        eye_path.cubicTo(
            QPointF(cx + r_eye * 0.55, cy + lid_h_dn * 1.10),
            QPointF(cx - r_eye * 0.55, cy + lid_h_dn * 1.10),
            c_left,
        )
        eye_path.closeSubpath()

        if vis <= 0.04:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_c(primary, 130), 2.0))
            p.drawLine(c_left, c_right)
        else:
            self._paint_eye_interior(
                p, cx, cy, r_eye, r_iris, r_pupil, iris_cx, iris_cy,
                lid_h_up, eye_path, primary, accent, bg, amp, breath
            )

        # ── 10. Front FX (Orbiting 3D Wireframe Cubes) ───────────────────────
        if self.fx:
            self._paint_front_fx(p, cx, cy, r_eye, primary, accent, amp)

    def _paint_eye_interior(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r_eye: float,
        r_iris: float,
        r_pupil: float,
        iris_cx: float,
        iris_cy: float,
        lid_h_up: float,
        eye_path: QPainterPath,
        primary: QColor,
        accent: QColor,
        bg: QColor,
        amp: float,
        breath: float,
    ) -> None:
        # Clip to aperture
        p.save()
        p.setClipPath(eye_path)

        # ── 4. Sclera: Deep Dark, Nearly Pitch Black with Vignette ──────────
        sclera_grad = QRadialGradient(cx, cy, r_eye * 1.2)
        sclera_center = _blend(bg, primary, 24)
        sclera_edge = _blend(bg, primary, 6)
        sclera_grad.setColorAt(0.00, sclera_center)
        sclera_grad.setColorAt(0.70, sclera_edge)
        sclera_grad.setColorAt(1.00, bg)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(sclera_grad))
        p.drawPath(eye_path)

        # Subtle dark red/accent filaments
        vessel_pen = QPen(_c(accent, 18 + 25 * amp), 0.8)
        p.setPen(vessel_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for vx_dir in (-1.0, 1.0):
            p.drawLine(
                QPointF(cx + vx_dir * r_eye * 0.95, cy),
                QPointF(cx + vx_dir * (r_eye * 0.58), cy - r_eye * 0.12),
            )
            p.drawLine(
                QPointF(cx + vx_dir * r_eye * 0.90, cy + r_eye * 0.08),
                QPointF(cx + vx_dir * (r_eye * 0.55), cy + r_eye * 0.18),
            )

        # ── 5. Iris ─────────────────────────────────────────────────────────
        iris_rect = QRectF(iris_cx - r_iris, iris_cy - r_iris, r_iris * 2.0, r_iris * 2.0)
        iris_grad = QRadialGradient(iris_cx, iris_cy, r_iris)

        iris_center_col = _c(accent, min(255, int(185 + 70 * amp + 25 * breath)))
        iris_mid_col = _c(accent, int(110 + 60 * amp))
        iris_rim_col = _blend(bg, accent, 42)

        iris_grad.setColorAt(0.00, iris_center_col)
        iris_grad.setColorAt(0.35, iris_mid_col)
        iris_grad.setColorAt(0.78, _blend(bg, accent, 75))
        iris_grad.setColorAt(1.00, iris_rim_col)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(iris_grad))
        p.drawEllipse(iris_rect)

        # ── Radial Striations (Iris fibers using precomputed numpy) ─────────
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        step_deg = 3
        inner_r = r_pupil * 0.95
        outer_r = r_iris * 0.96

        for deg in range(0, 360, step_deg):
            mod = float(self._iris_rays[deg])
            rad = math.radians(deg)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)

            line_out = outer_r * min(1.0, 0.85 + 0.15 * mod)
            line_in = inner_r * max(0.9, min(1.3, mod))

            alpha = int(max(15, min(140, (40 + 55 * amp) * mod)))
            pen_col = _c(accent if mod > 1.0 else primary, alpha)
            p.setPen(QPen(pen_col, 0.8))

            p.drawLine(
                QPointF(iris_cx + cos_a * line_in, iris_cy + sin_a * line_in),
                QPointF(iris_cx + cos_a * line_out, iris_cy + sin_a * line_out),
            )
        p.restore()

        # Concentric Rings
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r_factor, a_fac in ((0.52, 50), (0.75, 40), (0.92, 70)):
            ring_r = r_iris * r_factor
            p.setPen(QPen(_c(accent, int(a_fac * (0.8 + 0.4 * amp))), 0.9))
            p.drawEllipse(
                QRectF(iris_cx - ring_r, iris_cy - ring_r, ring_r * 2.0, ring_r * 2.0)
            )

        limbal_pen = QPen(QColor(0, 0, 0, 220), 2.2)
        p.setPen(limbal_pen)
        p.drawEllipse(iris_rect)

        # ── 6. Pupil ────────────────────────────────────────────────────────
        pupil_rect = QRectF(
            iris_cx - r_pupil, iris_cy - r_pupil, r_pupil * 2.0, r_pupil * 2.0
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(2, 2, 4)))
        p.drawEllipse(pupil_rect)

        pupil_rim_pen = QPen(_c(accent, int(80 + 100 * amp)), 1.1)
        p.setPen(pupil_rim_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pupil_rect)

        # ── 7. Specular Highlights ──────────────────────────────────────────
        hl_cx = iris_cx - r_iris * 0.32
        hl_cy = iris_cy - r_iris * 0.35
        hl_rx = max(2.0, r_iris * 0.16)
        hl_ry = max(1.5, r_iris * 0.11)

        hl_grad = QRadialGradient(hl_cx, hl_cy, hl_rx)
        hl_grad.setColorAt(0.00, QColor(255, 255, 255, 245))
        hl_grad.setColorAt(0.45, QColor(255, 255, 255, 175))
        hl_grad.setColorAt(1.00, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hl_grad))
        p.drawEllipse(QRectF(hl_cx - hl_rx, hl_cy - hl_ry, hl_rx * 2.0, hl_ry * 2.0))

        sec_cx = iris_cx + r_iris * 0.35
        sec_cy = iris_cy + r_iris * 0.32
        sec_r = max(1.0, r_iris * 0.08)
        p.setBrush(QBrush(QColor(255, 255, 255, int(60 + 50 * amp))))
        p.drawEllipse(QPointF(sec_cx, sec_cy), sec_r, sec_r)

        # ── 8. Eyelid Shadow ────────────────────────────────────────────────
        shadow_h = r_eye * 0.45
        shadow_rect = QRectF(cx - r_eye * 1.1, cy - lid_h_up, r_eye * 2.2, shadow_h)
        shadow_grad = QRadialGradient(cx, cy - lid_h_up, shadow_h * 1.5)
        shadow_grad.setColorAt(0.00, QColor(0, 0, 0, 195))
        shadow_grad.setColorAt(0.65, QColor(0, 0, 0, 110))
        shadow_grad.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(shadow_grad))
        p.drawRect(shadow_rect)

        p.restore()

        # ── 9. Eyelid Rim Lines ─────────────────────────────────────────────
        lid_pen = QPen(_c(primary, int(150 + 95 * amp)), 1.6)
        p.setPen(lid_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(eye_path)

        crease_pen = QPen(_c(accent, int(60 + 60 * amp)), 1.0)
        p.setPen(crease_pen)
        p.drawPath(eye_path)


    # ── Tech FX Layer Implementations ────────────────────────────────────────

    def _paint_back_fx(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r_eye: float,
        primary: QColor,
        accent: QColor,
        bg: QColor,
        amp: float,
    ) -> None:
        """Render subtle background tech scanlines and the rotating data ring behind the eye."""
        energy = self._fx_energy

        # 1. Subtle horizontal scan lines across background
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        scan_span = r_eye * 2.6
        scan_alpha = int(max(6, min(45, (10 + 25 * energy) * (0.1 if self._is_muted else 1.0))))
        scan_pen = QPen(_c(primary, scan_alpha), 1.0)
        p.setPen(scan_pen)

        # 7 scan lines moving downwards
        n_lines = 7
        for i in range(n_lines):
            line_frac = (self._scan_phase + i / n_lines) % 1.0
            ly = cy - scan_span * 0.5 + line_frac * scan_span
            half_w = scan_span * 0.55 * math.sin(line_frac * math.pi)
            p.drawLine(QPointF(cx - half_w, ly), QPointF(cx + half_w, ly))

        # 2. Tech Data Ring (ticking dashes and dots)
        ring_r = r_eye * 1.35
        ring_alpha = int(max(15, min(170, (40 + 110 * energy) * (0.2 if self._is_muted else 1.0))))
        accent_dot_pen = QPen(_c(accent, int(ring_alpha * 1.2)), 2.0)

        # Outer guide circle faint
        p.setPen(QPen(_c(primary, int(ring_alpha * 0.35)), 0.8))
        p.drawEllipse(QRectF(cx - ring_r, cy - ring_r, ring_r * 2.0, ring_r * 2.0))

        # Segments along ring
        n_segs = 48
        ang_base = self._data_ring_angle
        for s in range(n_segs):
            theta = ang_base + s * (2.0 * math.pi / n_segs)
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)

            if s % 6 == 0:
                # Cardinal / major dash
                p.setPen(QPen(_c(accent, int(ring_alpha * 1.1)), 1.4))
                p.drawLine(
                    QPointF(cx + cos_t * (ring_r - 5), cy + sin_t * (ring_r - 5)),
                    QPointF(cx + cos_t * (ring_r + 5), cy + sin_t * (ring_r + 5)),
                )
            elif s % 2 == 0:
                # Small tick
                p.setPen(QPen(_c(primary, int(ring_alpha * 0.7)), 0.9))
                p.drawLine(
                    QPointF(cx + cos_t * (ring_r - 2), cy + sin_t * (ring_r - 2)),
                    QPointF(cx + cos_t * (ring_r + 2), cy + sin_t * (ring_r + 2)),
                )
            elif s % 4 == 1:
                # Small data point
                p.setPen(accent_dot_pen)
                p.drawPoint(QPointF(cx + cos_t * ring_r, cy + sin_t * ring_r))

        p.restore()


    def _paint_front_fx(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r_eye: float,
        primary: QColor,
        accent: QColor,
        amp: float,
    ) -> None:
        """Render 6 3D wireframe cubes orbiting the eye in inclined orbits."""
        energy = self._fx_energy
        base_orbit_r = r_eye * 1.55 * self._orbit_dist_fac
        cube_size = max(3.0, r_eye * 0.08)

        base_alpha = int(max(20, min(240, (50 + 160 * energy) * (0.15 if self._is_muted else 1.0))))
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)

        cam_d = 4.0

        for i in range(6):
            theta = self._cube_angles[i]
            inc_x, inc_y = self._cube_incls[i]

            ox = math.cos(theta) * base_orbit_r
            oy = math.sin(theta) * base_orbit_r
            oz = 0.0

            # Rotate orbit around X and Y
            cx_cos, cx_sin = math.cos(inc_x), math.sin(inc_x)
            oy1 = oy * cx_cos - oz * cx_sin
            oz1 = oy * cx_sin + oz * cx_cos

            cy_cos, cy_sin = math.cos(inc_y), math.sin(inc_y)
            orbit_x = ox * cy_cos + oz1 * cy_sin
            orbit_y = oy1
            orbit_z = -ox * cy_sin + oz1 * cy_cos

            # Cube spin around its own axes
            spin = self._cube_spin[i]
            s1_c, s1_s = math.cos(spin), math.sin(spin)
            s2_c, s2_s = math.cos(spin * 0.7), math.sin(spin * 0.7)

            rot = np.array([
                [s1_c, 0.0, s1_s],
                [s1_s * s2_s, s2_c, -s1_c * s2_s],
                [-s1_s * s2_c, s2_s, s1_c * s2_c],
            ], dtype=np.float32)

            c_verts = (_CUBE_VERTS * cube_size) @ rot.T
            c_verts[:, 0] += orbit_x
            c_verts[:, 1] += orbit_y
            c_verts[:, 2] += orbit_z

            # Perspective projection
            z_factor = c_verts[:, 2] / base_orbit_r
            w = cam_d - z_factor
            np.maximum(w, 0.5, out=w)
            proj_scale = cam_d / w

            px = cx + c_verts[:, 0] * proj_scale
            py = cy + c_verts[:, 1] * proj_scale

            center_z = orbit_z / base_orbit_r
            depth_fade = max(0.25, min(1.2, 0.75 + 0.45 * center_z))
            cube_alpha = int(max(15, min(255, base_alpha * depth_fade)))

            cube_col = accent if (i % 2 == 1 or energy > 0.7) else primary
            pen = QPen(_c(cube_col, cube_alpha), 1.1 if depth_fade > 0.7 else 0.8)
            p.setPen(pen)

            for v1, v2 in _CUBE_EDGES:
                p.drawLine(QPointF(px[v1], py[v1]), QPointF(px[v2], py[v2]))

            p.setPen(QPen(_c(accent, int(cube_alpha * 0.9)), 2.0))
            p.drawPoint(QPointF(cx + orbit_x * (cam_d / max(0.5, cam_d - center_z)),
                                cy + orbit_y * (cam_d / max(0.5, cam_d - center_z))))

        p.restore()

