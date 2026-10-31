"""D20 VOID DOCK — Barra inferior trapezoidal chanfrada em #000000 com atalhos globais.

Sem timers nem animação própria: repinta apenas ao passar o mouse, clicar ou
mudar a página ativa.
"""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF,
)
from PyQt6.QtWidgets import QWidget

PAGE_ORDER = (
    "Início", "Atividade", "Plugins", "Memória", "Voz",
    "Motor", "Tema", "Ajustes", "Controles",
)
DOCK_ITEMS = (
    ("Início", "HOME", "home"),
    ("Atividade", "ACTIVITY", "activity"),
    ("Remoto", "REMOTE", "remote"),
    ("Ajustes", "SETTINGS", "settings"),
    ("Controles", "CONTROLS", "controls"),
)
DOCK_NAMES = tuple(item[0] for item in DOCK_ITEMS)
ICONS = tuple(item[2] for item in DOCK_ITEMS)

INACTIVE = QColor("#9a9aa6")
HOVER = QColor("#f4f4fa")


def _draw_icon(p, key, color):
    """Desenha ícone vetorial nítido em grade 24×24 já transladada."""
    pen = QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if key == "home":
        path = QPainterPath(QPointF(3.5, 11.5))
        for x, y in ((12, 3.5), (20.5, 11.5), (20.5, 20.5), (14.5, 20.5),
                     (14.5, 14.5), (9.5, 14.5), (9.5, 20.5), (3.5, 20.5)):
            path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    elif key == "activity":
        path = QPainterPath(QPointF(2, 13))
        for x, y in ((7.5, 13), (10.5, 6.5), (13.5, 17.5), (16.5, 10.5), (22, 10.5)):
            path.lineTo(x, y)
        p.drawPath(path)
    elif key == "remote":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(12, 16.5), 2.2, 2.2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawArc(QRectF(6.5, 11.0, 11.0, 11.0), 35 * 16, 110 * 16)
        p.drawArc(QRectF(2.5, 6.5, 19.0, 19.0), 35 * 16, 110 * 16)
    elif key == "settings":
        p.drawEllipse(QPointF(12, 12), 5.2, 5.2)
        for i in range(8):
            a = i * math.tau / 8.0
            p.drawLine(
                QPointF(12 + 6.4 * math.cos(a), 12 + 6.4 * math.sin(a)),
                QPointF(12 + 9.2 * math.cos(a), 12 + 9.2 * math.sin(a)),
            )
    else:  # controls
        for y, dot_x in ((6.5, 9.0), (12.0, 15.5), (17.5, 10.5)):
            p.drawLine(QPointF(3.5, y), QPointF(20.5, y))
            p.setBrush(QColor("#000000"))
            p.drawEllipse(QPointF(dot_x, y), 2.1, 2.1)
            p.setBrush(Qt.BrushStyle.NoBrush)


