"""
HoloCrystal — Modelo visual Shield Ruby 2.5D multi-estado para o HUD VOID OS.

Assinaturas visuais distintas por etapa:
    - IDLE:
        Rotação orbital contínua em 3 camadas contra-rotativas (bisel externo
        segmentado + satélites, arcos médios assimétricos e giroscópio interno),
        respiração orgânica e paralaxe 2.5D serena.
    - LISTENING (Escuta Ativa):
        Ondas acústicas convergentes (de fora para dentro em direção ao núcleo),
        colchetes equatoriais de captação enquadrando os 2 beacons cardeais e
        resposta imediata ao nível do microfone.
    - THINKING / PROCESSING (Processamento Neural):
        Modo scanner de alta velocidade: contra-rotação acelerada nos 3 anéis,
        beacons rubi destravados orbitando 360° com rastros luminosos (comet trails),
        varredura vertical de luz interna confinada nas facetas e pulso nas arestas "X".
    - SPEAKING (Voz Ativa do ULTRON):
        Envelope perceptual de alto ganho (amp + visemas v_open/v_level + portadora
        silábica), ondas sônicas expansivas (do núcleo para fora), ressonador
        harmônico radial no anel interno, articulação elástica das facetas/losango
        interno e núcleo rubi incandescente (100% sem vazar névoa no #000000 externo).

Tecnologia:
    PyQt6 + QPainter vetorial puro, zero QTimer extra, zero blur NumPy por frame.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

SPAN: float = 1.88

_TRANSPARENT_BLACK = QColor(0, 0, 0, 0)


def _rate(dt: float, tau: float) -> float:
    """Suavização exponencial independente da taxa de quadros."""
    if dt <= 0.0:
        return 0.0
    return 1.0 - math.exp(-dt / max(tau, 1e-6))


def _clamp(val: float, lo: float, hi: float) -> float:
    return lo if val < lo else (hi if val > hi else val)


def _tone(
    base: QColor,
    lum: float,
    *,
    crimson_blue_bias: float = 0.22,
    white_lift: float = 0.0,
    alpha: float = 255.0,
    muted: bool = False,
) -> QColor:
    """Deriva um tom de faceta/anel a partir da cor primária preservando a riqueza rubi."""
    if muted:
        g = int(
            _clamp(
                (base.red() * 0.30 + base.green() * 0.45 + base.blue() * 0.25) * lum
                + 255.0 * white_lift * 0.35,
                0.0,
                255.0,
            )
        )
        return QColor(
            g,
            int(_clamp(g * 1.04, 0, 255)),
            int(_clamp(g * 1.10, 0, 255)),
            int(_clamp(alpha, 0.0, 255.0)),
        )

    br, bg, bb = base.red(), base.green(), base.blue()
    is_ruby = br >= 165 and bg <= 75 and bb <= 110
    if is_ruby:
        r_v = 255.0 * lum + (255.0 - 255.0 * lum) * white_lift
        g_v = (16.0 * lum) + 235.0 * white_lift * 0.34
        b_v = (255.0 * lum * crimson_blue_bias) + 245.0 * white_lift * 0.44
    else:
        r_v = br * lum + (255.0 - br * lum) * white_lift
        g_v = bg * lum + (255.0 - bg * lum) * white_lift
        b_v = bb * lum + (255.0 - bb * lum) * white_lift

    return QColor(
        int(_clamp(r_v, 0.0, 255.0)),
        int(_clamp(g_v, 0.0, 255.0)),
        int(_clamp(b_v, 0.0, 255.0)),
        int(_clamp(alpha, 0.0, 255.0)),
    )


class HoloCrystal:
    """Visualizador Shield Ruby 2.5D com coreografias distintas para LISTENING, THINKING e SPEAKING."""

    SPAN: float = SPAN

    # Anel externo segmentado (start_deg, span_deg) — garante movimento visível no bisel externo
    _OUTER_BEZEL_ARCS: tuple[tuple[float, float], ...] = (
        (18.0, 54.0),
        (108.0, 54.0),
        (198.0, 54.0),
        (288.0, 54.0),
    )

    # Anel médio de telemetria (start_deg, span_deg, camada_rotacao)
    _TELEMETRY_ARCS: tuple[tuple[float, float, int], ...] = (
        (100.0, 46.0, 1),
        (158.0, 18.0, -1),
        (196.0, 48.0, 1),
        (264.0, 10.0, -1),
        (304.0, 50.0, 1),
        (4.0, 30.0, -1),
        (48.0, 19.0, 1),
    )

    # Anel interno giroscópico (start_deg, span_deg)
    _INNER_GYRO_ARCS: tuple[tuple[float, float], ...] = (
        (15.0, 74.0),
        (135.0, 74.0),
        (255.0, 74.0),
    )

    def __init__(self) -> None:
        self._t: float = 0.0
        self._amp: float = 0.0
        self._amp_fast: float = 0.0
        self._amp_disp: float = 0.0
        self._voice: float = 0.0      # envelope perceptual potente durante SPEAKING
        self._mic_pulse: float = 0.0  # envelope reativo durante LISTENING
        self._v_open: float = 0.0     # abertura fonêmica (visema) quando disponível

        self._speaking: bool = False
        self._muted: bool = False
        self._state: str = ""

        # Pesos interpolados de estado (0..1) para transições suaves e assinaturas únicas
        self._w_listen: float = 0.0
        self._w_think: float = 0.0
        self._w_speak: float = 0.0

        self._energy: float = 0.40
        self._breathe: float = 0.0

        # Fases orbitais independentes (nunca parecem círculos estáticos)
        self._outer_phase: float = 0.0
        self._arc_phase_a: float = 0.0
        self._arc_phase_b: float = 0.0
        self._inner_phase: float = 0.0
        self._beacon_orbit: float = 0.0
        self._sway_phase: float = 0.0
        self._scan_phase: float = 0.0

        # Ondas direcionais: convergentes (LISTENING) e expansivas (SPEAKING)
        self._inward_waves: list[float] = [0.0, 0.50]
        self._outward_waves: list[float] = [0.0, 0.33, 0.66]

        self._glance_x: float = 0.0
        self._glance_y: float = 0.0
        self._glance_tgt: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def prewarm_bloom(self) -> None:
        """Mantido por compatibilidade; o pipeline vetorial 2.5D dispensa blur offscreen."""
        return

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Inclina suavemente a paralaxe 2.5D do cristal na direção indicada."""
        self._glance_tgt = (
            _clamp(float(dx), -1.5, 1.5),
            _clamp(float(dy), -1.5, 1.5),
            self._t + float(hold),
        )

    def step(
        self,
        dt: float,
        amp: float,
        speaking: bool = False,
        muted: bool = False,
        state: str = "",
        **kw,
    ) -> None:
        """Avança a cinemática multi-estado, envelopes de voz e fases orbitais."""
        dt = _clamp(float(dt), 0.0, 0.1)
        self._t += dt
        self._speaking = bool(speaking)
        self._muted = bool(muted)
        self._state = str(state or "").upper()

        v_level = kw.get("v_level")
        v_open = kw.get("v_open")

        raw_amp = _clamp(float(amp), 0.0, 1.0)
        if v_level is not None:
            raw_amp = max(raw_amp, _clamp(float(v_level), 0.0, 1.0))

        # Ataque ultra-rápido (22 ms) para sílabas nítidas; queda elástica (115 ms)
        if raw_amp > self._amp_fast:
            self._amp_fast += (raw_amp - self._amp_fast) * _rate(dt, 0.022)
        else:
            self._amp_fast += (raw_amp - self._amp_fast) * _rate(dt, 0.115)

        self._amp_disp += (self._amp_fast - self._amp_disp) * _rate(dt, 0.055)
        self._amp = _clamp(self._amp_disp, 0.0, 1.0)

        # Visema de abertura silábica (ou derivado da energia vocal)
        tgt_open = _clamp(float(v_open), 0.0, 1.0) if v_open is not None else min(1.0, self._amp * 1.9)
        self._v_open += (tgt_open - self._v_open) * _rate(dt, 0.035)

        # Pesos exclusivos de cada etapa ativa
        is_think = (not self._muted) and (not self._speaking) and self._state in ("THINKING", "PROCESSING")
        is_speak = (not self._muted) and self._speaking
        is_listen = (not self._muted) and (not is_speak) and (not is_think) and self._state == "LISTENING"

        r_state = _rate(dt, 0.13)
        self._w_listen += ((1.0 if is_listen else 0.0) - self._w_listen) * r_state
        self._w_think += ((1.0 if is_think else 0.0) - self._w_think) * r_state
        self._w_speak += ((1.0 if is_speak else 0.0) - self._w_speak) * r_state

        # Curva perceptual de voz para SPEAKING: amplifica sinais típicos (0.10..0.35)
        # e mantém modulação silábica orgânica mesmo em trechos suaves de TTS.
        perceptual = min(1.0, (self._amp * 2.45) ** 0.68)
        if is_speak:
            syllabic_floor = (
                0.24
                + 0.22 * abs(math.sin(self._t * 8.4))
                * (0.45 + 0.55 * (math.sin(self._t * 3.3 + 0.7) ** 2))
            )
            tgt_voice = max(perceptual, self._v_open * 0.85, syllabic_floor)
        else:
            tgt_voice = 0.0
        self._voice += (tgt_voice - self._voice) * _rate(dt, 0.038 if is_speak else 0.14)

        # Envelope reativo de microfone para LISTENING
        tgt_mic = min(1.0, (self._amp * 2.2) ** 0.72) if is_listen else 0.0
        self._mic_pulse += (tgt_mic - self._mic_pulse) * _rate(dt, 0.045 if is_listen else 0.16)

        self._breathe += dt * (1.55 + 0.85 * self._w_listen + 1.4 * self._w_speak)

        # Velocidades orbitais claramente perceptíveis e únicas para cada estado
        if self._muted:
            tgt_energy = 0.12
            v_outer = 6.0
            v_mid_a = 9.0
            v_mid_b = -7.0
            v_inner = -10.0
            sway_rate = 0.30
        else:
            # Base IDLE (movimento vivo e contínuo) + deltas por etapa
            v_outer = (
                20.0
                + 14.0 * self._w_listen
                + 88.0 * self._w_think
                + (32.0 + 52.0 * self._voice) * self._w_speak
            )
            v_mid_a = (
                26.0
                + 16.0 * self._w_listen
                + 122.0 * self._w_think
                + (38.0 + 70.0 * self._voice) * self._w_speak
            )
            v_mid_b = -(
                21.0
                + 14.0 * self._w_listen
                + 104.0 * self._w_think
                + (30.0 + 58.0 * self._voice) * self._w_speak
            )
            v_inner = -(
                32.0
                + 18.0 * self._w_listen
                + 142.0 * self._w_think
                + (45.0 + 75.0 * self._voice) * self._w_speak
            )
            sway_rate = (
                0.72
                + 0.30 * self._w_listen
                + 1.15 * self._w_think
                + (0.95 + 1.10 * self._voice) * self._w_speak
            )
            tgt_energy = (
                0.38
                + 0.12 * math.sin(self._breathe)
                + (0.18 + 0.35 * self._mic_pulse) * self._w_listen
                + (0.48 + 0.14 * math.sin(self._t * 6.5)) * self._w_think
                + (0.34 + 0.62 * self._voice) * self._w_speak
            )

        self._energy += (tgt_energy - self._energy) * _rate(dt, 0.18)
        self._outer_phase = (self._outer_phase + v_outer * dt) % 360.0
        self._arc_phase_a = (self._arc_phase_a + v_mid_a * dt) % 360.0
        self._arc_phase_b = (self._arc_phase_b + v_mid_b * dt) % 360.0
        self._inner_phase = (self._inner_phase + v_inner * dt) % 360.0
        self._sway_phase += sway_rate * dt

        # Em THINKING os beacons destravam e orbitam velozmente; nos demais estados reancoram suavemente no equador
        if self._w_think > 0.05:
            self._beacon_orbit = (self._beacon_orbit + (55.0 + 145.0 * self._w_think) * dt) % 360.0
        elif abs(self._beacon_orbit) > 0.2:
            # Retorna pelo caminho angular mais curto para 0°
            rem = ((self._beacon_orbit + 180.0) % 360.0) - 180.0
            self._beacon_orbit = (rem * (1.0 - _rate(dt, 0.18))) % 360.0
            if abs(((self._beacon_orbit + 180.0) % 360.0) - 180.0) < 0.3:
                self._beacon_orbit = 0.0

        # Scanner vertical interno para THINKING
        self._scan_phase = (self._scan_phase + dt * (0.45 + 1.35 * self._w_think)) % 1.0

        # Ondas convergentes (LISTENING: fora -> dentro)
        in_speed = 0.42 + 0.55 * self._mic_pulse
        for i in range(len(self._inward_waves)):
            self._inward_waves[i] = (self._inward_waves[i] + dt * in_speed) % 1.0

        # Ondas sônicas expansivas (SPEAKING: núcleo -> fora)
        out_speed = 0.72 + 1.05 * self._voice
        for i in range(len(self._outward_waves)):
            self._outward_waves[i] = (self._outward_waves[i] + dt * out_speed) % 1.0

        # Glance / olhar direcional
        gx_tgt, gy_tgt, g_until = self._glance_tgt
        if self._t > g_until:
            gx_tgt, gy_tgt = 0.0, 0.0
        rg = _rate(dt, 0.22)
        self._glance_x += (gx_tgt - self._glance_x) * rg
        self._glance_y += (gy_tgt - self._glance_y) * rg

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
        """Renderiza os anéis orbitais multi-estado e o cristal Shield Ruby 2.5D."""
        if r <= 4.0 or not painter.isActive():
            return

        p = painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        base = QColor(primary)
        muted = self._muted
        energy = _clamp(self._energy, 0.0, 1.5)
        voice = _clamp(self._voice, 0.0, 1.0)
        mic = _clamp(self._mic_pulse, 0.0, 1.0)
        wl = _clamp(self._w_listen, 0.0, 1.0)
        wt = _clamp(self._w_think, 0.0, 1.0)
        ws = _clamp(self._w_speak, 0.0, 1.0)

        R = r * 0.90

        # ── 1. Sistema Orbital de 3 Anéis Vivos + Ondas de Estado ────────────────
        self._paint_hud_rings(p, cx, cy, R, base, energy, voice, mic, wl, wt, ws, muted)

        # ── 2. Cinemática 2.5D e Articulação Física do Cristal ───────────────────
        sway = math.sin(self._sway_phase) * (0.024 + 0.014 * wt + 0.012 * ws) + self._glance_x * 0.075
        tilt_y = math.cos(self._sway_phase * 0.78) * 0.009 + self._glance_y * 0.055

        # Em SPEAKING o cristal articula visivelmente a largura dos ombros e a altura das pontas
        speak_w_expand = 1.0 + (0.088 * voice + 0.022 * self._v_open) * ws
        speak_h_expand = 1.0 + (0.052 * voice + 0.018 * self._v_open) * ws
        listen_breathe = 0.012 * math.sin(self._breathe) * (1.0 + 0.5 * wl) + 0.024 * mic * wl

        sx = R * (1.0 + listen_breathe) * speak_w_expand
        sy = R * (1.0 + listen_breathe * 0.8) * speak_h_expand

        def pt(nx: float, ny: float, depth_factor: float = 0.0) -> QPointF:
            px_off = sway * depth_factor
            py_off = tilt_y * depth_factor * 0.65
            return QPointF(cx + (nx + px_off) * sx, cy + (ny + py_off) * sy)

        # Silhueta externa fiel à referência + crista vertical central única (sem cone/reflexo central)
        p_top = pt(0.000, -1.018, 0.30)
        p_sl = pt(-0.441, -0.295, 0.22)
        p_sr = pt(+0.441, -0.295, 0.22)
        p_kl = pt(-0.286, +0.454, 0.20)
        p_kr = pt(+0.286, +0.454, 0.20)
        p_bot = pt(0.000, +1.042, 0.28)

        sh_y = p_sl.y()
        p_sr = QPointF(p_sr.x(), sh_y)
        p_sh_mid = QPointF(pt(0.000, -0.295, 0.72).x(), sh_y)
        p_core = pt(0.000, +0.050, 0.72)

        hull_poly = QPolygonF([p_top, p_sr, p_kr, p_bot, p_kl, p_sl])
        hull_path = QPainterPath()
        hull_path.addPolygon(hull_poly)
        hull_path.closeSubpath()

        light_shift = _clamp(sway * 3.2, -0.15, 0.15)
        active_drive = voice * ws + mic * wl * 0.65

        def think_shimmer(idx: int) -> float:
            if wt <= 0.01:
                return 0.0
            return wt * 0.11 * (0.5 + 0.5 * math.sin(self._t * 6.8 + idx * 0.95))

        # ── 3. Oclusão #000000 + Preenchimento Limpo das Facetas de Vidro Rubi ───
        # Oclui os anéis que passam atrás do cristal para não criarem arcos fantasma na coroa
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 255)))
        p.drawPolygon(hull_poly)

        crown_e = 0.03 * energy + 0.07 * active_drive
        body_e = 0.05 * energy + 0.14 * active_drive

        # 3.1 Coroa Superior Esquerda (T -> SL -> Meio da Cintura)
        g_cl = QLinearGradient(p_top, p_sl)
        g_cl.setColorAt(0.0, _tone(base, 0.31 - light_shift * 0.25 + crown_e + think_shimmer(0) * 0.45, alpha=245, muted=muted))
        g_cl.setColorAt(1.0, _tone(base, 0.18 - light_shift * 0.20 + crown_e * 0.6, alpha=245, muted=muted))
        p.setBrush(QBrush(g_cl))
        p.drawPolygon(QPolygonF([p_top, p_sl, p_sh_mid]))

        # 3.2 Coroa Superior Direita (T -> Meio da Cintura -> SR)
        g_cr = QLinearGradient(p_top, p_sr)
        g_cr.setColorAt(0.0, _tone(base, 0.39 + light_shift * 0.25 + crown_e + think_shimmer(1) * 0.45, alpha=245, muted=muted))
        g_cr.setColorAt(0.65, _tone(base, 0.30 + light_shift * 0.20 + crown_e * 0.8, alpha=245, muted=muted))
        g_cr.setColorAt(1.0, _tone(base, 0.22 + light_shift * 0.15 + crown_e * 0.5, alpha=245, muted=muted))
        p.setBrush(QBrush(g_cr))
        p.drawPolygon(QPolygonF([p_top, p_sh_mid, p_sr]))

        # 3.3 Corpo Superior Esquerdo (SL -> Meio da Cintura -> Core)
        g_bul = QLinearGradient(QPointF(p_sl.x() * 0.5 + p_sh_mid.x() * 0.5, sh_y), p_core)
        g_bul.setColorAt(0.0, _tone(base, 0.24 - light_shift * 0.18 + body_e * 0.6 + think_shimmer(2) * 0.5, alpha=245, muted=muted))
        g_bul.setColorAt(1.0, _tone(base, 0.48 + body_e, white_lift=0.04 * voice * ws, alpha=245, muted=muted))
        p.setBrush(QBrush(g_bul))
        p.drawPolygon(QPolygonF([p_sl, p_sh_mid, p_core]))

        # 3.4 Corpo Superior Direito (Meio da Cintura -> SR -> Core)
        g_bur = QLinearGradient(QPointF(p_sr.x() * 0.5 + p_sh_mid.x() * 0.5, sh_y), p_core)
        g_bur.setColorAt(0.0, _tone(base, 0.29 + light_shift * 0.18 + body_e * 0.6 + think_shimmer(3) * 0.5, alpha=245, muted=muted))
        g_bur.setColorAt(1.0, _tone(base, 0.52 + body_e, white_lift=0.05 * voice * ws, alpha=245, muted=muted))
        p.setBrush(QBrush(g_bur))
        p.drawPolygon(QPolygonF([p_sh_mid, p_sr, p_core]))

        # 3.5 Asa Média Esquerda (SL -> Core -> KL)
        g_ml = QLinearGradient(p_core, QPointF((p_sl.x() + p_kl.x()) * 0.5, (p_sl.y() + p_kl.y()) * 0.5))
        g_ml.setColorAt(0.0, _tone(base, 0.52 - light_shift * 0.25 + body_e + think_shimmer(4) * 0.6, alpha=245, muted=muted))
        g_ml.setColorAt(1.0, _tone(base, 0.25 - light_shift * 0.20 + body_e * 0.4, alpha=245, muted=muted))
        p.setBrush(QBrush(g_ml))
        p.drawPolygon(QPolygonF([p_sl, p_core, p_kl]))

        # 3.6 Asa Média Direita (SR -> KR -> Core)
        g_mr = QLinearGradient(p_core, QPointF((p_sr.x() + p_kr.x()) * 0.5, (p_sr.y() + p_kr.y()) * 0.5))
        g_mr.setColorAt(0.0, _tone(base, 0.55 + light_shift * 0.25 + body_e + think_shimmer(5) * 0.6, alpha=245, muted=muted))
        g_mr.setColorAt(1.0, _tone(base, 0.29 + light_shift * 0.25 + body_e * 0.5, alpha=245, muted=muted))
        p.setBrush(QBrush(g_mr))
        p.drawPolygon(QPolygonF([p_sr, p_kr, p_core]))

        # 3.7 Pavilhão Inferior Esquerdo (KL -> Core -> B)
        g_ll = QLinearGradient(p_core, p_bot)
        g_ll.setColorAt(0.0, _tone(base, 0.48 + body_e + think_shimmer(6) * 0.6, alpha=245, muted=muted))
        g_ll.setColorAt(0.55, _tone(base, 0.34 + body_e * 0.6, alpha=245, muted=muted))
        g_ll.setColorAt(1.0, _tone(base, 0.19 + body_e * 0.3, alpha=245, muted=muted))
        p.setBrush(QBrush(g_ll))
        p.drawPolygon(QPolygonF([p_kl, p_core, p_bot]))

        # 3.8 Pavilhão Inferior Direito (Core -> KR -> B)
        g_lr = QLinearGradient(p_core, p_bot)
        g_lr.setColorAt(0.0, _tone(base, 0.41 + body_e * 0.9 + think_shimmer(7) * 0.6, alpha=245, muted=muted))
        g_lr.setColorAt(0.55, _tone(base, 0.27 + body_e * 0.5, alpha=245, muted=muted))
        g_lr.setColorAt(1.0, _tone(base, 0.15 + body_e * 0.25, alpha=245, muted=muted))
        p.setBrush(QBrush(g_lr))
        p.drawPolygon(QPolygonF([p_core, p_kr, p_bot]))

        # 3.9 Lapidação: contraste entre facetas + diferença sutil de tom esquerda/direita
        p.setPen(Qt.PenStyle.NoPen)
        for poly, shade in (
            ((p_top, p_sl, p_sh_mid), 52),
            ((p_sl, p_sh_mid, p_core), 44),
            ((p_sl, p_core, p_kl), 22),
            ((p_kl, p_core, p_bot), 46),
        ):
            p.setBrush(QColor(0, 0, 0, shade))
            p.drawPolygon(QPolygonF(list(poly)))
        for poly, lift in (
            ((p_top, p_sh_mid, p_sr), 20),
            ((p_sh_mid, p_sr, p_core), 10),
            ((p_sr, p_kr, p_core), 24),
            ((p_core, p_kr, p_bot), 8),
        ):
            p.setBrush(_tone(base, 0.95, white_lift=0.10, alpha=lift, muted=muted))
            p.drawPolygon(QPolygonF(list(poly)))

        # ── 4. Interior Recortado (Pequeno Brilho no Ápice + Luz Interna Sutil) ──
        p.save()
        p.setClipPath(hull_path)

        # Pequeno brilho localizado apenas no ápice superior
        apex_glow_r = R * (0.095 + 0.025 * active_drive)
        apex_glow = QRadialGradient(p_top, apex_glow_r)
        apex_glow.setColorAt(0.0, _tone(base, 0.95, white_lift=0.18, alpha=105 + 40 * active_drive, muted=muted))
        apex_glow.setColorAt(0.45, _tone(base, 0.70, white_lift=0.03, alpha=32 + 18 * active_drive, muted=muted))
        apex_glow.setColorAt(1.0, _TRANSPARENT_BLACK)
        p.setBrush(QBrush(apex_glow))
        p.drawEllipse(QRectF(p_top.x() - apex_glow_r, p_top.y() - apex_glow_r, apex_glow_r * 2.0, apex_glow_r * 2.0))

        # Luz radial sutil centrada no núcleo (sem losango/cone de reflexo invadindo o meio)
        glow_r = R * (0.26 + 0.15 * voice * ws + 0.06 * mic * wl + 0.02 * energy)
        inner_glow = QRadialGradient(p_core, glow_r)
        g_a0 = 82 + 28 * energy + 92 * voice * ws + 34 * mic * wl
        g_lift = 0.12 + 0.22 * voice * ws
        inner_glow.setColorAt(0.00, _tone(base, 0.98, white_lift=g_lift, alpha=min(235.0, g_a0), muted=muted))
        inner_glow.setColorAt(0.32, _tone(base, 0.86, white_lift=g_lift * 0.30, alpha=g_a0 * 0.45, muted=muted))
        inner_glow.setColorAt(0.68, _tone(base, 0.64, white_lift=0.0, alpha=g_a0 * 0.14, muted=muted))
        inner_glow.setColorAt(1.00, _TRANSPARENT_BLACK)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(inner_glow))
        p.drawEllipse(QRectF(p_core.x() - glow_r, p_core.y() - glow_r, glow_r * 2.0, glow_r * 2.0))

        # ── 4b. Cristal do Núcleo 3D (Bipirâmide Octaédrica com Paralaxe e Profundidade) ──
        # Levitação suave viva independente (sensação de núcleo vivo suspenso em gravidade zero)
        inner_float_y = 0.008 * math.sin(self._t * 2.2) + 0.004 * math.cos(self._t * 1.6)
        inner_pulse = 1.0 + 0.035 * math.sin(self._t * 3.1) + 0.14 * voice * ws + 0.06 * mic * wl

        # Dimensões imponentes do cristal interno (permanece estritamente abaixo da cintura sh_y = -0.295)
        # Alongado na parte inferior acompanhando a espinha central, com presença volumétrica real
        w_in = 0.190 * inner_pulse
        h_top_in = 0.230 * inner_pulse
        h_bot_in = 0.460 * inner_pulse
        core_ny = 0.058 + inner_float_y

        # Vértices 2.5D com profundidade de paralaxe volumétrica:
        # d_front projeta-se à frente (depth=1.15), d_back fica no fundo (depth=0.20),
        # fazendo o cristal interno angular e rotacionar realisticamente em 3D conforme sway e glance!
        d_top = pt(0.000, core_ny - h_top_in, 0.68)
        d_bot = pt(0.000, core_ny + h_bot_in, 0.68)
        d_l = pt(-w_in, core_ny, 0.52)
        d_r = pt(+w_in, core_ny, 0.52)
        d_front = pt(0.000, core_ny, 1.15)
        d_back = pt(0.000, core_ny, 0.20)

        # Iluminação dinâmica 3D por faceta (reage à inclinação angular sway, glance e refração interna)
        sway_n = _clamp(sway * 4.5, -0.6, 0.6)
        lum_l = _clamp(0.48 - sway_n * 0.42, 0.18, 0.88)
        lum_r = _clamp(0.48 + sway_n * 0.42, 0.18, 0.88)
        # Brilho cáustico interno refrativo (o cristal "respira" e refrata a luz em movimento contínuo)
        shimmer_in = 0.08 * math.sin(self._t * 3.4 + sway * 6.0)
        base_a = 100 + 28 * energy + 75 * voice * ws + 26 * mic * wl

        # 1) Fundo refrativo profundo (massa volumétrica interna do cristal)
        back_grad = QLinearGradient(d_top, d_bot)
        back_grad.setColorAt(0.0, _tone(base, 0.78, white_lift=0.03, alpha=base_a * 0.42, muted=muted))
        back_grad.setColorAt(0.4, _tone(base, 0.95, white_lift=0.10 + shimmer_in, alpha=base_a * 0.72, muted=muted))
        back_grad.setColorAt(1.0, _tone(base, 0.70, white_lift=0.00, alpha=base_a * 0.32, muted=muted))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(back_grad))
        p.drawPolygon(QPolygonF([d_top, d_r, d_bot, d_l]))

        # 2) Facetas frontais 3D (4 triângulos com sombreamento volumétrico e refração)
        # Faceta Superior Esquerda
        g_tl = QLinearGradient(d_front, QPointF(d_l.x() * 0.7 + d_top.x() * 0.3, d_l.y() * 0.7 + d_top.y() * 0.3))
        g_tl.setColorAt(0.0, _tone(base, 1.00, white_lift=0.18 * lum_l + 0.12 * voice * ws + shimmer_in, alpha=min(240.0, base_a * (0.85 + 0.35 * lum_l)), muted=muted))
        g_tl.setColorAt(1.0, _tone(base, 0.80, white_lift=0.02, alpha=base_a * 0.32 * lum_l, muted=muted))
        p.setBrush(QBrush(g_tl))
        p.drawPolygon(QPolygonF([d_top, d_l, d_front]))

        # Faceta Superior Direita
        g_tr = QLinearGradient(d_front, QPointF(d_r.x() * 0.7 + d_top.x() * 0.3, d_r.y() * 0.7 + d_top.y() * 0.3))
        g_tr.setColorAt(0.0, _tone(base, 1.00, white_lift=0.18 * lum_r + 0.12 * voice * ws - shimmer_in, alpha=min(240.0, base_a * (0.85 + 0.35 * lum_r)), muted=muted))
        g_tr.setColorAt(1.0, _tone(base, 0.80, white_lift=0.02, alpha=base_a * 0.32 * lum_r, muted=muted))
        p.setBrush(QBrush(g_tr))
        p.drawPolygon(QPolygonF([d_top, d_front, d_r]))

        # Faceta Inferior Esquerda
        g_bl = QLinearGradient(d_front, d_bot)
        g_bl.setColorAt(0.0, _tone(base, 0.98, white_lift=0.14 * lum_l + shimmer_in * 0.6, alpha=base_a * (0.75 + 0.30 * lum_l), muted=muted))
        g_bl.setColorAt(1.0, _tone(base, 0.70, white_lift=0.00, alpha=base_a * 0.25, muted=muted))
        p.setBrush(QBrush(g_bl))
        p.drawPolygon(QPolygonF([d_bot, d_front, d_l]))

        # Faceta Inferior Direita
        g_br = QLinearGradient(d_front, d_bot)
        g_br.setColorAt(0.0, _tone(base, 0.98, white_lift=0.14 * lum_r - shimmer_in * 0.6, alpha=base_a * (0.75 + 0.30 * lum_r), muted=muted))
        g_br.setColorAt(1.0, _tone(base, 0.70, white_lift=0.00, alpha=base_a * 0.25, muted=muted))
        p.setBrush(QBrush(g_br))
        p.drawPolygon(QPolygonF([d_bot, d_r, d_front]))

        # 3) Arestas 3D luminosas do cristal interno (destacam as quinas volumétricas com brilho vítreo)
        in_edge_alpha = 155 + 32 * energy + 65 * voice * ws + 24 * mic * wl
        in_pen = QPen(
            _tone(base, 0.98, white_lift=0.22 + 0.15 * voice * ws, alpha=in_edge_alpha, muted=muted),
            1.10 + 0.35 * voice * ws,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        p.setPen(in_pen)
        # Cristas frontais salientes (cruz 3D central projetada)
        p.drawLine(QLineF(d_top, d_front))
        p.drawLine(QLineF(d_bot, d_front))
        p.drawLine(QLineF(d_l, d_front))
        p.drawLine(QLineF(d_r, d_front))
        # Contorno perimétrico fino
        p.setPen(QPen(_tone(base, 0.90, white_lift=0.08, alpha=in_edge_alpha * 0.65, muted=muted), 0.85))
        p.drawPolygon(QPolygonF([d_top, d_r, d_bot, d_l]))

        p.restore()

        # ── 5. Arestas de Facetas, Espinha Vertical, "X", Cintura e Contorno ─────
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Crista vertical superior fina dividindo as 2 facetas da coroa (T -> Meio da Cintura -> Core)
        crown_rib_alpha = 165 + 30 * energy + 40 * wt + 35 * voice * ws
        crown_rib_pen = QPen(
            _tone(base, 0.92, white_lift=0.10 + 0.10 * voice * ws, alpha=crown_rib_alpha, muted=muted),
            1.0,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        p.setPen(crown_rib_pen)
        p.drawLine(QLineF(p_top, p_sh_mid))
        p.drawLine(QLineF(p_sh_mid, p_core))

        inner_edge_alpha = 212 + 30 * energy + 30 * voice * ws
        inner_w = 1.30 + 0.40 * voice * ws
        inner_pen = QPen(
            _tone(base, 0.98, white_lift=0.15 + 0.12 * voice * ws, alpha=inner_edge_alpha, muted=muted),
            inner_w,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(inner_pen)
        p.drawLine(QLineF(p_sl, p_sr))

        # "X" central + Espinha vertical (pulsam rápido em THINKING e acendem forte em SPEAKING)
        x_pulse = 45.0 * wt * abs(math.sin(self._t * 6.2)) + 50.0 * voice * ws
        x_pen = QPen(
            _tone(
                base,
                1.00,
                white_lift=0.20 + 0.18 * voice * ws + 0.10 * wt,
                alpha=min(255.0, inner_edge_alpha + x_pulse),
                muted=muted,
            ),
            inner_w + 0.15 * wt,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        p.setPen(x_pen)
        p.drawLine(QLineF(p_sl, p_core))
        p.drawLine(QLineF(p_sr, p_core))
        p.drawLine(QLineF(p_core, p_kl))
        p.drawLine(QLineF(p_core, p_kr))
        p.drawLine(QLineF(p_core, p_bot))

        outer_pen = QPen(
            _tone(base, 1.00, white_lift=0.18 + 0.16 * voice * ws, alpha=228 + 27 * active_drive, muted=muted),
            1.65 + 0.45 * voice * ws,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.MiterJoin,
        )
        p.setPen(outer_pen)
        p.drawPolygon(hull_poly)

        # ── 6. Orbe Rubi Central + Pontos de Ápice ───────────────────────────────
        orb_r = R * (
            0.046
            + 0.024 * voice * ws
            + 0.010 * mic * wl
            + 0.004 * wt * math.sin(self._t * 9.0)
            + 0.002 * math.sin(self._breathe * 1.4)
        )
        halo_r = orb_r * (2.25 + 1.05 * voice * ws + 0.40 * mic * wl)
        orb_halo = QRadialGradient(p_core, halo_r)
        orb_halo.setColorAt(0.0, _tone(base, 1.00, white_lift=0.38 + 0.25 * voice * ws, alpha=155 + 85 * active_drive, muted=muted))
        orb_halo.setColorAt(0.55, _tone(base, 0.96, white_lift=0.18, alpha=64 + 55 * active_drive, muted=muted))
        orb_halo.setColorAt(1.0, _TRANSPARENT_BLACK)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(orb_halo))
        p.drawEllipse(QRectF(p_core.x() - halo_r, p_core.y() - halo_r, halo_r * 2.0, halo_r * 2.0))

        # Disco central nítido (aquece o centro para rosa-quente/branco nos picos de fala)
        # Camada 2 do coração: anel fino de energia pulsando ao redor do disco (controlado)
        ring_r = orb_r * (1.75 + 0.18 * math.sin(self._t * 3.0) + 0.45 * voice * ws)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_tone(base, 1.00, white_lift=0.22, alpha=105 + 70 * active_drive + 25 * energy, muted=muted), 1.0))
        p.drawEllipse(QRectF(p_core.x() - ring_r, p_core.y() - ring_r, ring_r * 2.0, ring_r * 2.0))
        p.setPen(Qt.PenStyle.NoPen)
        core_lift = 0.33 + 0.34 * voice * ws + 0.12 * mic * wl
        p.setBrush(QBrush(_tone(base, 1.00, white_lift=core_lift, alpha=248, muted=muted)))
        p.drawEllipse(QRectF(p_core.x() - orb_r, p_core.y() - orb_r, orb_r * 2.0, orb_r * 2.0))

        # Micro-losango luminoso no ápice superior e ponto na ponta inferior
        tip_r = max(1.8, R * (0.013 + 0.007 * voice * ws))
        tip_poly = QPolygonF([
            QPointF(p_top.x(), p_top.y() - tip_r * 1.25),
            QPointF(p_top.x() + tip_r, p_top.y()),
            QPointF(p_top.x(), p_top.y() + tip_r * 1.25),
            QPointF(p_top.x() - tip_r, p_top.y()),
        ])
        p.setBrush(QBrush(_tone(base, 1.00, white_lift=0.26 + 0.22 * voice * ws, alpha=238, muted=muted)))
        p.drawPolygon(tip_poly)

        bot_r = max(1.2, R * (0.008 + 0.005 * voice * ws))
        p.setBrush(QBrush(_tone(base, 1.00, white_lift=0.22 + 0.20 * voice * ws, alpha=195 + 55 * active_drive, muted=muted)))
        p.drawEllipse(QRectF(p_bot.x() - bot_r, p_bot.y() - bot_r, bot_r * 2.0, bot_r * 2.0))

        p.restore()

    def _paint_hud_rings(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        R: float,
        base: QColor,
        energy: float,
        voice: float,
        mic: float,
        wl: float,
        wt: float,
        ws: float,
        muted: bool,
    ) -> None:
        """Desenha os 3 anéis orbitais vivos e os efeitos direcionais exclusivos de cada etapa."""
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── A. Ondas Direcionais Exclusivas de LISTENING vs SPEAKING ─────────────
        # LISTENING: ondas acústicas convergentes (fora -> dentro, captando áudio)
        if wl > 0.03 and not muted:
            for ph in self._inward_waves:
                # ph 0->1 move o raio de 0.99*R até 0.56*R
                wr = R * (0.99 - 0.43 * ph)
                env = math.sin(ph * math.pi)
                alpha = env * wl * (46.0 + 115.0 * mic)
                if alpha > 3.0:
                    p.setPen(QPen(_tone(base, 0.78, white_lift=0.10, alpha=alpha, muted=muted), 1.0 + 0.6 * mic))
                    p.drawEllipse(QRectF(cx - wr, cy - wr, wr * 2.0, wr * 2.0))

        # SPEAKING: ondas sônicas expansivas (núcleo -> fora, projetando a voz)
        if ws > 0.03 and not muted:
            for ph in self._outward_waves:
                wr = R * (0.42 + 0.66 * ph)
                env = math.sin(ph * math.pi)
                alpha = env * ws * (62.0 + 150.0 * voice)
                if alpha > 3.0:
                    pen_w = (1.1 + 1.4 * voice) * (1.15 - 0.45 * ph)
                    p.setPen(
                        QPen(
                            _tone(base, 0.96, white_lift=0.16 * (1.0 - ph), alpha=alpha, muted=muted),
                            pen_w,
                        )
                    )
                    p.drawEllipse(QRectF(cx - wr, cy - wr, wr * 2.0, wr * 2.0))

        # ── B. Anel Externo (r = 1.000 * R): Trilha + Bisel Rotativo + Satélites ─
        r_outer = R * (1.0 + 0.014 * voice * ws)
        outer_rect = QRectF(cx - r_outer, cy - r_outer, r_outer * 2.0, r_outer * 2.0)

        # Trilha base sutil mantém o círculo externo de referência
        track_alpha = 72 + 20 * energy
        p.setPen(QPen(_tone(base, 0.34, crimson_blue_bias=0.28, alpha=track_alpha, muted=muted), 1.0))
        p.drawEllipse(outer_rect)

        # 4 arcos de bisel rotativos + ticks radiais nas extremidades (movimento sempre visível!)
        bezel_alpha = 135 + 45 * wt + 55 * voice * ws + 25 * wl
        bezel_pen = QPen(
            _tone(base, 0.58 + 0.20 * wt + 0.22 * voice * ws, crimson_blue_bias=0.26, alpha=bezel_alpha, muted=muted),
            1.4 + 0.35 * voice * ws,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.FlatCap,
        )
        p.setPen(bezel_pen)
        tick_len = max(3.0, R * (0.022 + 0.008 * wt))
        for start_deg, span_deg in self._OUTER_BEZEL_ARCS:
            ang0 = (start_deg + self._outer_phase) % 360.0
            p.drawArc(outer_rect, int(round(ang0 * 16.0)), int(round(span_deg * 16.0)))
            # Pequenos ticks radiais para evidenciar o giro do anel externo
            for edge_deg in (ang0, (ang0 + span_deg) % 360.0):
                rad = math.radians(edge_deg)
                ca, sa = math.cos(rad), -math.sin(rad)
                p.drawLine(
                    QLineF(
                        cx + ca * (r_outer - tick_len),
                        cy + sa * (r_outer - tick_len),
                        cx + ca * (r_outer + tick_len * 0.45),
                        cy + sa * (r_outer + tick_len * 0.45),
                    )
                )

        # 2 micro-satélites orbitando continuamente sobre o anel externo
        sat_r = max(1.6, R * (0.009 + 0.004 * wt))
        sat_col = _tone(base, 0.94, white_lift=0.18, alpha=175 + 60 * wt + 45 * voice * ws, muted=muted)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(sat_col))
        for offset in (63.0, 243.0):
            s_rad = math.radians((offset + self._outer_phase) % 360.0)
            sx_p = cx + math.cos(s_rad) * r_outer
            sy_p = cy - math.sin(s_rad) * r_outer
            p.drawEllipse(QRectF(sx_p - sat_r, sy_p - sat_r, sat_r * 2.0, sat_r * 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── C. Anel Interno (r = 0.720 * R): Giroscópio Contra-Rotativo + Espectro
        r_inner = R * (0.720 + 0.018 * voice * ws - 0.008 * mic * wl)
        inner_rect = QRectF(cx - r_inner, cy - r_inner, r_inner * 2.0, r_inner * 2.0)

        p.setPen(QPen(_tone(base, 0.26, crimson_blue_bias=0.26, alpha=58 + 18 * energy, muted=muted), 0.9))
        p.drawEllipse(inner_rect)

        gyro_alpha = 112 + 65 * wt + 60 * voice * ws + 28 * wl
        gyro_pen = QPen(
            _tone(base, 0.56 + 0.24 * wt + 0.22 * voice * ws, crimson_blue_bias=0.24, alpha=gyro_alpha, muted=muted),
            1.2 + 0.3 * wt,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        p.setPen(gyro_pen)
        for start_deg, span_deg in self._INNER_GYRO_ARCS:
            ang = (start_deg + self._inner_phase) % 360.0
            p.drawArc(inner_rect, int(round(ang * 16.0)), int(round(span_deg * 16.0)))

        # Assinatura SPEAKING no anel interno: ressonador harmônico radial (24 barras simétricas)
        if ws > 0.03 and not muted:
            bars = 24
            bar_base_alpha = ws * (115.0 + 135.0 * voice)
            for i in range(bars):
                theta = (math.tau * i / bars) + math.radians(self._inner_phase * 0.25)
                # Modulação harmônica viva sem precisar de FFT separado
                wave = (
                    0.50
                    + 0.30 * math.sin(theta * 3.0 + self._t * 11.0)
                    + 0.20 * math.cos(theta * 5.0 - self._t * 15.0)
                )
                bar_len = R * (0.012 + 0.058 * voice * wave) * ws
                ca, sa = math.cos(theta), math.sin(theta)
                p.setPen(
                    QPen(
                        _tone(base, 0.96, white_lift=0.18 * voice * wave, alpha=bar_base_alpha * (0.55 + 0.45 * wave), muted=muted),
                        1.35,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                p.drawLine(
                    QLineF(
                        cx + ca * (r_inner - bar_len * 0.35),
                        cy + sa * (r_inner - bar_len * 0.35),
                        cx + ca * (r_inner + bar_len),
                        cy + sa * (r_inner + bar_len),
                    )
                )

        # ── D. Anel Médio (r = 0.865 * R): Telemetria Contra-Rotativa + Beacons ──
        r_mid = R * (0.865 + 0.022 * voice * ws)
        mid_rect = QRectF(cx - r_mid, cy - r_mid, r_mid * 2.0, r_mid * 2.0)

        arc_alpha = 158 + 52 * wt + 68 * voice * ws + 26 * wl
        arc_w = 1.50 + 0.55 * voice * ws + 0.25 * wt
        arc_pen = QPen(
            _tone(
                base,
                0.72 + 0.20 * voice * ws + 0.16 * wt,
                crimson_blue_bias=0.21,
                white_lift=0.05 + 0.14 * voice * ws,
                alpha=min(255.0, arc_alpha),
                muted=muted,
            ),
            arc_w,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        p.setPen(arc_pen)
        # Em SPEAKING os arcos se dilatam com a voz; em THINKING ficam mais curtos e afiados como scanner
        span_scale = 1.0 + 0.18 * voice * ws - 0.14 * wt
        for start_deg, span_deg, layer in self._TELEMETRY_ARCS:
            phase = self._arc_phase_a if layer > 0 else self._arc_phase_b
            ang = (start_deg + phase) % 360.0
            adj_span = max(5.0, span_deg * span_scale)
            p.drawArc(mid_rect, int(round(ang * 16.0)), int(round(adj_span * 16.0)))

        # Assinatura LISTENING: colchetes acústicos equatoriais enquadrando a recepção lateral
        if wl > 0.03 and not muted:
            br_r = r_mid + R * (0.042 - 0.010 * mic)
            br_rect = QRectF(cx - br_r, cy - br_r, br_r * 2.0, br_r * 2.0)
            br_span = 22.0 + 12.0 * mic + 3.0 * math.sin(self._breathe * 1.3)
            br_alpha = wl * (135.0 + 105.0 * mic)
            p.setPen(
                QPen(
                    _tone(base, 0.94, white_lift=0.16 + 0.14 * mic, alpha=br_alpha, muted=muted),
                    1.45 + 0.4 * mic,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            for center_deg in (0.0, 180.0):
                p.drawArc(
                    br_rect,
                    int(round((center_deg - br_span * 0.5) * 16.0)),
                    int(round(br_span * 16.0)),
                )

        # 2 Beacons Rubi Principais (flutuação equatorial em IDLE/LISTENING/SPEAKING; órbita 360° com rastro em THINKING)
        equator_bob = math.sin(self._t * 1.7) * 5.5 * (1.0 - wt)
        base_angles = (
            (0.0 + equator_bob + self._beacon_orbit) % 360.0,
            (180.0 - equator_bob + self._beacon_orbit) % 360.0,
        )

        # Rastros de cometa exclusivos do scanner THINKING
        if wt > 0.04 and not muted:
            trail_span = 34.0 * wt
            p.setPen(
                QPen(
                    _tone(base, 0.96, white_lift=0.18, alpha=155.0 * wt, muted=muted),
                    2.1,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            for b_deg in base_angles:
                p.drawArc(
                    mid_rect,
                    int(round((b_deg - trail_span) * 16.0)),
                    int(round(trail_span * 16.0)),
                )

        dot_r = max(
            2.4,
            R * (0.016 + 0.008 * voice * ws + 0.005 * mic * wl + 0.003 * wt),
        )
        halo_dot_r = dot_r * (2.3 + 1.1 * voice * ws + 0.7 * mic * wl + 0.6 * wt)
        dot_col = _tone(
            base,
            1.00,
            white_lift=0.20 + 0.24 * voice * ws + 0.14 * mic * wl,
            alpha=235 + 20 * max(voice, mic),
            muted=muted,
        )

        p.setPen(Qt.PenStyle.NoPen)
        for b_deg in base_angles:
            rad = math.radians(b_deg)
            dx = cx + math.cos(rad) * r_mid
            dy = cy - math.sin(rad) * r_mid

            d_glow = QRadialGradient(dx, dy, halo_dot_r)
            d_glow.setColorAt(0.0, _tone(base, 1.00, white_lift=0.25, alpha=125 + 95 * max(voice * ws, mic * wl, wt), muted=muted))
            d_glow.setColorAt(1.0, _TRANSPARENT_BLACK)
            p.setBrush(QBrush(d_glow))
            p.drawEllipse(QRectF(dx - halo_dot_r, dy - halo_dot_r, halo_dot_r * 2.0, halo_dot_r * 2.0))

            p.setBrush(QBrush(dot_col))
            p.drawEllipse(QRectF(dx - dot_r, dy - dot_r, dot_r * 2.0, dot_r * 2.0))
