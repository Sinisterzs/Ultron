"""Sinal de áudio do HUD (D20 — VOID OS): estado + ondas sob o cristal.

Desenho puro em ``QPainter`` — sem timers, sem rede e sem captura própria. O
chamador entrega o nível de áudio já suavizado (microfone ao ouvir, voz do
Ultron ao falar) e um contador de quadros do relógio compartilhado do HUD.

Estados visuais:
  STANDBY     linha discreta de pontos, sem animação constante;
  LISTENING   barras simétricas guiadas pelo nível real do microfone;
  PROCESSING  segmentos que acendem em sequência, com marcadores altos;
  SPEAKING    barras simétricas guiadas pelo nível da voz reproduzida.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

BLOCK_H = 142.0 * 0.68     # altura total reservada para o bloco (já escalada)
SCALE = 0.68               # escala visual do bloco inteiro
_TEXT_H = 22.0
_HALF = 38.0               # meia-altura máxima das barras
_BARS = 48


def _mix(col: QColor, a: float) -> QColor:
    """Mistura ``col`` sobre preto puro (evita compor transparência no Qt)."""
    a = max(0.0, min(1.0, a))
    return QColor(int(col.red() * a), int(col.green() * a), int(col.blue() * a))


def mode_for(state: str, speaking: bool, muted: bool) -> str:
    if muted:
        return "muted"
    if speaking:
        return "speaking"
    st = str(state or "").upper()
    if st in ("THINKING", "PROCESSING"):
        return "processing"
    if st == "LISTENING":
        return "listening"
    return "idle"


def paint_audio_signal(
    p: QPainter,
    cx: float,
    top: float,
    width: float,
    *,
    mode: str,
    state: str,
    amp: float,
    tick: int,
    primary: QColor,
    accent: QColor,
    muted_color: QColor,
    caption: str = "ULTRON / AUDIO CORE",
) -> None:
    """Desenha o bloco a partir de ``top`` (topo da linha de estado)."""
    if width < 120:
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(cx, top); p.scale(SCALE, SCALE); cx, top, width = 0.0, 0.0, width / SCALE

    if mode == "muted":
        col, label = QColor(muted_color), "MUTED"
    elif mode == "speaking":
        col, label = QColor(accent), "SPEAKING"
    elif mode == "processing":
        col, label = _mix(QColor(primary).lighter(125), 1.0), "PROCESSING"
    elif mode == "listening":
        col, label = QColor(primary), "LISTENING"
    else:
        st = str(state or "").upper()
        col = _mix(primary, 0.72)
        label = "STANDBY" if st in ("", "IDLE") else st

    # ── Linha de estado: ● TEXTO com filetes finos nas laterais ──────────────
    font = QFont("Consolas", 13, QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
    p.setFont(font)
    tw = QFontMetricsF(font).horizontalAdvance(label)
    row_cy = top + _TEXT_H / 2.0
    total = tw + 18.0
    x0 = cx - total / 2.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawEllipse(QPointF(x0 + 3.5, row_cy), 3.5, 3.5)
    p.setPen(QPen(col, 1))
    p.drawText(QRectF(x0 + 18.0, top, tw + 6.0, _TEXT_H),
               Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

    rule = _mix(primary, 0.50)
    gap = total / 2.0 + 14.0
    length = min(150.0, width * 0.26)
    p.setPen(QPen(rule, 1))
    p.drawLine(QPointF(cx - gap - length, row_cy), QPointF(cx - gap, row_cy))
    p.drawLine(QPointF(cx + gap, row_cy), QPointF(cx + gap + length, row_cy))

    # ── Sinal ────────────────────────────────────────────────────────────────
    yc = top + _TEXT_H + 8.0 + _HALF
    pitch = min(10.0, (width * 0.86) / _BARS)
    bw = max(2.0, pitch * 0.68)
    xs = cx - (_BARS * pitch) / 2.0 + (pitch - bw) / 2.0

    if mode == "listening" or mode == "speaking":
        lvl = max(0.0, min(1.0, amp))
        drive = min(1.0, lvl * 2.4 + (0.12 if mode == "speaking" else 0.07))
        p.setPen(QPen(_mix(primary, 0.55), 1.4))
        p.drawLine(QPointF(xs - 6, yc), QPointF(xs + _BARS * pitch, yc))
        phase = tick * 0.11
        p.setPen(Qt.PenStyle.NoPen)
        center = (_BARS - 1) / 2.0
        for i in range(_BARS):
            lobe = 0.55 * abs(math.sin(i * 0.33 + phase)) + 0.45 * abs(math.sin(i * 0.81 - phase * 1.3))
            edge = 0.45 + 0.55 * (1.0 - abs(i - center) / center) ** 0.5
            h = 1.5 + drive * (_HALF - 1.5) * lobe * edge
            strong = h > _HALF * 0.30
            p.setBrush(col if strong else _mix(col, 0.92))
            p.drawRect(QRectF(xs + i * pitch, yc - h, bw, h * 2.0))
    elif mode == "processing":
        head = (tick * 0.42) % _BARS
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(_BARS):
            behind = (head - i) % _BARS            # 0 = ponta acesa, cresce para trás
            glow = max(0.0, 1.0 - behind / 14.0)
            marker = (i % 8 == 0)
            intensity = 0.48 + 0.52 * glow
            if marker:
                h = 26.0 + 8.0 * glow
                p.setBrush(_mix(col, 0.70 + 0.30 * glow))
                p.drawRect(QRectF(xs + i * pitch, yc - h, bw, h * 2.0))
            else:
                h = 5.0 + 2.5 * glow
                p.setBrush(_mix(col, intensity))
                p.drawRect(QRectF(xs + i * pitch, yc - h, bw, h * 2.0))
    else:
        # STANDBY / MUTED: pontos discretos e estáticos
        dim = _mix(col, 0.8 if mode == "idle" else 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dim)
        for i in range(_BARS):
            p.drawRect(QRectF(xs + i * pitch, yc - 3.0, bw, 6.0))
        p.setPen(QPen(_mix(primary, 0.55), 1.4))
        p.drawLine(QPointF(xs - 6, yc), QPointF(xs + _BARS * pitch, yc))

    # ── Legenda ──────────────────────────────────────────────────────────────
    ly = yc + _HALF + 8.0
    p.setPen(QPen(_mix(primary, 0.45), 1))
    half_rule = min(width * 0.40, 240.0)
    p.drawLine(QPointF(cx - half_rule, ly), QPointF(cx + half_rule, ly))
    cap_font = QFont("Consolas", 9)
    cap_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
    p.setFont(cap_font)
    p.setPen(QPen(QColor(190, 170, 176), 1))
    p.drawText(QRectF(cx - half_rule, ly + 5.0, half_rule * 2.0, 18.0),
               Qt.AlignmentFlag.AlignCenter, caption)
    p.restore()
