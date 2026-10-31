"""Dock inferior plano em vetor (sem imagens): moldura chanfrada, ícones e rótulos.

Sem timers nem animação própria: repinta apenas ao passar o mouse, clicar ou
mudar a página ativa.
"""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF,
)
from PyQt6.QtWidgets import QWidget

PAGE_ORDER = ("Início", "Atividade", "Plugins", "Memória", "Voz",
              "Motor", "Tema", "Ajustes", "Controles")
ICONS = ("home", "activity", "plugins", "memory", "voice", "engine",
         "theme", "settings", "controls")
INACTIVE = QColor("#a4a4ad")
HOVER = QColor("#f2f2f6")
LAVENDER = QColor("#c9bfe4")


def _draw_icon(p, key, color):
    """Desenha em uma grade 24×24 já transladada; `color` é a tinta atual."""
    pen = QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if key == "home":
        path = QPainterPath(QPointF(3, 11.5))
        for x, y in ((12, 3), (21, 11.5), (21, 21), (14.5, 21), (14.5, 14),
                     (9.5, 14), (9.5, 21), (3, 21)):
            path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    elif key == "activity":
        path = QPainterPath(QPointF(2, 13))
        for x, y in ((8, 13), (11, 9), (13, 15), (16, 10), (22, 11)):
            path.lineTo(x, y)
        p.drawPath(path)
    elif key == "plugins":
        p.drawRect(QRectF(3, 3, 18, 18))
        thin = QPen(color, 1.0)
        p.setPen(thin)
        for n in (7.5, 12, 16.5):
            p.drawLine(QPointF(n, 3), QPointF(n, 21))
            p.drawLine(QPointF(3, n), QPointF(21, n))
    elif key == "memory":
        p.drawRoundedRect(QRectF(3, 3, 18, 18), 1.5, 1.5)
        p.setPen(QPen(color, 1.3))
        for y in (7.5, 11, 14.5, 18):
            p.drawLine(QPointF(6, y), QPointF(18, y))
    elif key == "voice":
        p.drawEllipse(QPointF(12, 12), 9, 9)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(12, 12), 5.3, 5.3)
    elif key == "engine":
        path = QPainterPath(QPointF(12, 3))
        for x, y in ((21, 12), (12, 21), (3, 12)):
            path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    elif key == "theme":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for i in range(12):
            a = i * math.tau / 12
            p.drawEllipse(QPointF(12 + 8.5 * math.cos(a), 12 + 8.5 * math.sin(a)), 1.0, 1.0)
    elif key == "settings":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        teeth = 8
        points = []
        for i in range(teeth * 2):
            a0 = (i / (teeth * 2)) * math.tau
            a1 = ((i + 1) / (teeth * 2)) * math.tau
            r = 10.5 if i % 2 == 0 else 7.6
            for a in (a0 + 0.05, a1 - 0.05):
                points.append(QPointF(12 + r * math.cos(a), 12 + r * math.sin(a)))
        gear = QPainterPath()
        gear.addPolygon(QPolygonF(points))
        gear.closeSubpath()
        hole = QPainterPath()
        hole.addEllipse(QPointF(12, 12), 3.6, 3.6)
        p.drawPath(gear.subtracted(hole))
    else:  # controls: quadrado hachurado
        p.drawRect(QRectF(3, 3, 18, 18))
        p.save()
        p.setClipRect(QRectF(3, 3, 18, 18))
        p.setPen(QPen(color, 1.2))
        for k in range(-18, 24, 3):
            p.drawLine(QPointF(3 + k, 21), QPointF(21 + k, 3))
        p.restore()


