"""D20 VOID OS — Fixed angular primary panels and ~200 ms expanding submenus.

No QGraphicsProxyWidget (all text and controls remain 100% flat, straight, and
sharp) and no independent QTimer (slide interpolation shares HudCanvas.pacedFrame).
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)


def build_angular_polygon(
    width: float,
    height: float,
    side: str = "left",
    *,
    tilt_top: float = 13.0,
    tilt_bot: float = 9.0,
    chamfer: float = 11.0,
) -> QPolygonF:
    """Return an angular chamfered polygon visually inclined toward the crystal."""
    w = max(24.0, float(width))
    h = max(24.0, float(height))
    m = 1.5
    c = min(float(chamfer), w * 0.14, h * 0.08)
    tt = min(float(tilt_top), h * 0.10)
    tb = min(float(tilt_bot), h * 0.08)
    co = max(3.0, c * 0.45)

    if side == "left":
        y_tl, y_bl = m, h - m
        y_tr, y_br = m + tt, h - m - tb
        pts = [
            QPointF(m, y_tl + c),
            QPointF(m + c, y_tl),
            QPointF(w - m - c, y_tr),
            QPointF(w - m, y_tr + c),
            QPointF(w - m, y_br - c),
            QPointF(w - m - c, y_br),
            QPointF(m + co, y_bl),
            QPointF(m, y_bl - co),
        ]
    else:
        y_tl, y_bl = m + tt, h - m - tb
        y_tr, y_br = m, h - m
        pts = [
            QPointF(m, y_tl + c),
            QPointF(m + c, y_tl),
            QPointF(w - m - c, y_tr),
            QPointF(w - m, y_tr + c),
            QPointF(w - m, y_br - co),
            QPointF(w - m - co, y_br),
            QPointF(m + c, y_bl),
            QPointF(m, y_bl - c),
        ]
    return QPolygonF(pts)


class _AngularFrameCache:
    """Physical-pixel cached painter for pure #000000 angular holographic frames."""

    def __init__(self, side: str, *, tilt_top: float, tilt_bot: float, chamfer: float):
        self.side = side
        self.tilt_top = tilt_top
        self.tilt_bot = tilt_bot
        self.chamfer = chamfer
        self._key = None
        self._image: QImage | None = None

    def paint(self, widget: QWidget, painter: QPainter, accent_hex: str) -> None:
        w, h = widget.width(), widget.height()
        if w <= 1 or h <= 1:
            return
        dpr = max(1.0, float(widget.devicePixelRatioF()))
        accent_norm = (accent_hex or "#ff2034").lower()
        key = (w, h, round(dpr, 2), accent_norm, self.side)
        if self._key != key or self._image is None:
            pw = max(1, math.ceil(w * dpr))
            ph = max(1, math.ceil(h * dpr))
            img = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(Qt.GlobalColor.transparent)

            ip = QPainter(img)
            ip.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            poly = build_angular_polygon(
                w, h, self.side,
                tilt_top=self.tilt_top, tilt_bot=self.tilt_bot, chamfer=self.chamfer,
            )
            path = QPainterPath()
            path.addPolygon(poly)
            path.closeSubpath()

            # Absolute #000000 opaque fill inside the holographic silhouette.
            ip.fillPath(path, QColor(0, 0, 0, 255))

            red = QColor(accent_norm)
            edge = QColor(red)
            edge.setAlpha(155)
            ip.setBrush(Qt.BrushStyle.NoBrush)
            ip.setPen(QPen(edge, 1.25))
            ip.drawPolygon(poly)

            # Subtle brighter accents on the chamfered corners facing the crystal.
            hi = QColor(red)
            hi.setAlpha(235)
            ip.setPen(QPen(hi, 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            pts = [poly.at(i) for i in range(poly.count())]
            if len(pts) == 8:
                ip.drawPolyline(QPolygonF([pts[0], pts[1]]))
                ip.drawPolyline(QPolygonF([pts[2], pts[3]]))
                if self.side == "left":
                    ip.drawPolyline(QPolygonF([pts[4], pts[5]]))
                else:
                    ip.drawPolyline(QPolygonF([pts[6], pts[7]]))
            ip.end()
            self._key = key
            self._image = img

        painter.drawImage(0, 0, self._image)


class VoidMenuButton(QAbstractButton):
    """Straight, crisp horizontal menu item with discrete active highlight."""

    def __init__(self, text: str, side: str = "left", accent=lambda: "#ff2034", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setAccessibleName(text)
        self.setCheckable(True)
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._side = side
        self._accent = accent
        self._hovered = False
        self._badge = False

    def set_badge(self, active: bool) -> None:
        active = bool(active)
        if self._badge != active:
            self._badge = active
            self.update()

    def has_badge(self) -> bool:
        return self._badge

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        w, h = float(self.width()), float(self.height())
        rect = QRectF(1.0, 1.0, max(1.0, w - 2.0), max(1.0, h - 2.0))
        red = QColor(self._accent())
        active = self.isChecked()

        if active:
            fill = QColor(red)
            fill.setAlpha(28)
            border = QColor(red)
            border.setAlpha(150)
            p.setPen(QPen(border, 1.0))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 3.0, 3.0)

            # Discrete directional bar on the inner edge facing the submenu/crystal.
            bar_x = rect.right() - 2.0 if self._side == "left" else rect.left() + 2.0
            p.setPen(QPen(red, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(bar_x, rect.top() + 6.0), QPointF(bar_x, rect.bottom() - 6.0))
        elif self._hovered:
            fill = QColor(red)
            fill.setAlpha(14)
            border = QColor(red)
            border.setAlpha(70)
            p.setPen(QPen(border, 1.0))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 3.0, 3.0)

        font = QFont("Consolas")
        font.setPixelSize(11)
        font.setBold(active)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
        p.setFont(font)
        text_color = QColor("#ffffff") if active else (
            QColor("#ececf4") if self._hovered else QColor("#b4b4c0")
        )
        p.setPen(text_color)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

        if self._badge and not active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(red)
            dot_x = rect.right() - 10.0 if self._side == "left" else rect.left() + 10.0
            p.drawEllipse(QPointF(dot_x, rect.center().y()), 2.6, 2.6)
        p.end()


class VoidCloseButton(QAbstractButton):
    """Discrete vector close button (×) for expanding holographic submenus."""

    def __init__(self, accent=lambda: "#ff2034", parent=None):
        super().__init__(parent)
        self.setText("×")
        self.setAccessibleName("Fechar submenu")
        self.setToolTip("Fechar [Esc]")
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._accent = accent
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        red = QColor(self._accent())
        rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        if self._hovered:
            fill = QColor(red)
            fill.setAlpha(36)
            edge = QColor(red)
            edge.setAlpha(185)
            p.setPen(QPen(edge, 1.0))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 3.0, 3.0)
        ink = QColor("#ffffff") if self._hovered else QColor("#8e8e9c")
        p.setPen(QPen(ink, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy, d = rect.center().x(), rect.center().y(), 4.2
        p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
        p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))
        p.end()


class VoidPrimaryPanel(QWidget):
    """Fixed visible primary side panel (SYSTEM on left, INTERACTION on right)."""

    sectionClicked = pyqtSignal(str)

    def __init__(
        self,
        side: str,
        title: str,
        items: tuple[str, ...],
        accent=lambda: "#ff2034",
        parent=None,
    ):
        super().__init__(parent)
        self.side = side
        self.panel_title = title
        self._items = tuple(items)
        self._accent = accent
        self._active: str | None = None
        self._frame = _AngularFrameCache(side, tilt_top=14.0, tilt_bot=10.0, chamfer=11.0)
        self.setObjectName(f"VoidPrimary_{title}")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(168)
        self.setMaximumWidth(216)
        self.setMinimumHeight(304)
        self.setMaximumHeight(336)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 24, 18, 22)
        layout.setSpacing(8)

        self.title_label = QLabel(title, self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont("Consolas")
        title_font.setPixelSize(14)
        title_font.setBold(True)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.4)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(
            f"color: {self._accent()}; background: transparent; border: none; font-family: 'Consolas';"
        )
        layout.addWidget(self.title_label)
        layout.addSpacing(8)

        self._buttons: dict[str, VoidMenuButton] = {}
        for item in self._items:
            btn = VoidMenuButton(item, side=side, accent=accent, parent=self)
            btn.clicked.connect(lambda _checked=False, name=item: self._on_item_clicked(name))
            self._buttons[item] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

    def items(self) -> tuple[str, ...]:
        return self._items

    def button(self, name: str) -> VoidMenuButton | None:
        return self._buttons.get(name)

    def active_section(self) -> str | None:
        return self._active

    def set_active_section(self, name: str | None) -> None:
        self._active = name if name in self._buttons else None
        for key, btn in self._buttons.items():
            is_sel = key == self._active
            btn.setChecked(is_sel)
            if is_sel:
                btn.set_badge(False)
            btn.update()

    def set_badge(self, name: str, active: bool) -> None:
        btn = self._buttons.get(name)
        if btn is not None:
            if active and self._active == name:
                return
            btn.set_badge(active)

    def refresh_theme(self) -> None:
        self.title_label.setStyleSheet(
            f"color: {self._accent()}; background: transparent; border: none; font-family: 'Consolas';"
        )
        self.update()
        for btn in self._buttons.values():
            btn.update()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(190)
        return hint

    def _on_item_clicked(self, name: str) -> None:
        # Keep checked state governed strictly by submenu open/close truth.
        self.set_active_section(self._active)
        self.sectionClicked.emit(name)

    def paintEvent(self, event):
        p = QPainter(self)
        self._frame.paint(self, p, self._accent())
        p.end()


