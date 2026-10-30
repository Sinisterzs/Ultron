"""Compact, vector-painted navigation without external icon assets."""

from PyQt6.QtCore import QPointF, QRectF, QRect, Qt, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QPainter, QPainterPath, QPen, QLinearGradient, QTransform, QRadialGradient, QPixmap, QPolygonF, QKeySequence, QShortcut, QBrush
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QPushButton

from ui_theme import BORDER, BORDER_HI


class RailButton(QAbstractButton):
    def __init__(self, text, icon, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setAccessibleName(text)
        self.setToolTip(text)
        self.setCheckable(True)
        self.setFixedSize(71, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon = icon

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        active = self.isChecked()
        color = QColor("#f0f0f5" if active else "#f4f4fa" if self.underMouse() else "#96969f")
        w, h = self.width(), self.height()

        # A geometria do ícone original é aproximadamente 24x26 e começa em (0, 0).
        # O desenho NÃO é centrado na origem. Posicionar pela esquina superior
        # esquerda evita deslocar os ícones sobre os respectivos textos.
        # D22O: scale lettering and icon together with the actual button size.
        scale = min(1.0, max(0.63, min(w / 70.0, h / 46.0)))
        font = QFont("Segoe UI", 8, QFont.Weight.Normal)
        font.setPointSizeF(max(5.5, 8.0 * scale))
        fm = QFontMetrics(font)
        text_h = fm.height()
        padding_y = max(1, round(3 * scale))
        gap = max(1, round(3 * scale))
        # Usar um limite de altura que respeite a altura real da fonte.
        icon_size = min(19.0 * scale, float(max(7, h - 2 * padding_y - text_h - gap)))
        total_h = icon_size + gap + text_h
        top = (h - total_h) / 2.0
        icon_rect = QRectF((w - icon_size) / 2.0, top, icon_size, icon_size)
        text_rect = QRectF(3.0, icon_rect.bottom() + gap, w - 6.0, text_h)

        # D23C: transparent smoked glass, restrained crimson outline.
        # Paint only on hover/selection; no timer or animated effects.
        mx, my = max(2, int(w * 0.06)), max(2, int(h * 0.05))
        radius = min(8, max(4, int(h * 0.18)))
        surface = QRectF(mx, my, w - 2 * mx, h - 2 * my)
        if self.underMouse():
            # D23C.1: bottom-up white reflection, barely translucent.
            # At the bottom the highlight is visible; toward the top it fades to zero.
            hover = QLinearGradient(surface.left(), surface.bottom(),
                                    surface.left(), surface.top())
            hover.setColorAt(0.0, QColor(255, 255, 255, 26))
            hover.setColorAt(0.38, QColor(255, 255, 255, 12))
            hover.setColorAt(0.78, QColor(255, 255, 255, 3))
            hover.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(QPen(QColor(255, 82, 103, 70), 1))
            p.setBrush(hover)
            p.drawRoundedRect(surface, radius, radius)
            # A thin specular reflection, not an opaque white tile.
            p.setPen(QPen(QColor(235, 242, 252, 39), 1))
            p.drawLine(QPointF(surface.left()+radius+2, surface.top()+1),
                       QPointF(surface.right()-radius-2, surface.top()+1))
        if active:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(250, 64, 87, 112), 1))
            p.drawRoundedRect(surface, radius, radius)
            p.setPen(QPen(QColor(255, 53, 78, 200), max(1.0, scale)))
            y = surface.bottom() - 1.0
            p.drawLine(QPointF(surface.left() + surface.width() * .31, y),
                       QPointF(surface.right() - surface.width() * .31, y))

        p.setPen(QPen(color, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.save()
        # _draw_icon tem extensão máxima ~24x26; ajustar ambos os eixos.
        scale = icon_size / 26.0
        actual_w = 24.0 * scale
        p.translate((w - actual_w) / 2.0, icon_rect.top())
        p.scale(scale, scale)
        self._draw_icon(p)
        p.restore()

        p.setFont(font)
        p.setPen(QPen(color))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self.text())

    def _draw_icon(self, p):
        if self.icon == "home":
            path = QPainterPath(QPointF(1, 11))
            for x, y in ((11, 2), (21, 11), (18, 11), (18, 23), (5, 23), (5, 11)):
                path.lineTo(x, y)
            p.drawPath(path)
        elif self.icon == "activity":
            path = QPainterPath(QPointF(0, 13))
            for x, y in ((5, 13), (8, 4), (13, 23), (17, 10), (22, 10)):
                path.lineTo(x, y)
            p.drawPath(path)
        elif self.icon == "plugins":
            for x, y in ((1, 2), (13, 2), (1, 14), (13, 14)):
                p.drawRoundedRect(QRectF(x, y, 8, 8), 2, 2)
        elif self.icon == "memory":
            p.drawRoundedRect(QRectF(2, 2, 19, 22), 3, 3)
            for y in (8, 13, 18):
                p.drawLine(6, y, 17, y)
        elif self.icon == "voice":
            p.drawRoundedRect(QRectF(7, 1, 9, 15), 4, 4)
            p.drawArc(QRectF(3, 5, 17, 16), 180 * 16, 180 * 16)
            p.drawLine(11, 21, 11, 25)
            p.drawLine(7, 25, 16, 25)
        elif self.icon == "engine":
            p.drawRoundedRect(QRectF(4, 5, 15, 15), 2, 2)
            p.drawRect(QRectF(8, 9, 7, 7))
            for n in (7, 12, 17):
                p.drawLine(n, 1, n, 5)
                p.drawLine(n, 20, n, 24)
                p.drawLine(0, n, 4, n)
                p.drawLine(19, n, 23, n)
        elif self.icon == "theme":
            p.drawEllipse(QRectF(1, 2, 22, 22))
            for x, y in ((7, 8), (15, 7), (18, 14), (8, 17)):
                p.drawEllipse(QPointF(x, y), 1.5, 1.5)
        elif self.icon == "settings":
            p.drawEllipse(QRectF(3, 4, 17, 17))
            p.drawEllipse(QRectF(8, 9, 7, 7))
            for angle in range(0, 360, 45):
                p.save()
                p.translate(11.5, 12.5)
                p.rotate(angle)
                p.drawLine(QPointF(0, 9), QPointF(0, 12))
                p.restore()
        else:
            for x, y in ((3, 8), (11, 17), (20, 11)):
                p.drawLine(x, 2, x, 24)
                p.drawEllipse(QPointF(x, y), 2.5, 2.5)


class UserInitial(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.initial = (name.strip() or "U")[0].upper()
        self.setFixedSize(71, 48)
        self.setToolTip(name or "Usuário")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor("#260b12"))
        p.drawEllipse(QRectF(19, 7, 32, 32))
        p.setPen(QColor("#ececf2"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        p.drawText(QRectF(19, 7, 32, 32), Qt.AlignmentFlag.AlignCenter, self.initial)


class SideRail(QWidget):
    pageRequested = pyqtSignal(str)
    PAGES = ("Início", "Atividade", "Plugins", "Memória", "Voz", "Motor", "Tema", "Ajustes")

    def __init__(self, user_name="", parent=None):
        super().__init__(parent)
        self.setFixedWidth(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 1, 0)
        layout.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: #08080b;")
        items = QVBoxLayout(content)
        items.setContentsMargins(0, 0, 0, 0)
        items.setSpacing(0)
        self.buttons = {}
        for name, icon in zip(self.PAGES, ("home", "activity", "plugins", "memory", "voice", "engine", "theme")):
            button = RailButton(name, icon, content)
            button.clicked.connect(lambda checked=False, page=name: self.request_page(page))
            self.buttons[name] = button
            items.addWidget(button)
        items.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.settings_button = RailButton("Ajustes", "settings", self)
        self.controls_button = RailButton("Controles", "controls", self)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.controls_button)
        layout.addWidget(UserInitial(user_name, self))
        self.set_active("Início")

    def set_active(self, page):
        self.settings_button.setChecked(page == "Ajustes")
        for name, button in self.buttons.items():
            button.setChecked(name == page)

    def request_page(self, page):
        if page in self.PAGES:
            self.set_active(page)
            self.pageRequested.emit(page)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#08080b"))
        p.fillRect(self.width() - 1, 0, 1, self.height(), QColor(BORDER))



# D24 Integration: independently animated dock, geometry shared by all visuals.
import csv
import math
import time
import statistics
import bisect
from pathlib import Path

PAGES = ["Início", "Atividade", "Plugins", "Memória", "Voz", "Motor", "Tema", "Ajustes", "Controles"]
SYMBOLS = ["⌂", "⌁", "⊞", "▤", "♩", "⚙", "◉", "✧", "☷"]

def clamp(v, low, high):
    return max(low, min(high, v))

class PanoramicDock(QGraphicsItem):
    """One item with segmented curved projections; hit testing uses same 3D model."""
    def __init__(self, notify):
        super().__init__()
        self.notify = notify
        self.depth = 0.58
        self.selected = 0
        self.hovered = -1
        self.logical_w = 960.0
        self.logical_h = 86.0
        self.samples = []
        self.hit_areas = []
        self._glyph_layout_cache = {}  # D24.14: precompute projection of static glyphs
        self._static_pixmap = None
        self._labels_pixmap = None
        self.static_rebuild_ms = []
        self.labels_rebuild_ms = []
        self.static_cache_hits = 0
        self.hover_changes = 0
        self.hover_paint_ms = []
        self.material_paint_ms = []
        self.effects_enabled = True
        self.fx_paint_ms = []
        self.base_paint_ms = []
        self.travel_enabled = True  # D24.6: start visibly active; A toggles for A/B test
        self.travel_paint_ms = []
        self.travel_on_samples = []
        self.travel_off_samples = []
        self.travel_started = time.perf_counter()
        self.travel_ticks = 0
        # D24.8: one high-density cached glow texture per dock, never generated per frame.
        self._hires_glow = self._build_hires_glow()
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self._build_hit_areas()

    @staticmethod
    def _build_hires_glow():
        """64 logical pixels rendered at 3x density; smooth transparent perimeter."""
        ratio = 3
        extent = 50  # D24.13: fit the travelling halo in the compact viewport
        pm = QPixmap(extent * ratio, extent * ratio)
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = extent / 2
        g = QRadialGradient(QPointF(center, center), 23.0)
        # Remove abrupt color/alpha jumps between stops.
        for stop, rgba in (
            (0.00, (255, 255, 255, 245)),
            (0.035, (255, 226, 234, 232)),
            (0.085, (255, 164, 181, 190)),
            (0.16, (255, 89, 118, 127)),
            (0.29, (245, 36, 76, 72)),
            (0.47, (217, 18, 58, 36)),
            (0.72, (180, 7, 44, 12)),
            (1.00, (130, 0, 25, 0)),
        ):
            g.setColorAt(stop, QColor(*rgba))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(g)
        painter.drawEllipse(QRectF(2, 2, extent-4, extent-4))
        painter.end()
        return pm

    def boundingRect(self):
        # Account for halo and thick rails, otherwise GraphicsView clips them.
        return QRectF(-28, -28, self.logical_w + 56, self.logical_h + 56)

    def set_width(self, width):
        width = float(width)
        if abs(self.logical_w-width) > 0.5:
            self.prepareGeometryChange()
            self.logical_w = width
            self._glyph_layout_cache.clear()
            self._invalidate_cache()
            self._build_hit_areas()
            self.update()

    def _invalidate_cache(self):
        self._static_pixmap = None
        self._labels_pixmap = None

    def toggle_effects(self):
        self.effects_enabled = not self.effects_enabled
        self._invalidate_cache()
        self.update()

    def toggle_travel(self):
        self.travel_enabled = not self.travel_enabled
        self.travel_started = time.perf_counter()
        self.update()

    def set_depth(self, depth):
        self.depth = clamp(depth, 0.20, 1.15)
        self._glyph_layout_cache.clear()
        self._invalidate_cache()
        self._build_hit_areas()
        self.update()

    def _surface(self, u, v):
        """Project a cylindrical segment (u: -1..1; v: -1..1) into view.

        Far side surfaces have lower scale and a slightly higher screen position.
        Every frame/button/highlight vertex uses this same projection.
        """
        theta = u * self.depth
        radius = self.logical_w / (2 * math.sin(self.depth))
        x3 = radius * math.sin(theta)
        z = radius * (1 - math.cos(theta))
        camera = 1.9 * self.logical_w
        k = camera / (camera + z)
        cx = self.logical_w / 2
        cy = self.logical_h * .52
        x = cx + x3 * k
        y = cy + v * (34.0 * k) - z * .095
        return QPointF(x, y)

    def _quad(self, u0, u1, v0=-1.0, v1=1.0):
        return QPolygonF([self._surface(u0, v0), self._surface(u1, v0),
                          self._surface(u1, v1), self._surface(u0, v1)])

    def _curved_patch(self, u0, u1, v0=-1.0, v1=1.0, steps=8):
        """Projected strip with curved top/bottom, never a flat quadrilateral."""
        result = QPainterPath()
        result.moveTo(self._surface(u0, v0))
        for j in range(1, steps+1):
            result.lineTo(self._surface(u0+(u1-u0)*j/steps, v0))
        for j in range(steps, -1, -1):
            result.lineTo(self._surface(u0+(u1-u0)*j/steps, v1))
        result.closeSubpath()
        return result

    def _perimeter(self):
        """Closed, arc-length sampled circuit, including both end caps.

        Cache geometry: only rebuild if dock width or curvature changes.
        """
        key = (round(self.logical_w, 2), round(self.depth, 5))
        if getattr(self, '_perimeter_key', None) == key:
            return self._perimeter_cache
        points = []
        def append_point(u, v):
            points.append(self._surface(u, v))
        samples = 120
        # Clockwise: top L->R, right edge T->B, bottom R->L, left B->T.
        for i in range(samples+1):
            append_point(-1.0 + 2.0*i/samples, -1.20)
        for i in range(1, 19):
            append_point(1.0, -1.20 + 2.41*i/18)
        for i in range(1, samples+1):
            append_point(1.0 - 2.0*i/samples, 1.21)
        for i in range(1, 19):
            append_point(-1.0, 1.21 - 2.41*i/18)
        # points[-1] == points[0]: circuit is geometrically closed.
        distances = [0.0]
        for a, b in zip(points, points[1:]):
            distances.append(distances[-1] + math.hypot(b.x()-a.x(), b.y()-a.y()))
        self._perimeter_key = key
        self._perimeter_cache = (points, distances, distances[-1])
        return self._perimeter_cache

    def _perimeter_point(self, distance):
        points, lengths, total = self._perimeter()
        d = distance % total
        i = max(0, min(len(lengths)-2, bisect.bisect_right(lengths, d)-1))
        span = max(.00001, lengths[i+1]-lengths[i])
        a = (d-lengths[i])/span
        return QPointF(points[i].x()*(1-a)+points[i+1].x()*a,
                       points[i].y()*(1-a)+points[i+1].y()*a)

    def _cell_interval(self, i):
        return -0.93 + 1.86 * i/9, -0.93 + 1.86 * (i+1)/9

    def _build_hit_areas(self):
        self.hit_areas = []
        for i in range(9):
            a,b = self._cell_interval(i)
            self.hit_areas.append(self._curved_patch(a, b, -1.0, 1.0))

    def _curved_text(self, p, text, font, u0, u1, v, *, color):
        """D24.14: cache projected glyph poses; repaint only draws glyphs.

        The cylindrical projection, font metrics, and glyph positioning do
        not change unless geometry/depth changes, so thousands of surface()
        evaluations per repaint were wasted work.
        """
        key = (text, font.family(), font.pointSize(), round(u0, 5),
               round(u1, 5), round(v, 4), round(self.logical_w, 1),
               round(self.depth, 5))
        poses = self._glyph_layout_cache.get(key)
        if poses is None:
            fm = QFontMetricsF(font)
            glyphs = [(char, fm.horizontalAdvance(char)) for char in text]
            text_w = sum(width for _, width in glyphs)
            poses = []
            if text_w > 0:
                mid = (u0 + u1)*.5
                left_pt = self._surface(u0, v)
                right_pt = self._surface(u1, v)
                region_w = right_pt.x() - left_pt.x()
                fit = min(1.0, max(.5, (region_w - 8)/text_w))
                start_x = self._surface(mid, v).x() - text_w * fit *.5
                cursor = 0.0
                for char, advance in glyphs:
                    center_x = start_x + (cursor + advance*.5)*fit
                    lo, hi = u0, u1
                    for _ in range(9):
                        uv = (lo+hi)*.5
                        if self._surface(uv, v).x() < center_x:
                            lo = uv
                        else:
                            hi = uv
                    u = (lo+hi)*.5
                    point = self._surface(u, v)
                    delta = .001
                    before = self._surface(max(-1.0,u-delta), v)
                    after = self._surface(min(1.0,u+delta), v)
                    angle = math.degrees(math.atan2(after.y()-before.y(), after.x()-before.x()))
                    poses.append((char, advance, point, angle, fit, fm.ascent()*.36))
                    cursor += advance
            self._glyph_layout_cache[key] = poses
        p.save()
        p.setFont(font)
        p.setPen(color)
        for char, advance, point, angle, fit, baseline in poses:
            p.save()
            p.translate(point)
            p.rotate(angle)
            p.scale(fit, 1.0)
            p.drawText(QPointF(-advance*.5, baseline), char)
            p.restore()
        p.restore()

    def _label(self, p, i, u0, u1):
        mid = (u0 + u1) / 2
        facing = max(.72, math.cos(mid*self.depth))
        symbol_font = QFont("Segoe UI Symbol", max(11, round(21*facing)))
        font = QFont("Segoe UI", max(8, round(10*facing)))
        text_color = QColor(255, 75, 98) if i == self.selected else QColor(225,226,235)
        # Baselines use the very same cylinder as the frame and highlights.
        self._curved_text(p, SYMBOLS[i], symbol_font, u0, u1, -.32, color=text_color)
        self._curved_text(p, PAGES[i], font, u0, u1, .34, color=text_color)

    def _curve(self, u0, u1, v, steps=44):
        path = QPainterPath(self._surface(u0, v))
        for j in range(1, steps + 1):
            path.lineTo(self._surface(u0 + (u1-u0)*j/steps, v))
        return path

    def _paint_static_material(self, p):
        """Render expensive stationary hull into an offscreen pixmap ONCE."""
        # D24.3: Every hull, reflection and panel uses the SAME cylinder.
        # No full-window blur, no separate animation clock, no raster textures.
        # D24.10: material now uses the ACTUAL projected 86px canvas.
        # The old 36..135px gradients belonged to the large standalone demo,
        # producing a pink opaque strip when embedded in the small dock.
        top_y = self._surface(0, -1.20).y()
        bottom_y = self._surface(0, 1.21).y()
        chassis = self._curved_patch(-1, 1, -1.20, 1.21, steps=64)
        edge_metal = QLinearGradient(0, top_y, 0, bottom_y)
        edge_metal.setColorAt(0.00, QColor(189, 42, 65, 49))
        edge_metal.setColorAt(0.12, QColor(43, 19, 28, 21))
        edge_metal.setColorAt(0.48, QColor(0, 0, 0, 2))
        edge_metal.setColorAt(0.86, QColor(29, 13, 20, 13))
        edge_metal.setColorAt(1.00, QColor(164, 32, 53, 42))
        p.setBrush(edge_metal)
        p.drawPath(chassis)

        # Restrained smoked-glass sheen; no opaque pane hiding the void.
        glass = QLinearGradient(0, self._surface(0, -1.01).y(),
                               0, self._surface(0, 1.01).y())
        glass.setColorAt(0.00, QColor(250, 252, 255, 19))
        glass.setColorAt(0.07, QColor(180, 193, 211, 12))
        glass.setColorAt(0.20, QColor(20, 28, 39, 6))
        glass.setColorAt(0.65, QColor(0, 0, 0, 0))
        glass.setColorAt(0.92, QColor(191, 204, 226, 7))
        glass.setColorAt(1.00, QColor(244, 251, 255, 14))
        p.setBrush(glass)
        p.drawPath(self._curved_patch(-.981, .981, -1.01, 1.01, steps=64))

        # Subdivisions are subtle and stay curved from upper to lower rail.
        for j in range(1, 9):
            u = -.93 + 1.86*j/9
            p.setPen(QPen(QColor(245, 48, 73, 20), .7))
            p.drawLine(self._surface(u, -.88), self._surface(u, .87))

        # Structural rails + shallow layered reflections, no image/Pixmap seam.
        for v, color, width in (
                (-1.20, QColor(232, 44, 65, 171), 1.45),
                (-1.115, QColor(245, 250, 255, 89), .85),
                (-1.025, QColor(239, 66, 86, 60), .75),
                (1.025, QColor(223, 36, 62, 66), .85),
                (1.12, QColor(245, 250, 255, 67), .8),
                (1.21, QColor(244, 43, 70, 175), 1.4)):
            p.setPen(QPen(color, width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(self._curve(-1, 1, v))

        # Fragmented specular rail glints: vivid, but restrained and static.
        for u0, u1, v, alpha, thickness in (
                (-.96,-.79,-1.20,215,2.15),(-.52,-.37,-1.20,115,1.3),
                (-.10,.11,-1.20,88,1.0),(.48,.63,-1.20,147,1.55),
                (.83,.97,-1.20,205,2.0),(-.97,-.77,1.21,175,1.7),
                (-.36,-.13,1.21,120,1.25),(.08,.32,1.21,158,1.55),
                (.76,.96,1.21,184,1.8)):
            p.setPen(QPen(QColor(255, 99, 114, alpha), thickness))
            p.drawPath(self._curve(u0, u1, v, steps=15))

        # Faceted left and right end caps recede in depth with the surface.
        for sign in (-1, 1):
            outer = float(sign)
            inner = sign * .945
            cap = QPolygonF([self._surface(outer, -1.20),
                             self._surface(inner, -.91),
                             self._surface(inner, .91),
                             self._surface(outer, 1.21)])
            p.setPen(QPen(QColor(253, 57, 82, 115), 1.05))
            p.setBrush(QColor(108, 15, 35, 32))
            p.drawPolygon(cap)
            # One outline per end cap; duplicated internal edge removed.

        # D24.10: tiny optical etching/metallic facets that run with curvature.
        # These are static and share the projection of all navigation content.
        for side in (-1.0, 1.0):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(254, 116, 135, 83), 1.0))
            p.drawLine(self._surface(side*.99, -1.16),
                       self._surface(side*.935, -.87))
            p.drawLine(self._surface(side*.935, .88),
                       self._surface(side*.99, 1.17))
            # Avoid a second parallel seam near the outer rail.
        # Metallic upper-lip highlights, segmented to avoid a neon solid bar.
        for ua, ub, opacity in ((-.90,-.78,95),(-.67,-.54,45),
                               (-.28,-.09,68),(.12,.35,46),(.67,.90,98)):
            p.setPen(QPen(QColor(246, 252, 255, opacity), 1.15,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(self._curve(ua, ub, -1.115, steps=12))

        # D24.4: All material FX are ON-DEMAND and share the existing projection.
        # No QTimer, no QGraphicsEffect blur, no full-size image buffers.
        fx_start = time.perf_counter_ns()
        if self.effects_enabled:
            # Soft edge radiance: only short rail segments, not a costly bloom.
            for v, spread, alpha in ((-1.20, 3.2, 16), (1.21, 3.6, 19)):
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(239, 28, 60, alpha), spread,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(self._curve(-.98, .98, v, steps=32))
            # Internal segmented reflections add visible metallic facets and
            # follow the cylinder exactly. Two restrained rows of highlights.
            for j in range(9):
                u0,u1=self._cell_interval(j)
                top_alpha = 29 if j%3 else 49
                p.setPen(QPen(QColor(230, 237, 250, top_alpha), .7))
                p.drawPath(self._curve(u0+.018,u1-.018,-.88,steps=5))
                p.setPen(QPen(QColor(255, 65, 89, 20), .7))
                p.drawPath(self._curve(u0+.018,u1-.018,.87,steps=5))
            # Micro-LEDs on joints: no expensive radial-gradient allocation.
            p.setPen(Qt.PenStyle.NoPen)
            for j in range(1,9):
                u=-.93+1.86*j/9
                for v in (-1.14,1.15):
                    pt=self._surface(u,v)
                    p.setBrush(QColor(248, 59, 82, 112 if j%2 else 68))
                    p.drawEllipse(pt,1.15,1.15)
            # Thin asymmetric glints along the receding end caps.
            for side in (-1.0,1.0):
                p.setPen(QPen(QColor(255, 190, 196, 100), 1.5))
                p.drawLine(self._surface(side,-.86),self._surface(side,-.23))
                p.setPen(QPen(QColor(248, 60, 86, 70), .9))
                p.drawLine(self._surface(side,.26),self._surface(side,.83))
        fx_elapsed=(time.perf_counter_ns()-fx_start)/1e6
        if self.effects_enabled:
            self.fx_paint_ms.append(fx_elapsed)
            if len(self.fx_paint_ms)>1000:
                self.fx_paint_ms=self.fx_paint_ms[-500:]

    def _paint_labels(self, p):
        for i in range(9):
            a, b = self._cell_interval(i)
            self._label(p, i, a, b)

    def _cached_layer(self, layer):
        attribute = '_static_pixmap' if layer == 'material' else '_labels_pixmap'
        pm = getattr(self, attribute)
        if pm is not None:
            self.static_cache_hits += 1
            return pm
        t0 = time.perf_counter_ns()
        bounds = self.boundingRect()
        # Keep 1.0x logical resolution: widget itself is already scaled to 0.70.
        # Gradients, curves, and glyph coordinates are rendered only on rebuild.
        pm = QPixmap(max(1, math.ceil(bounds.width())), max(1, math.ceil(bounds.height())))
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.translate(-bounds.left(), -bounds.top())
        if layer == 'material':
            self._paint_static_material(painter)
        else:
            self._paint_labels(painter)
        painter.end()
        setattr(self, attribute, pm)
        ms = (time.perf_counter_ns()-t0)/1e6
        records = self.static_rebuild_ms if layer == 'material' else self.labels_rebuild_ms
        records.append(ms)
        if len(records)>80:
            del records[:40]
        return pm

    def paint(self, p, option, widget=None):
        started = time.perf_counter_ns()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)

        # D24.18: material and text are cached separately from the moving energy.
        # On each frame, only the transient glow/hover requires vector painting.
        bounds = self.boundingRect()
        p.drawPixmap(bounds.topLeft(), self._cached_layer('material'))

        # D24.7: continuous motion around the entire perimeter.
        # Motion uses arc length rather than U interpolation; both corners and
        # end caps are traversed instead of snapping to the opposite side.
        travel_ns = time.perf_counter_ns()
        if self.travel_enabled:
            t = time.perf_counter() - self.travel_started
            _, _, circumference = self._perimeter()
            speed = 125.0  # projected pixels per second; constant along caps
            for which in range(2):
                # Two lights on opposite sides, moving in opposing directions.
                origin = circumference * (0.00 if which == 0 else .50)
                direction = 1.0 if which == 0 else -1.0
                head_dist = origin + direction * speed*t
                # Trail wraps seamlessly across every corner and the circuit seam.
                # Subpixel Catmull-Rom-like smooth curve, sampled by arc distance.
                # The old 25-point polyline made visible corners in the wide halo.
                sample_count = 61
                spacing = 1.4  # same ~84px tail, denser and smoother
                points = [self._perimeter_point(
                    head_dist - direction * (sample_count-1-j) * spacing)
                    for j in range(sample_count)]
                trail = QPainterPath(points[0])
                for j in range(1, sample_count-1):
                    mid = QPointF((points[j].x()+points[j+1].x())*.5,
                                  (points[j].y()+points[j+1].y())*.5)
                    trail.quadTo(points[j], mid)
                trail.lineTo(points[-1])
                p.setBrush(Qt.BrushStyle.NoBrush)
                for thick, color in (
                    (17.0, QColor(205, 11, 45, 12)),
                    (12.0, QColor(240, 26, 60, 22)),
                    (7.0, QColor(248, 43, 77, 39)),
                    (4.0, QColor(255, 79, 106, 81)),
                    (1.4, QColor(255, 181, 195, 200)),
                ):
                    p.setPen(QPen(color, thick, Qt.PenStyle.SolidLine,
                                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    p.drawPath(trail)

                head = self._perimeter_point(head_dist)
                # High-density cached sprite (3x logical resolution), with
                # smooth pixmap interpolation when the projected head moves.
                p.setPen(Qt.PenStyle.NoPen)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                p.drawPixmap(QPointF(head.x()-25.0, head.y()-25.0), self._hires_glow)
        travel_ms = (time.perf_counter_ns() - travel_ns)/1e6
        if self.travel_enabled:
            self.travel_paint_ms.append(travel_ms)
            if len(self.travel_paint_ms)>600:
                self.travel_paint_ms=self.travel_paint_ms[-400:]

        # Active / hover panel patches projected exactly like the glass surface.
        for i in range(9):
            a, b = self._cell_interval(i)
            if i == self.selected or i == self.hovered:
                hover_start = time.perf_counter_ns()
                patch = self._curved_patch(a+.008,b-.008,-.94,.95,steps=14)
                top = self._surface((a+b)/2,-.94).y()
                bottom = self._surface((a+b)/2,.95).y()
                highlight = QLinearGradient(0,bottom,0,top)
                if i == self.hovered:
                    highlight.setColorAt(0,QColor(255,255,255,28))
                    highlight.setColorAt(.4,QColor(255,255,255,12))
                    highlight.setColorAt(1,QColor(255,255,255,0))
                else:
                    highlight.setColorAt(0,QColor(228,35,64,17))
                    highlight.setColorAt(.5,QColor(128,12,32,4))
                    highlight.setColorAt(1,QColor(228,35,64,0))
                p.setBrush(highlight)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(patch)
                p.setBrush(Qt.BrushStyle.NoBrush)
                # Both rails follow the same projection as the shell.
                if i == self.selected:
                    p.setPen(QPen(QColor(255,94,111,194),1.4))
                    p.drawPath(self._curve(a+.013,b-.013,.96,steps=12))
                    p.setPen(QPen(QColor(251,75,100,80),.75))
                    p.drawPath(self._curve(a+.013,b-.013,-.94,steps=12))
                else:
                    p.setPen(QPen(QColor(241,245,255,72),.8))
                    p.drawPath(self._curve(a+.013,b-.013,.95,steps=12))
                self.hover_paint_ms.append((time.perf_counter_ns()-hover_start)/1e6)
                if len(self.hover_paint_ms)>500:
                    self.hover_paint_ms=self.hover_paint_ms[-250:]
        p.drawPixmap(bounds.topLeft(), self._cached_layer('labels'))

        elapsed=(time.perf_counter_ns()-started)/1e6
        self.samples.append(elapsed)
        bucket = self.travel_on_samples if self.travel_enabled else self.travel_off_samples
        bucket.append(elapsed)
        if len(bucket)>600:
            del bucket[:200]
        if not self.effects_enabled:
            self.base_paint_ms.append(elapsed)
            if len(self.base_paint_ms)>500:
                self.base_paint_ms=self.base_paint_ms[-250:]
        if len(self.samples)>1000:
            self.samples=self.samples[-500:]

    def _hit_index(self, point):
        for i, path in enumerate(self.hit_areas):
            if path.contains(point):
                return i
        return -1

    def hoverMoveEvent(self, event):
        i = self._hit_index(event.pos())
        if i != self.hovered:
            self.hovered = i
            self.hover_changes += 1
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if self.hovered != -1:
            self.hovered = -1
            self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._hit_index(event.pos())
            if i >= 0:
                self.selected = i
                self._labels_pixmap = None
                self.notify(PAGES[i])
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)



class _IntegratedDockView(QGraphicsView):
    def __init__(self, notify, parent):
        super().__init__(parent)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet("background: transparent; border: 0px;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.viewport().setAutoFillBackground(False)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setScene(self._scene)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.item = PanoramicDock(notify)
        self._scene.addItem(self.item)
        # D24.12: real transparent padding at both sides and top; prevents
        # high-resolution traveling glow from being clipped in window mode.
        # Compact projection, centered within enough physical space for glow.
        self._scale = 0.70
        self._pad_x = 29
        self._top = 20
        self.resetTransform()
        self.scale(self._scale, self._scale)
        self.item.setPos(self._pad_x / self._scale, self._top / self._scale)
        # D24.17: animation cadence is supplied by the existing HUD clock.
        self._last_anim_paint = 0.0
        self._last_dirty_rects = []

    def _animate(self, now=None):
        if not self.isVisible() or not self.item.travel_enabled:
            return
        now = time.perf_counter() if now is None else now
        # At most 30 dock frames/s; on a 47 Hz HUD the samples follow HUD ticks.
        # No competing QTimer. Position itself is always time-based.
        if now - self._last_anim_paint < 1.0 / 30.0:
            return
        self._last_anim_paint = now
        self.item.travel_ticks += 1
        # D24.17: minimize dirty viewport work by invalidating old/new
        # track positions only, not the entire GraphicsItem bounds.
        import math
        rects = []
        item = self.item
        _, _, circumference = item._perimeter()
        elapsed = now - item.travel_started
        for i in range(2):
            direction = 1.0 if i == 0 else -1.0
            dist = circumference * (0.0 if i == 0 else .5) + direction * 125.0 * elapsed
            # Path has ~84 px tail plus 50px halo; union all positions.
            pts = [item._perimeter_point(dist - direction*j*7.0) for j in range(13)]
            xs = [p.x() for p in pts]
            ys = [p.y() for p in pts]
            rects.append(QRectF(min(xs)-29, min(ys)-29,
                                max(xs)-min(xs)+58, max(ys)-min(ys)+58))
        for rect in self._last_dirty_rects + rects:
            item.update(rect)
        self._last_dirty_rects = rects

    def set_dock_width(self, width):
        width = max(320, int(width))
        # Keep horizontal margins even for moving halos at narrow widths.
        content_w = max(280, width - 2 * self._pad_x)
        self.item.set_width(content_w / self._scale)
        self._scene.setSceneRect(0, 0, width / self._scale, 104 / self._scale)
        # Do NOT resetTransform here: it would undo responsive sizing.


class BottomNavBar(QWidget):
    """D24.8 integrated floating 2.5D dock. Compatible with legacy UI APIs."""
    pageRequested = pyqtSignal(str)
    PAGES = tuple(PAGES[:-1])
    # D24.12: compact dock; no reserved opaque footer or giant 142px layer.
    DOCK_W = 684
    DOCK_MIN_W = 410
    DOCK_VIEWPORT_RATIO = 0.53
    DOCK_H = 104

    def __init__(self, user_name="", parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.DOCK_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._available_w = 980
        # The main UI calls .clicked.connect on Ajustes and Controles.
        # Keep real Qt signals while the visible dock is drawn on one scene.
        self.buttons = {}
        for name in PAGES:
            b = QPushButton(name, self)
            b.setCheckable(True)
            b.hide()
            self.buttons[name] = b
        self._view = _IntegratedDockView(self._on_choice, self)
        self._view.item.selected = 0
        from core.app_paths import data_root
        self._diag_path = data_root() / "logs" / "d24_18_cached_dock_diagnostics.csv"
        self._dock_w = 0
        self._reposition()
        self._shortcut = QShortcut(QKeySequence("Ctrl+Alt+L"), self)
        self._shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcut.activated.connect(self.toggle_energy)

    def bind_hud_clock(self, hud):
        """D24.17: reuse HudCanvas's frame signal, no dock timer."""
        self._hud_clock = hud
        hud.pacedFrame.connect(self._on_hud_tick)

    def _on_hud_tick(self, now):
        self._view._animate(now)
        # Capture comparisons by window mode every 10 seconds without a timer.
        if now - getattr(self, '_last_diag', 0.0) >= 10.0:
            self._last_diag = now
            self._log_sample('periodic_10s')

    def toggle_energy(self):
        self._view.item.toggle_travel()
        self._view._last_dirty_rects = []
        self._view.item.update()  # clear former glow immediately, once
        self._log_sample('toggle_energy')

    def _on_choice(self, name):
        if name not in self.buttons:
            return
        if name in self.PAGES:
            # Page navigation must not re-emit the hidden compatibility click:
            # Ajustes' handler calls request_page(), which would recurse here.
            self.set_active(name)
            self.pageRequested.emit(name)
        else:
            # Let the checkable control toggle itself. Preselecting it would
            # cause click() to uncheck it before the drawer handler runs.
            self.buttons[name].click()
        self._log_sample('click:' + name)

    def request_page(self, page):
        if page in self.buttons:
            self._on_choice(page)

    def set_active(self, page):
        for name, button in self.buttons.items():
            button.setChecked(name == page)
        if page in PAGES:
            self._view.item.selected = PAGES.index(page)
            self._view.item._labels_pixmap = None
            self._view.item.update()

    def popup_anchor(self, name, parent):
        """Map the painted dock cell to a widget coordinate for popups."""
        index = PAGES.index(name)
        cell = self._view.item.hit_areas[index].boundingRect()
        point = QPointF(cell.center().x(), cell.top())
        scene_point = self._view.item.mapToScene(point)
        viewport_point = self._view.mapFromScene(scene_point)
        return self._view.viewport().mapTo(parent, viewport_point)

    def update_viewport_width(self, width):
        width = max(1, int(width))
        if self._available_w != width:
            self._available_w = width
            self._reposition()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self):
        available = min(self.width() or self._available_w, self._available_w)
        if available <= 0:
            return
        width = min(self.DOCK_W, max(self.DOCK_MIN_W, int(available*self.DOCK_VIEWPORT_RATIO)), max(320, available-12))
        if self._dock_w != width:
            self._dock_w = width
            self._view.set_dock_width(width)
        # Dock drifts slightly left in window mode; centered on maximized.
        win = self.window()
        maximized = bool(win and win.isMaximized())
        shift = 0 if maximized else -min(54, max(0, available-width)//3)
        x = max(0, (available-width)//2 + shift)
        if self._view.geometry() != QRect(x, 0, width, self.DOCK_H):
            self._view.setGeometry(x, 0, width, self.DOCK_H)

    def _log_sample(self, reason):
        item = self._view.item
        samples = item.samples[-250:]
        if not samples:
            return
        try:
            self._diag_path.parent.mkdir(parents=True, exist_ok=True)
            header = not self._diag_path.exists()
            ordered = sorted(samples)
            with self._diag_path.open("a", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                if header:
                    wr.writerow(("timestamp","event","paint_count","paint_mean_ms","paint_p95_ms","travel_enabled","travel_paint_mean_ms","fx_mean_ms","window_mode","hud_target_fps","dock_anim_ticks","static_cache_hits","static_rebuild_ms","labels_rebuild_ms"))
                wr.writerow((time.strftime("%Y-%m-%d %H:%M:%S"), reason, len(item.samples),
                             round(statistics.fmean(samples),3), round(ordered[int(.95*(len(ordered)-1))],3),
                             int(item.travel_enabled),
                             round(statistics.fmean(item.travel_paint_ms),3) if item.travel_paint_ms else 0,
                             round(statistics.fmean(item.fx_paint_ms),3) if item.fx_paint_ms else 0,
                             'maximized' if self.window().isMaximized() else 'windowed',
                             getattr(getattr(self, '_hud_clock', None), '_fps_target', ''),
                             item.travel_ticks, item.static_cache_hits,
                             round(statistics.fmean(item.static_rebuild_ms),3) if item.static_rebuild_ms else 0,
                             round(statistics.fmean(item.labels_rebuild_ms),3) if item.labels_rebuild_ms else 0))
        except OSError:
            pass

    def closeEvent(self, event):
        self._log_sample('close')
        super().closeEvent(event)