class FlatDock(QWidget):
    """Barra de navegação plana. Emite `chosen(nome)` ao clicar numa célula."""
    chosen = pyqtSignal(str)
    FRAME_H = 58
    TOP = 26

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
        return QRectF(2, self.TOP, self.width() - 4, self.FRAME_H)

    def _cell(self, index):
        frame = self._frame()
        inner = frame.adjusted(12, 0, -12, 0)
        width = inner.width() / len(PAGE_ORDER)
        return QRectF(inner.left() + index * width, frame.top(), width, frame.height())

    def hit_index(self, point):
        for i in range(len(PAGE_ORDER)):
            if self._cell(i).contains(QPointF(point)):
                return i
        return -1

    def popup_anchor_local(self, index):
        cell = self._cell(index)
        return QPointF(cell.center().x(), cell.top())

    # ── eventos ────────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event):
        index = self.hit_index(event.position())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if index >= 0 else Qt.CursorShape.ArrowCursor
        )
        if index != self._hover:
            self._hover = index
            self.update()
        event.accept()

    def leaveEvent(self, event):
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.hit_index(event.position())
            if index >= 0:
                self.chosen.emit(PAGE_ORDER[index])
                return
        super().mousePressEvent(event)

    # ── pintura ────────────────────────────────────────────────────────────
    def _paint_frame(self, p, red):
        f = self._frame()
        c, m = 15.0, 1.5
        l, r, t, b = f.left() + m, f.right() - m, f.top() + m, f.bottom() - m
        outline = QPolygonF([
            QPointF(l + c, t), QPointF(r - c, t), QPointF(r, t + c), QPointF(r, b - c),
            QPointF(r - c, b), QPointF(l + c, b), QPointF(l, b - c), QPointF(l, t + c)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 230))
        p.drawPolygon(outline)
        dim = QColor(red)
        dim.setAlpha(80)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(dim, 1.3))
        p.drawPolygon(outline)
        seg = min(92.0, f.width() * 0.18)
        p.setPen(QPen(red, 2.2))
        mid = c + 8
        for sx in (1, -1):
            x0 = l if sx == 1 else r
            xe = (l + c + seg) if sx == 1 else (r - c - seg)
            corner = (l + c) if sx == 1 else (r - c)
            p.drawPolyline(QPolygonF([QPointF(xe, t), QPointF(corner, t),
                                      QPointF(x0, t + c), QPointF(x0, t + mid)]))
            p.drawPolyline(QPolygonF([QPointF(xe, b), QPointF(corner, b),
                                      QPointF(x0, b - c), QPointF(x0, b - mid)]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(red)
        cx = f.center().x()
        p.drawEllipse(QPointF(cx, t), 2.3, 2.3)
        p.drawEllipse(QPointF(cx, b), 2.3, 2.3)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        red = QColor(self._accent())
        self._paint_frame(p, red)
        cell_w = self._cell(0).width()
        icon_scale = min(0.75, max(0.58, cell_w / 72.0))
        icon_sz = 24.0 * icon_scale
        font = QFont("Consolas")
        font.setPixelSize(max(7, min(8, int(cell_w / 6.5))))
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)
        metrics = QFontMetrics(font)
        for i, name in enumerate(PAGE_ORDER):
            cell = self._cell(i)
            active = i == self.selected
            hovered = i == self._hover
            color = red if active else (HOVER if hovered else INACTIVE)
            icon_color = color
            if ICONS[i] == "settings" and not active:
                icon_color = HOVER if hovered else LAVENDER
            p.save()
            p.translate(cell.center().x() - icon_sz / 2.0, cell.top() + 10)
            p.scale(icon_scale, icon_scale)
            _draw_icon(p, ICONS[i], icon_color)
            p.restore()
            p.setFont(font)
            p.setPen(color)
            label = name.upper()
            label_rect = QRectF(cell.left(), cell.top() + 33, cell.width(), 13)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label)
            if active:
                half = min(metrics.horizontalAdvance(label) / 2.0 + 3, cell.width() / 2.0 - 2)
                p.setPen(QPen(red, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                y = cell.top() + 49
                p.drawLine(QPointF(cell.center().x() - half, y), QPointF(cell.center().x() + half, y))
        p.end()