class FlatDock(QWidget):
    """VOID DOCK — barra trapezoidal inferior em #000000 com borda carmesim fina."""

    chosen = pyqtSignal(str)
    FRAME_H = 42
    TOP = 52

    def __init__(self, accent=lambda: "#ff2034", parent=None):
        super().__init__(parent)
        self._accent = accent
        self.selected = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── geometria ──────────────────────────────────────────────────────────
    def _frame(self):
        return QRectF(2, self.TOP, max(20, self.width() - 4), self.FRAME_H)

    def _slot_rect(self, slot: int) -> QRectF:
        frame = self._frame()
        inner = frame.adjusted(16, 0, -16, 0)
        width = inner.width() / len(DOCK_ITEMS)
        slot = max(0, min(len(DOCK_ITEMS) - 1, int(slot)))
        return QRectF(inner.left() + slot * width, frame.top(), width, frame.height())

    def _slot_for_page_index(self, index: int) -> int:
        if 0 <= index < len(PAGE_ORDER):
            page_name = PAGE_ORDER[index]
            if page_name in DOCK_NAMES:
                return DOCK_NAMES.index(page_name)
        return max(0, min(len(DOCK_ITEMS) - 1, int(index)))

    def _cell(self, index: int) -> QRectF:
        """Retorna célula da dock (aceita índice em PAGES ou slot direto)."""
        return self._slot_rect(self._slot_for_page_index(index))

    def hit_index(self, point) -> int:
        pt = QPointF(point)
        for slot in range(len(DOCK_ITEMS)):
            if self._slot_rect(slot).contains(pt):
                return slot
        return -1

    def popup_anchor_local(self, index: int) -> QPointF:
        cell = self._cell(index)
        return QPointF(cell.center().x(), cell.top())

    # ── eventos ────────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event):
        slot = self.hit_index(event.position())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if slot >= 0 else Qt.CursorShape.ArrowCursor
        )
        if slot != self._hover:
            self._hover = slot
            self.update()
        event.accept()

    def leaveEvent(self, event):
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            slot = self.hit_index(event.position())
            if slot >= 0:
                self.chosen.emit(DOCK_NAMES[slot])
                return
        super().mousePressEvent(event)

    # ── pintura ────────────────────────────────────────────────────────────
    def _paint_frame(self, p, red):
        f = self._frame()
        c, m = 13.0, 1.5
        l, r, t, b = f.left() + m, f.right() - m, f.top() + m, f.bottom() - m
        # Top-chamfered VOID DOCK trapezoid matching the wireframe silhouette.
        outline = QPolygonF([
            QPointF(l, b),
            QPointF(l, t + c),
            QPointF(l + c, t),
            QPointF(r - c, t),
            QPointF(r, t + c),
            QPointF(r, b),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 255))
        p.drawPolygon(outline)

        edge = QColor(red)
        edge.setAlpha(150)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(edge, 1.25))
        p.drawPolygon(outline)

        hi = QColor(red)
        hi.setAlpha(235)
        p.setPen(QPen(hi, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPolyline(QPolygonF([QPointF(l, t + c), QPointF(l + c, t), QPointF(l + c + 24.0, t)]))
        p.drawPolyline(QPolygonF([QPointF(r - c - 24.0, t), QPointF(r - c, t), QPointF(r, t + c)]))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        red = QColor(self._accent())
        self._paint_frame(p, red)

        slot_w = self._slot_rect(0).width()
        show_icon = slot_w >= 86.0
        icon_scale = 0.54
        icon_sz = 24.0 * icon_scale

        font = QFont("Consolas")
        font.setPixelSize(10 if slot_w >= 92.0 else 9)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        p.setFont(font)
        metrics = QFontMetrics(font)

        for slot, (_page_key, label, icon_key) in enumerate(DOCK_ITEMS):
            cell = self._slot_rect(slot)
            active = slot == self.selected
            hovered = slot == self._hover
            color = red if active else (HOVER if hovered else INACTIVE)

            text_w = metrics.horizontalAdvance(label)
            gap = 6.0 if show_icon else 0.0
            group_w = (icon_sz + gap if show_icon else 0.0) + text_w
            start_x = cell.center().x() - group_w / 2.0
            cy = cell.center().y()

            if show_icon:
                p.save()
                p.translate(start_x, cy - icon_sz / 2.0)
                p.scale(icon_scale, icon_scale)
                _draw_icon(p, icon_key, color)
                p.restore()
                text_x = start_x + icon_sz + gap
            else:
                text_x = start_x

            p.setFont(font)
            p.setPen(color)
            text_rect = QRectF(text_x, cell.top(), text_w + 4.0, cell.height())
            p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

            if active:
                half = min(group_w / 2.0 + 2.0, cell.width() / 2.0 - 4.0)
                p.setPen(QPen(red, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                y = cell.bottom() - 4.5
                p.drawLine(QPointF(cell.center().x() - half, y), QPointF(cell.center().x() + half, y))

            if slot > 0:
                div = QColor(red)
                div.setAlpha(38)
                p.setPen(QPen(div, 1.0))
                p.drawLine(QPointF(cell.left(), cell.top() + 10.0), QPointF(cell.left(), cell.bottom() - 10.0))
        p.end()