class _VoidSubmenuSurface(QWidget):
    """Fixed-width inner surface inside VoidSubmenuDrawer's sliding clip viewport."""

    def __init__(self, side: str, accent=lambda: "#ff2034", parent=None):
        super().__init__(parent)
        self._side = side
        self._accent = accent
        self._frame = _AngularFrameCache(side, tilt_top=11.0, tilt_bot=8.0, chamfer=10.0)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QPainter(self)
        self._frame.paint(self, p, self._accent())
        p.end()


class VoidSubmenuDrawer(QWidget):
    """Expanding holographic side submenu (~200 ms slide, pure #000000 interior).

    Uses a clip-viewport container so the inner panel maintains fixed width
    during the 200 ms slide (zero text reflow, zero QImage rebuild per tick,
    and zero HudCanvas layout resize).
    """

    DURATION = 0.20  # 200 ms smooth cubic ease-out transition
    GAP = 8
    MIN_W = 276
    MAX_W = 332
    MAX_H = 448

    sectionChanged = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(
        self,
        side: str,
        title_prefix: str,
        accent=lambda: "#ff2034",
        anchor_panel: QWidget | None = None,
        parent: QWidget | None = None,
        *,
        bottom_clearance: int = 0,
    ):
        super().__init__(parent)
        self.side = side
        self._prefix = title_prefix
        self._accent = accent
        self._anchor = anchor_panel
        self._bottom_clearance = int(bottom_clearance)
        self._hud = None

        self._sections: dict[str, QWidget] = {}
        self._active_section: str | None = None
        self._progress = 0.0
        self._target = 0.0
        self._anim_from = 0.0
        self._anim_start: float | None = None
        self._animating = False
        self._full_width = 296
        self._full_height = 420

        self.setObjectName(f"VoidSubmenuDrawer_{title_prefix}")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._surface = _VoidSubmenuSurface(side, accent=accent, parent=self)
        inner = QVBoxLayout(self._surface)
        inner.setContentsMargins(16, 22, 16, 20)
        inner.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(6)
        self.header_label = QLabel(title_prefix, self._surface)
        hdr_font = QFont("Consolas")
        hdr_font.setPixelSize(11)
        hdr_font.setBold(True)
        hdr_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        self.header_label.setFont(hdr_font)
        self.header_label.setStyleSheet(
            f"color: {self._accent()}; background: transparent; border: none; font-family: 'Consolas';"
        )
        self.close_button = VoidCloseButton(accent=accent, parent=self._surface)
        self.close_button.clicked.connect(lambda: self.close_submenu())
        hdr.addWidget(self.header_label, 1)
        hdr.addWidget(self.close_button, 0)
        inner.addLayout(hdr)

        self._divider = QFrame(self._surface)
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet("background: #380c15; border: none;")
        inner.addWidget(self._divider)

        self.stack = QStackedWidget(self._surface)
        self.stack.setObjectName(f"VoidSubmenuStack_{title_prefix}")
        self.stack.setStyleSheet(
            f"QStackedWidget#VoidSubmenuStack_{title_prefix} {{ background: #000000; border: none; }}"
        )
        inner.addWidget(self.stack, 1)

        if anchor_panel is not None:
            node = anchor_panel
            while node is not None:
                node.installEventFilter(self)
                if node is self.parentWidget():
                    break
                node = node.parentWidget()
        if parent is not None:
            parent.installEventFilter(self)

        self.hide()

    def bind_hud_clock(self, hud) -> None:
        """Drive the 200 ms slide from HudCanvas.pacedFrame without adding a QTimer."""
        if self._hud is hud:
            return
        if self._hud is not None:
            try:
                self._hud.pacedFrame.disconnect(self._on_paced_frame)
            except TypeError:
                pass
        self._hud = hud
        if hud is not None:
            hud.pacedFrame.connect(self._on_paced_frame)

    def add_section(self, name: str, widget: QWidget) -> None:
        widget.setObjectName(f"VoidSection_{self._prefix}_{name}")
        self._sections[name] = widget
        self.stack.addWidget(widget)

    def section_widget(self, name: str) -> QWidget | None:
        return self._sections.get(name)

    def active_section(self) -> str | None:
        return self._active_section

    def is_open(self) -> bool:
        return self._target > 0.5

    def is_animating(self) -> bool:
        return self._animating

    def progress(self) -> float:
        return self._progress

    def full_open_width(self) -> int:
        self._compute_target_metrics()
        return self._full_width

    def toggle_section(self, name: str) -> bool:
        """Open section, switch in place if another is open, or close if re-clicked."""
        if self.is_open() and self._active_section == name:
            self.close_submenu()
            return False
        self.open_section(name)
        return True

    def open_section(self, name: str, *, animate: bool = True) -> None:
        if name not in self._sections:
            return
        already_fully_open = (self.is_open() and not self._animating and self._progress >= 0.999) or (not animate)
        self._active_section = name
        self.header_label.setText(f"{self._prefix}  //  {name}")
        self.stack.setCurrentWidget(self._sections[name])

        if already_fully_open:
            # Reuse the open area immediately without re-running slide animation.
            self._target = 1.0
            self._progress = 1.0
            self._animating = False
            self._anim_start = None
            self.show()
            self.reposition()
            self.raise_()
            self.sectionChanged.emit(name)
            return

        self._target = 1.0
        if self._hud is None:
            self._progress = 1.0
            self._animating = False
            self._anim_start = None
            self.show()
            self.reposition()
            self.raise_()
        else:
            self._anim_from = self._progress
            self._anim_start = None
            self._animating = True
            if self._progress <= 0.001:
                # Start with a 1 px sliver so the widget is visible for the next tick.
                self._progress = 0.01
            self.show()
            self.reposition()
            self.raise_()
        self.sectionChanged.emit(name)

    def close_submenu(self, *, immediate: bool = False) -> None:
        if not self.is_open() and not self._animating and self._progress <= 0.001:
            self._active_section = None
            self.hide()
            return
        self._active_section = None
        self._target = 0.0
        if immediate or self._hud is None:
            self._progress = 0.0
            self._animating = False
            self._anim_start = None
            self.hide()
            self.closed.emit()
            return
        self._anim_from = self._progress
        self._anim_start = None
        self._animating = True
        self.closed.emit()

    def refresh_theme(self) -> None:
        self.header_label.setStyleSheet(
            f"color: {self._accent()}; background: transparent; border: none; font-family: 'Consolas';"
        )
        self._surface.update()
        self.close_button.update()

    def _on_paced_frame(self, now: float) -> None:
        if not self._animating:
            return
        if self._anim_start is None:
            self._anim_start = now
        elapsed = max(0.0, now - self._anim_start)
        t = min(1.0, elapsed / self.DURATION)
        eased = 1.0 - (1.0 - t) ** 3  # Cubic ease-out (~200 ms)
        self._progress = self._anim_from + (self._target - self._anim_from) * eased
        if t >= 1.0:
            self._progress = self._target
            self._animating = False
            self._anim_start = None
            if self._progress <= 0.001:
                self.hide()
                return
        self.reposition()

    def _compute_target_metrics(self) -> tuple[int, int, int, int]:
        parent = self.parentWidget()
        if parent is None:
            return 0, 0, self._full_width, self._full_height
        pw, ph = parent.width(), parent.height()
        desired_w = min(self.MAX_W, max(self.MIN_W, int(pw * 0.24)))

        if self._anchor is not None and self._anchor.width() > 0 and self._anchor.height() > 0:
            tl = parent.mapFromGlobal(self._anchor.mapToGlobal(self._anchor.rect().topLeft()))
            aw, ah = self._anchor.width(), self._anchor.height()
            top = tl.y()
            if self._bottom_clearance > 0:
                avail_h = ph - self._bottom_clearance - top
                height = max(180, min(self.MAX_H, avail_h))
            else:
                height = max(180, ah)
            if self.side == "left":
                anchor_edge = tl.x() + aw + self.GAP
                max_avail = max(160, pw - anchor_edge - 16)
            else:
                anchor_edge = tl.x() - self.GAP
                max_avail = max(160, anchor_edge - 16)
            width = min(desired_w, max_avail)
        else:
            top = 60
            height = max(180, ph - 140)
            width = min(desired_w, max(160, pw - 40))
            anchor_edge = 210 if self.side == "left" else max(210, pw - 210)

        self._full_width = max(120, int(width))
        self._full_height = max(160, int(height))
        return anchor_edge, int(top), self._full_width, self._full_height

    def reposition(self) -> None:
        if self._progress <= 0.0 and not self._animating and not self.is_open():
            if not self.isHidden():
                self.hide()
            return
        anchor_edge, top, full_w, full_h = self._compute_target_metrics()
        vis_w = max(1, int(round(full_w * max(0.0, min(1.0, self._progress)))))

        if self._surface.width() != full_w or self._surface.height() != full_h:
            self._surface.resize(full_w, full_h)

        if self.side == "left":
            # Emerges smoothly to the RIGHT from SYSTEM's inner border.
            self.setGeometry(anchor_edge, top, vis_w, full_h)
            self._surface.move(vis_w - full_w, 0)
        else:
            # Emerges smoothly to the LEFT from INTERACTION's inner border.
            self.setGeometry(anchor_edge - vis_w, top, vis_w, full_h)
            self._surface.move(0, 0)
        if not self.isHidden():
            self.raise_()

    def eventFilter(self, watched, event):
        if watched is not self and event.type() in (
            QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.LayoutRequest
        ):
            if not self.isHidden():
                self.reposition()
        return False
