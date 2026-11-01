"""
ui_plugins_center.py — Holographic Plugin Control Center for ULTRON.

Features:
1. SVG Icon Cache: Pre-renders vector SVGs and image paths to QPixmap, cached by (spec, size, color).
2. Holographic Chamfered Borders: Pre-computes QPainterPath and corner bracket lines on resizeEvent only.
3. Static Texts & Layouts: Pre-instantiates labels and containers; updates text on-demand without layout thrashing.
4. Plugin Card List: Updates only when state, selection, or search/filter changes.
5. Live Permissions: Queries real-time storage without trusting stale cache; instant revocation.
6. Event-Driven: Zero continuous timers or polling loops.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import math
import time
from PyQt6.QtCore import QByteArray, QEvent, QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
)

try:
    from PyQt6.QtSvg import QSvgRenderer
    HAVE_SVG = True
except Exception:
    QSvgRenderer = None
    HAVE_SVG = False

from memory.config_manager import (
    get_plugin_enabled, save_plugin_enabled,
    get_plugin_config, save_plugin_config,
    get_vision_permissions, clear_vision_persistent_permissions,
    add_persistent_capture_scope, add_persistent_send_destination
)
from plugins._smart_vision_permissions import get_shared_permission_manager


# ── SVG Vector Templates & Pre-rendered Cache ────────────────────────────────

_SVG_PRESETS = {
    "eye": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6 14V6H14" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M42 14V6H34" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M6 34V42H14" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M42 34V42H34" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M12 24C16 16 32 16 36 24C32 32 16 32 12 24Z" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="24" cy="24" r="4" fill="{color}"/>
</svg>""",
    "vision": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6 14V6H14" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M42 14V6H34" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M6 34V42H14" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M42 34V42H34" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M12 24C16 16 32 16 36 24C32 32 16 32 12 24Z" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="24" cy="24" r="4" fill="{color}"/>
</svg>""",
    "spotify": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M18 34C18 36.2 16.2 38 14 38C11.8 38 10 36.2 10 34C10 31.8 11.8 30 14 30C15.2 30 16.2 30.5 17 31.3V14L34 10V28C34 30.2 32.2 32 30 32C27.8 32 26 30.2 26 28C26 25.8 27.8 24 30 24C31.2 24 32.2 24.5 33 25.3V13.5L18 17V34Z" fill="{color}"/>
</svg>""",
    "media": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M18 34C18 36.2 16.2 38 14 38C11.8 38 10 36.2 10 34C10 31.8 11.8 30 14 30C15.2 30 16.2 30.5 17 31.3V14L34 10V28C34 30.2 32.2 32 30 32C27.8 32 26 30.2 26 28C26 25.8 27.8 24 30 24C31.2 24 32.2 24.5 33 25.3V13.5L18 17V34Z" fill="{color}"/>
</svg>""",
    "terminal": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M10 14L22 24L10 34" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="26" y1="34" x2="38" y2="34" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
</svg>""",
    "files": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M8 12C8 10.9 8.9 10 10 10H20L24 14H38C39.1 14 40 14.9 40 16V36C40 37.1 39.1 38 38 38H10C8.9 38 8 37.1 8 36V12Z" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="28" cy="28" r="6" stroke="{color}" stroke-width="2"/>
  <line x1="32.5" y1="32.5" x2="38" y2="38" stroke="{color}" stroke-width="2" stroke-linecap="round"/>
</svg>""",
    "generic": """<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
  <polygon points="24,6 40,15 40,33 24,42 8,33 8,15" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="24" cy="24" r="5" stroke="{color}" stroke-width="2"/>
  <line x1="24" y1="6" x2="24" y2="14" stroke="{color}" stroke-width="2"/>
  <line x1="24" y1="34" x2="24" y2="42" stroke="{color}" stroke-width="2"/>
  <line x1="8" y1="24" x2="16" y2="24" stroke="{color}" stroke-width="2"/>
  <line x1="32" y1="24" x2="40" y2="24" stroke="{color}" stroke-width="2"/>
</svg>""",
}

_ICON_CACHE: dict[tuple[str, int, str], QPixmap] = {}


def get_cached_plugin_icon(icon_spec: str, size: int, color_hex: str = "#ff2a4b") -> QPixmap:
    """Retrieve pre-rendered QPixmap from cache or render once from SVG/image."""
    spec = (icon_spec or "").strip().lower()
    key = (spec, size, color_hex.lower())
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    if os.path.isfile(icon_spec):
        if icon_spec.lower().endswith(".svg") and QSvgRenderer is not None:
            renderer = QSvgRenderer(icon_spec)
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
        else:
            raw = QPixmap(icon_spec)
            pm = raw.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        _ICON_CACHE[key] = pm
        return pm

    svg_template = _SVG_PRESETS.get(spec)
    if not svg_template:
        if "vision" in spec or "eye" in spec:
            svg_template = _SVG_PRESETS["eye"]
        elif "spotify" in spec or "music" in spec or "audio" in spec:
            svg_template = _SVG_PRESETS["spotify"]
        elif "term" in spec or "code" in spec or "dev" in spec:
            svg_template = _SVG_PRESETS["terminal"]
        elif "file" in spec or "search" in spec:
            svg_template = _SVG_PRESETS["files"]
        else:
            svg_template = _SVG_PRESETS["generic"]

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    if QSvgRenderer is not None:
        svg_data = svg_template.replace("{color}", color_hex)
        renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
        p = QPainter(pm)
        renderer.render(p)
        p.end()
    else:
        # Fallback vector painter if QSvgRenderer is unavailable
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(color_hex), 1.5))
        p.drawRect(4, 4, size - 8, size - 8)
        p.setFont(QFont("Consolas", size // 4, QFont.Weight.Bold))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, (spec[:2] or "PL").upper())
        p.end()

    _ICON_CACHE[key] = pm
    return pm


# ── Static Font Constants ───────────────────────────────────────────────────

_F_PCC_TITLE = QFont("Consolas", 13, QFont.Weight.Bold)
_F_PCC_SUBTITLE = QFont("Consolas", 8, QFont.Weight.Bold)
_F_PCC_CARD_TITLE = QFont("Consolas", 10, QFont.Weight.Bold)
_F_PCC_CARD_TAG = QFont("Consolas", 7, QFont.Weight.Bold)
_F_PCC_CARD_DESC = QFont("Consolas", 8)
_F_PCC_HEADER_NAME = QFont("Consolas", 15, QFont.Weight.Bold)
_F_PCC_LABEL = QFont("Consolas", 8, QFont.Weight.Bold)
_F_PCC_BODY = QFont("Consolas", 8)


# ── Interactive HUD Widgets ──────────────────────────────────────────────────

class PluginIconWidget(QWidget):
    """Futuristic HUD icon container that draws cached vector icons."""

    def __init__(self, icon_spec: str = "", name: str = "", size: int = 46, selected: bool = False, parent=None):
        super().__init__(parent)
        self.icon_spec = (icon_spec or "").strip().lower()
        self.plugin_name = name or ""
        self.box_size = size
        self.selected = selected
        self._cached_bg_path: Optional[QPainterPath] = None
        self.setFixedSize(size, size)
        self._rebuild_path(size, size)

    def _rebuild_path(self, w: int, h: int):
        self._cached_bg_path = QPainterPath()
        radius = 8.0 if w > 50 else 6.0
        self._cached_bg_path.addRoundedRect(QRectF(1, 1, max(10, w - 2), max(10, h - 2)), radius, radius)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_path(self.width(), self.height())

    def update_spec(self, icon_spec: str = "", name: str = ""):
        self.icon_spec = (icon_spec or "").strip().lower()
        self.plugin_name = name or ""
        self.update()

    def setSelected(self, val: bool):
        if self.selected != val:
            self.selected = val
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor(26, 7, 12, 230) if self.selected else QColor(16, 5, 8, 200)
        border_pen = QPen(QColor("#ff2a4b") if self.selected else QColor("#4a121c"), 1.2)

        if self._cached_bg_path is not None:
            painter.fillPath(self._cached_bg_path, QBrush(bg_color))
            painter.setPen(border_pen)
            painter.drawPath(self._cached_bg_path)

        icon_color = "#ff2a4b" if self.selected else "#ff3b5c"
        pad = 12 if self.box_size > 50 else 8
        icon_dim = max(16, self.box_size - pad * 2)
        pm = get_cached_plugin_icon(self.icon_spec or self.plugin_name, icon_dim, icon_color)
        ox = (self.width() - pm.width()) // 2
        oy = (self.height() - pm.height()) // 2
        painter.drawPixmap(ox, oy, pm)


class ToggleSwitch(QWidget):
    """Sleek neon HUD pill toggle switch."""

    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = bool(checked)
        self._cached_track_path: Optional[QPainterPath] = None
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rebuild_track(40, 22)

    def _rebuild_track(self, w: int, h: int):
        self._cached_track_path = QPainterPath()
        radius = h / 2.0
        self._cached_track_path.addRoundedRect(QRectF(1, 1, max(10, w - 2), max(10, h - 2)), radius, radius)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_track(self.width(), self.height())

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != bool(checked):
            self._checked = bool(checked)
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        if self._checked:
            track_color = QColor("#ff2a4b")
            border_color = QColor("#ff4d6a")
            knob_color = QColor("#ffffff")
            knob_x = w - h + 3
        else:
            track_color = QColor(36, 12, 18)
            border_color = QColor(64, 20, 28)
            knob_color = QColor(100, 32, 44)
            knob_x = 3

        if self._cached_track_path is not None:
            painter.fillPath(self._cached_track_path, QBrush(track_color))
            painter.setPen(QPen(border_color, 1))
            painter.drawPath(self._cached_track_path)

        knob_d = h - 6
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(knob_color))
        painter.drawEllipse(QRectF(knob_x, 3, knob_d, knob_d))


class PluginCardWidget(QWidget):
    """Item card for the Installed Modules list."""

    selected = pyqtSignal(dict)
    toggled = pyqtSignal(str, bool)

    def __init__(self, plugin_data: dict, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.plugin_data = plugin_data
        self.is_selected = is_selected
        self._cached_card_path: Optional[QPainterPath] = None
        self._cached_indicator_rect: Optional[QRectF] = None
        self.setFixedHeight(76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(12)

        # 1. Icon Box
        name = plugin_data.get("name", "")
        icon_spec = plugin_data.get("icon") or ""
        self.icon_widget = PluginIconWidget(icon_spec=icon_spec, name=name, size=46, selected=is_selected, parent=self)
        lay.addWidget(self.icon_widget)

        # 2. Text column
        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        text_lay.setContentsMargins(0, 0, 0, 0)

        # Title
        display_name = name.replace("_", " ").title()
        if display_name.lower() == "smart vision":
            display_name = "Smart Vision"
        elif display_name.lower() == "spotify control":
            display_name = "Spotify"

        self.title_lbl = QLabel(display_name)
        self.title_lbl.setFont(_F_PCC_CARD_TITLE)
        self.title_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        text_lay.addWidget(self.title_lbl)

        # Category / Tags badge
        cat = plugin_data.get("category") or "MODULE"
        tags = plugin_data.get("tags") or []
        tag_str = cat.upper()
        if tags:
            tag_str += " • " + " • ".join(str(t).upper() for t in tags)
        self.cat_lbl = QLabel(tag_str)
        self.cat_lbl.setFont(_F_PCC_CARD_TAG)
        self.cat_lbl.setStyleSheet("color: #ff385c; background: transparent;")
        text_lay.addWidget(self.cat_lbl)

        # Brief description
        desc = (plugin_data.get("description") or "").strip().split(".")[0]
        if len(desc) > 38:
            desc = desc[:35] + "..."
        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setFont(_F_PCC_CARD_DESC)
        self.desc_lbl.setStyleSheet("color: #888898; background: transparent;")
        text_lay.addWidget(self.desc_lbl)

        lay.addLayout(text_lay, stretch=1)

        # 3. Toggle Switch
        is_enabled = bool(plugin_data.get("enabled", False))
        self.switch = ToggleSwitch(checked=is_enabled, parent=self)
        self.switch.toggled.connect(lambda on: self.toggled.emit(name, on))
        lay.addWidget(self.switch, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._rebuild_card_path(self.width(), 76)

    def _rebuild_card_path(self, w: int, h: int):
        self._cached_card_path = QPainterPath()
        self._cached_card_path.addRoundedRect(QRectF(1, 1, max(10, w - 2), h - 2), 6, 6)
        self._cached_indicator_rect = QRectF(1, 10, 3, h - 20)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_card_path(self.width(), self.height())

    def setSelected(self, val: bool):
        if self.is_selected != val:
            self.is_selected = val
            self.icon_widget.setSelected(val)
            self.update()

    def setPluginEnabled(self, val: bool):
        self.plugin_data["enabled"] = bool(val)
        self.switch.setChecked(bool(val))

    def mousePressEvent(self, event):
        self.selected.emit(self.plugin_data)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.is_selected:
            bg_color = QColor(22, 6, 10, 240)
            border_pen = QPen(QColor("#ff2a4b"), 1.2)
        else:
            bg_color = QColor(14, 4, 7, 200)
            border_pen = QPen(QColor("#2d0d14"), 1.0)

        if self._cached_card_path is not None:
            painter.fillPath(self._cached_card_path, QBrush(bg_color))
            painter.setPen(border_pen)
            painter.drawPath(self._cached_card_path)

        if self.is_selected and self._cached_indicator_rect is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#ff2a4b")))
            bar_path = QPainterPath()
            bar_path.addRoundedRect(self._cached_indicator_rect, 1.5, 1.5)
            painter.fillPath(bar_path, QBrush(QColor("#ff2a4b")))


class _ModuleDetailsWidget(QWidget):
    """Right column inspector for the selected module."""

    permissions_changed = pyqtSignal()
    open_settings_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_data = {}
        self._cached_vision_perms: tuple[float, dict] | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            _ModuleDetailsWidget {
                background: rgba(14, 4, 7, 240);
                border: 1px solid #280b12;
                border-radius: 8px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        # ── 1. Header (Icon + Name + Status + Version) ──────────────────────
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(14)

        self._header_icon = PluginIconWidget("", "", size=56, selected=True, parent=self)
        hdr_row.addWidget(self._header_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._title_lbl = QLabel("Module Name")
        self._title_lbl.setFont(_F_PCC_HEADER_NAME)
        self._title_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        title_col.addWidget(self._title_lbl)

        self._status_lbl = QLabel("• ACTIVE MODULE")
        self._status_lbl.setFont(_F_PCC_SUBTITLE)
        self._status_lbl.setStyleSheet("color: #ff2a4b; background: transparent;")
        title_col.addWidget(self._status_lbl)
        hdr_row.addLayout(title_col, stretch=1)

        self._version_lbl = QLabel("v1.0")
        self._version_lbl.setFont(_F_PCC_SUBTITLE)
        self._version_lbl.setStyleSheet("color: #888898; background: transparent;")
        hdr_row.addWidget(self._version_lbl, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(hdr_row)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #240a10; margin: 2px 0;")
        lay.addWidget(sep1)

        # ── 2. ABOUT Section ────────────────────────────────────────────────
        about_lbl = QLabel("ABOUT")
        about_lbl.setFont(_F_PCC_LABEL)
        about_lbl.setStyleSheet("color: #ff2a4b; background: transparent;")
        lay.addWidget(about_lbl)

        self._desc_lbl = QLabel()
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setFont(_F_PCC_BODY)
        self._desc_lbl.setStyleSheet("color: #c8c8d4; background: transparent; line-height: 1.4;")
        lay.addWidget(self._desc_lbl)

        # ── 3. PERMISSIONS Section (Dedicated for Smart Vision) ─────────────
        self._perm_container = QWidget(self)
        perm_lay = QVBoxLayout(self._perm_container)
        perm_lay.setContentsMargins(0, 4, 0, 4)
        perm_lay.setSpacing(10)

        perm_hdr = QLabel("PERMISSIONS")
        perm_hdr.setFont(_F_PCC_LABEL)
        perm_hdr.setStyleSheet("color: #ff2a4b; background: transparent;")
        perm_lay.addWidget(perm_hdr)

        # Row 1: Screen Capture
        row_cap = QHBoxLayout()
        cap_col = QVBoxLayout()
        cap_col.setSpacing(1)
        lbl_cap_title = QLabel("Screen Capture")
        lbl_cap_title.setFont(_F_PCC_CARD_TITLE)
        lbl_cap_title.setStyleSheet("color: #ffffff; background: transparent;")
        lbl_cap_sub = QLabel("Main display")
        lbl_cap_sub.setFont(_F_PCC_CARD_DESC)
        lbl_cap_sub.setStyleSheet("color: #888898; background: transparent;")
        cap_col.addWidget(lbl_cap_title)
        cap_col.addWidget(lbl_cap_sub)
        row_cap.addLayout(cap_col, stretch=1)

        self._pill_cap = QLabel("○  ASK EVERY TIME")
        self._pill_cap.setFont(_F_PCC_LABEL)
        self._pill_cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pill_cap.setFixedHeight(30)
        self._pill_cap.setStyleSheet("""
            QLabel {
                background: rgba(30, 8, 14, 200);
                border: 1px solid #4a1420;
                border-radius: 4px;
                color: #ff3b5c;
                padding: 0 14px;
            }
        """)
        row_cap.addWidget(self._pill_cap)
        perm_lay.addLayout(row_cap)

        # Row 2: AI Transmission
        row_send = QHBoxLayout()
        send_col = QVBoxLayout()
        send_col.setSpacing(1)
        lbl_send_title = QLabel("AI Transmission")
        lbl_send_title.setFont(_F_PCC_CARD_TITLE)
        lbl_send_title.setStyleSheet("color: #ffffff; background: transparent;")
        lbl_send_sub = QLabel("Gemini — authorized destination")
        lbl_send_sub.setFont(_F_PCC_CARD_DESC)
        lbl_send_sub.setStyleSheet("color: #888898; background: transparent;")
        send_col.addWidget(lbl_send_title)
        send_col.addWidget(lbl_send_sub)
        row_send.addLayout(send_col, stretch=1)

        self._pill_send = QLabel("○  ASK EVERY TIME")
        self._pill_send.setFont(_F_PCC_LABEL)
        self._pill_send.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pill_send.setFixedHeight(30)
        self._pill_send.setStyleSheet("""
            QLabel {
                background: rgba(30, 8, 14, 200);
                border: 1px solid #4a1420;
                border-radius: 4px;
                color: #ff3b5c;
                padding: 0 14px;
            }
        """)
        row_send.addWidget(self._pill_send)
        perm_lay.addLayout(row_send)

        # Action Buttons Row: MANAGE PERMISSIONS | REVOKE ACCESS
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._btn_manage = QPushButton("MANAGE PERMISSIONS")
        self._btn_manage.setFixedHeight(34)
        self._btn_manage.setFont(_F_PCC_LABEL)
        self._btn_manage.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_manage.setStyleSheet("""
            QPushButton {
                background: rgba(28, 7, 12, 220);
                color: #ff385c;
                border: 1px solid #ff2a4b;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(80, 16, 26, 240);
                color: #ffffff;
            }
        """)
        self._btn_manage.clicked.connect(self._toggle_always_allow)
        btn_row.addWidget(self._btn_manage)

        self._btn_revoke = QPushButton("REVOKE ACCESS")
        self._btn_revoke.setFixedHeight(34)
        self._btn_revoke.setFont(_F_PCC_LABEL)
        self._btn_revoke.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_revoke.setStyleSheet("""
            QPushButton {
                background: rgba(20, 6, 10, 200);
                color: #a82e3c;
                border: 1px solid #44141e;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ff2a4b;
                border-color: #ff2a4b;
                background: rgba(40, 10, 16, 220);
            }
        """)
        self._btn_revoke.clicked.connect(self._revoke_access)
        btn_row.addWidget(self._btn_revoke)

        perm_lay.addLayout(btn_row)
        lay.addWidget(self._perm_container)

        # ── 4. Standard / Generic Module Status ─────────────────────────────
        self._generic_container = QWidget(self)
        gen_lay = QVBoxLayout(self._generic_container)
        gen_lay.setContentsMargins(0, 4, 0, 4)
        gen_lay.setSpacing(6)

        gen_hdr = QLabel("CONFIGURATION")
        gen_hdr.setFont(_F_PCC_LABEL)
        gen_hdr.setStyleSheet("color: #ff2a4b; background: transparent;")
        gen_lay.addWidget(gen_hdr)

        self._gen_text = QLabel("Standard desktop module. No elevated permissions required.")
        self._gen_text.setFont(_F_PCC_BODY)
        self._gen_text.setStyleSheet("color: #888898; background: transparent;")
        gen_lay.addWidget(self._gen_text)

        self._btn_settings = QPushButton("⚙  CONFIGURE MODULE SETTINGS")
        self._btn_settings.setFixedHeight(34)
        self._btn_settings.setFont(_F_PCC_LABEL)
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.setStyleSheet("""
            QPushButton {
                background: rgba(28, 7, 12, 220);
                color: #ff385c;
                border: 1px solid #ff2a4b;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(80, 16, 26, 240);
                color: #ffffff;
            }
        """)
        self._btn_settings.clicked.connect(lambda: self.open_settings_requested.emit(self.plugin_data.get("name", "")))
        self._btn_settings.setVisible(False)
        gen_lay.addWidget(self._btn_settings)

        lay.addWidget(self._generic_container)

        lay.addStretch(1)

        # ── 5. Footer Status ────────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #240a10; margin: 2px 0;")
        lay.addWidget(sep2)

        footer_row = QHBoxLayout()
        lbl_mod_stat = QLabel("MODULE STATUS")
        lbl_mod_stat.setFont(_F_PCC_LABEL)
        lbl_mod_stat.setStyleSheet("color: #66202c; background: transparent;")
        footer_row.addWidget(lbl_mod_stat)

        footer_row.addStretch(1)

        self._footer_val = QLabel("●  READY")
        self._footer_val.setFont(_F_PCC_LABEL)
        self._footer_val.setStyleSheet("color: #ff2a4b; background: transparent;")
        footer_row.addWidget(self._footer_val)
        lay.addLayout(footer_row)

    def update_module(self, plugin_data: dict):
        self.plugin_data = plugin_data
        name = plugin_data.get("name", "")

        display_name = name.replace("_", " ").title()
        if display_name.lower() == "smart vision":
            display_name = "Smart Vision"
        elif display_name.lower() == "spotify control":
            display_name = "Spotify"

        self._title_lbl.setText(display_name)
        self._version_lbl.setText(plugin_data.get("version", "v1.0"))

        self._header_icon.icon_spec = plugin_data.get("icon") or ""
        self._header_icon.plugin_name = name
        self._header_icon.update()

        is_enabled = bool(plugin_data.get("enabled", False))
        if is_enabled:
            self._status_lbl.setText("• ACTIVE MODULE")
            self._status_lbl.setStyleSheet("color: #ff2a4b; background: transparent;")
            self._footer_val.setText("●  READY")
            self._footer_val.setStyleSheet("color: #ff2a4b; background: transparent;")
        else:
            self._status_lbl.setText("○ INACTIVE MODULE")
            self._status_lbl.setStyleSheet("color: #66202c; background: transparent;")
            self._footer_val.setText("○  DISABLED")
            self._footer_val.setStyleSheet("color: #66202c; background: transparent;")

        self._desc_lbl.setText(plugin_data.get("description", "No description available."))

        if name == "smart_vision":
            self._perm_container.setVisible(True)
            self._generic_container.setVisible(False)
            self.refresh_permissions()
        else:
            self._perm_container.setVisible(False)
            self._generic_container.setVisible(True)
            if plugin_data.get("settings"):
                self._gen_text.setText("Configurable module with dedicated settings schema.")
                self._btn_settings.setVisible(True)
            else:
                self._gen_text.setText("Standard sandboxed integration. Operates within user session boundaries.")
                self._btn_settings.setVisible(False)

    def refresh_permissions(self):
        """Query real live permissions without trusting old cached state."""
        try:
            perms = get_vision_permissions()
            pm = get_shared_permission_manager()
            cap_scopes = set(perms.get("capture_scopes", []))
            send_dests = set(perms.get("send_destinations", []))

            # Screen Capture state
            if "screen:screen" in cap_scopes:
                self._pill_cap.setText("●  ALWAYS ALLOW")
                self._pill_cap.setStyleSheet("QLabel { background: rgba(30, 8, 14, 200); border: 1px solid #ff2a4b; border-radius: 4px; color: #ff2a4b; padding: 0 14px; }")
            elif pm.has_capture_permission("screen", "screen"):
                self._pill_cap.setText("●  SESSION ALLOW")
                self._pill_cap.setStyleSheet("QLabel { background: rgba(30, 8, 14, 200); border: 1px solid #ff6680; border-radius: 4px; color: #ff6680; padding: 0 14px; }")
            else:
                self._pill_cap.setText("○  ASK EVERY TIME")
                self._pill_cap.setStyleSheet("QLabel { background: rgba(20, 6, 10, 200); border: 1px solid #44141e; border-radius: 4px; color: #772836; padding: 0 14px; }")

            # AI Transmission state
            if "gemini-2.5-flash" in send_dests or bool(send_dests):
                self._pill_send.setText("●  ALWAYS ALLOW")
                self._pill_send.setStyleSheet("QLabel { background: rgba(30, 8, 14, 200); border: 1px solid #ff2a4b; border-radius: 4px; color: #ff2a4b; padding: 0 14px; }")
            elif pm.has_send_permission("gemini-2.5-flash"):
                self._pill_send.setText("●  SESSION ALLOW")
                self._pill_send.setStyleSheet("QLabel { background: rgba(30, 8, 14, 200); border: 1px solid #ff6680; border-radius: 4px; color: #ff6680; padding: 0 14px; }")
            else:
                self._pill_send.setText("○  ASK EVERY TIME")
                self._pill_send.setStyleSheet("QLabel { background: rgba(20, 6, 10, 200); border: 1px solid #44141e; border-radius: 4px; color: #772836; padding: 0 14px; }")
        except Exception:
            pass

    def _toggle_always_allow(self):
        try:
            perms = get_vision_permissions()
            if "screen:screen" in perms.get("capture_scopes", []):
                clear_vision_persistent_permissions()
            else:
                add_persistent_capture_scope("screen:screen")
                add_persistent_send_destination("gemini-2.5-flash")
            self.refresh_permissions()
            self.permissions_changed.emit()
        except Exception:
            pass

    def _revoke_access(self):
        try:
            clear_vision_persistent_permissions()
            pm = get_shared_permission_manager()
            pm.revoke_all(clear_persistent=True)
            self.refresh_permissions()
            self.permissions_changed.emit()
        except Exception:
            pass


class _ModuleSettingsWidget(QWidget):
    """Dynamic settings form editor placed inside the SELECTED MODULE column."""

    back_requested = pyqtSignal()
    saved = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_data: dict = {}
        self._inputs: dict[str, tuple[QWidget, str]] = {}
        self._namespace: str = ""

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            _ModuleSettingsWidget {
                background: rgba(14, 4, 7, 240);
                border: 1px solid #280b12;
                border-radius: 8px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        # 1. Back link
        self._back_btn = QPushButton("‹  BACK TO MODULE DETAILS")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #ff3b5c;
                font: bold 9px 'Consolas';
                text-align: left;
                padding: 0;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        self._back_btn.clicked.connect(self.back_requested.emit)
        lay.addWidget(self._back_btn)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #240a10; margin: 2px 0;")
        lay.addWidget(sep1)

        # 2. Header
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(2)
        self._title_lbl = QLabel("Settings")
        self._title_lbl.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet("color: #ff2a4b; background: transparent;")
        hdr_col.addWidget(self._title_lbl)

        self._subtitle_lbl = QLabel("CONFIGURATION")
        self._subtitle_lbl.setFont(_F_PCC_SUBTITLE)
        self._subtitle_lbl.setStyleSheet("color: #8c2434; background: transparent; letter-spacing: 1px;")
        hdr_col.addWidget(self._subtitle_lbl)
        lay.addLayout(hdr_col)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #240a10; margin: 2px 0;")
        lay.addWidget(sep2)

        # 3. Dynamic Form in Scroll Area (strictly NO horizontal scrollbar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #44141e;
                min-height: 24px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #ff2a4b;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._form_container = QWidget()
        self._form_container.setStyleSheet("background: transparent;")
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setContentsMargins(0, 4, 4, 4)
        self._form_layout.setSpacing(12)

        scroll.setWidget(self._form_container)
        lay.addWidget(scroll, stretch=1)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("color: #240a10; margin: 2px 0;")
        lay.addWidget(sep3)

        # 4. Footer & Action Buttons
        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)

        self._hint_lbl = QLabel("CHANGES APPLY ONLY AFTER SAVING")
        self._hint_lbl.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        self._hint_lbl.setStyleSheet("color: #551622; background: transparent;")
        footer_row.addWidget(self._hint_lbl, stretch=1)

        self._btn_cancel = QPushButton("CANCEL")
        self._btn_cancel.setFixedHeight(32)
        self._btn_cancel.setFixedWidth(80)
        self._btn_cancel.setFont(_F_PCC_LABEL)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(20, 6, 10, 200);
                color: #a82e3c;
                border: 1px solid #44141e;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ff2a4b;
                border-color: #ff2a4b;
                background: rgba(40, 10, 16, 220);
            }
        """)
        self._btn_cancel.clicked.connect(self.back_requested.emit)
        footer_row.addWidget(self._btn_cancel)

        self._btn_save = QPushButton("SAVE")
        self._btn_save.setFixedHeight(32)
        self._btn_save.setFixedWidth(90)
        self._btn_save.setFont(_F_PCC_LABEL)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setStyleSheet("""
            QPushButton {
                background: rgba(36, 10, 16, 230);
                color: #ffffff;
                border: 1px solid #ff2a4b;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(80, 16, 26, 250);
                border-color: #ff4d6a;
            }
        """)
        self._btn_save.clicked.connect(self._on_save_clicked)
        footer_row.addWidget(self._btn_save)

        lay.addLayout(footer_row)

    def load_schema(self, plugin_data: dict):
        self.plugin_data = plugin_data
        settings = plugin_data.get("settings") or {}
        self._namespace = settings.get("namespace") or plugin_data.get("name") or ""
        title = settings.get("title") or plugin_data.get("name", "").replace("_", " ").title()
        self._title_lbl.setText(f"{title} Settings")

        cat = plugin_data.get("category") or "CONFIGURATION"
        self._subtitle_lbl.setText(f"{cat.upper()} / CONFIGURATION")
        self._btn_save.setText("SAVE")

        # Clear existing dynamic fields
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        self._inputs.clear()
        values = get_plugin_config(self._namespace)
        fields = settings.get("fields") or []

        for f in fields:
            key = f.get("key")
            if not key:
                continue
            label_text = f.get("label") or key.replace("_", " ").title()
            hint_text = f.get("hint") or ""
            ftype = (f.get("type") or "text").lower()
            default = f.get("default")
            curr_val = values.get(key, default)

            field_box = QVBoxLayout()
            field_box.setSpacing(3)

            # Label on top
            lbl_w = QLabel(label_text)
            lbl_w.setFont(_F_PCC_CARD_TITLE)
            lbl_w.setStyleSheet("color: #ffffff; background: transparent;")
            field_box.addWidget(lbl_w)

            # Hint directly below label
            if hint_text:
                hint_w = QLabel(hint_text)
                hint_w.setFont(_F_PCC_CARD_DESC)
                hint_w.setStyleSheet("color: #888898; background: transparent;")
                hint_w.setWordWrap(True)
                field_box.addWidget(hint_w)

            # Input widget
            if ftype == "password":
                inp_row = QHBoxLayout()
                inp_row.setSpacing(6)

                inp = QLineEdit("" if curr_val is None else str(curr_val))
                inp.setEchoMode(QLineEdit.EchoMode.Password)
                inp.setFixedHeight(34)
                inp.setFont(_F_PCC_BODY)
                inp.setStyleSheet("""
                    QLineEdit {
                        background: rgba(18, 5, 8, 240);
                        border: 1px solid #361018;
                        border-radius: 4px;
                        color: #ffffff;
                        padding: 0 10px;
                        selection-background-color: #ff2a4b;
                    }
                    QLineEdit:focus { border-color: #ff2a4b; }
                """)
                inp_row.addWidget(inp, stretch=1)

                show_btn = QPushButton("SHOW")
                show_btn.setFixedSize(60, 34)
                show_btn.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                show_btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(24, 7, 12, 220);
                        color: #888898;
                        border: 1px solid #361018;
                        border-radius: 4px;
                    }
                    QPushButton:hover { color: #ffffff; border-color: #ff2a4b; }
                """)

                def _toggle_pw(checked=False, b=show_btn, line=inp):
                    if line.echoMode() == QLineEdit.EchoMode.Password:
                        line.setEchoMode(QLineEdit.EchoMode.Normal)
                        b.setText("HIDE")
                    else:
                        line.setEchoMode(QLineEdit.EchoMode.Password)
                        b.setText("SHOW")

                show_btn.clicked.connect(_toggle_pw)
                inp_row.addWidget(show_btn)

                field_box.addLayout(inp_row)
                self._inputs[key] = (inp, "password")
            elif ftype == "toggle":
                sw = ToggleSwitch(checked=bool(curr_val))
                field_box.addWidget(sw, alignment=Qt.AlignmentFlag.AlignLeft)
                self._inputs[key] = (sw, "toggle")
            elif ftype == "choice":
                combo = QComboBox()
                combo.setFixedHeight(34)
                combo.setFont(_F_PCC_BODY)
                combo.setStyleSheet("""
                    QComboBox {
                        background: rgba(18, 5, 8, 240);
                        border: 1px solid #361018;
                        border-radius: 4px;
                        color: #ffffff;
                        padding: 0 10px;
                    }
                    QComboBox QAbstractItemView {
                        background: #120508;
                        color: #ffffff;
                        selection-background-color: #361018;
                    }
                """)
                for opt in f.get("options", []):
                    combo.addItem(str(opt))
                if curr_val is not None:
                    combo.setCurrentText(str(curr_val))
                field_box.addWidget(combo)
                self._inputs[key] = (combo, "choice")
            else:
                inp = QLineEdit("" if curr_val is None else str(curr_val))
                inp.setFixedHeight(34)
                inp.setFont(_F_PCC_BODY)
                inp.setStyleSheet("""
                    QLineEdit {
                        background: rgba(18, 5, 8, 240);
                        border: 1px solid #361018;
                        border-radius: 4px;
                        color: #ffffff;
                        padding: 0 10px;
                        selection-background-color: #ff2a4b;
                    }
                    QLineEdit:focus { border-color: #ff2a4b; }
                """)
                if f.get("placeholder"):
                    inp.setPlaceholderText(str(f["placeholder"]))
                field_box.addWidget(inp)
                self._inputs[key] = (inp, "text")

            self._form_layout.addLayout(field_box)

        self._form_layout.addStretch(1)

    def _on_save_clicked(self):
        vals = {}
        for key, (w, ftype) in self._inputs.items():
            if ftype == "toggle":
                vals[key] = w.isChecked()
            elif ftype == "choice":
                vals[key] = w.currentText()
            else:
                vals[key] = w.text().strip()
        save_plugin_config(self._namespace, vals)
        self._btn_save.setText("SAVED ✓")
        self.saved.emit(self._namespace, vals)


class _PluginManagerSurface(QWidget):
    """Futuristic holographic Plugin Control Center modal."""

    closed = pyqtSignal()
    open_settings = pyqtSignal(str)

    _OW = 840
    _OH = 560

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self._raw_plugins = list(plugins)
        self._current_filter = "ALL"
        self._search_text = ""
        self._card_widgets: dict[str, PluginCardWidget] = {}
        self._selected_card: Optional[PluginCardWidget] = None

        self._cached_frame_path: Optional[QPainterPath] = None
        self._cached_bracket_lines: list[QLineF] = []

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMinimumSize(600, 400)
        self.resize(self._OW, self._OH)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(20, 16, 20, 16)
        main_lay.setSpacing(12)

        # ── 1. Header (Title + Breadcrumbs + Close Button) ──────────────────
        hdr_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        hdr_lbl = QLabel("PLUGIN CONTROL CENTER")
        hdr_lbl.setFont(_F_PCC_TITLE)
        hdr_lbl.setStyleSheet("color: #ff2a4b; background: transparent; letter-spacing: 1px;")
        title_col.addWidget(hdr_lbl)

        self._sub_lbl = QLabel("SYSTEM / PLUGINS / CONFIGURATION")
        self._sub_lbl.setFont(_F_PCC_SUBTITLE)
        self._sub_lbl.setStyleSheet("color: #77202e; background: transparent; letter-spacing: 1px;")
        title_col.addWidget(self._sub_lbl)
        hdr_row.addLayout(title_col, stretch=1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8c2434;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: rgba(255, 42, 75, 40);
            }
        """)
        close_btn.clicked.connect(self.closed.emit)
        hdr_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        main_lay.addLayout(hdr_row)

        # ── 2. Top Action Bar (Search + Segmented Filter + Counter) ──────────
        act_row = QHBoxLayout()
        act_row.setSpacing(12)

        # Search Bar
        self._search_input = QLineEdit()
        self._search_input.setFixedHeight(32)
        self._search_input.setFixedWidth(280)
        self._search_input.setFont(_F_PCC_BODY)
        self._search_input.setPlaceholderText("🔍  Search plugins...")
        self._search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(18, 5, 8, 240);
                border: 1px solid #361018;
                border-radius: 6px;
                color: #ffffff;
                padding-left: 10px;
                selection-background-color: #ff2a4b;
            }
            QLineEdit:focus {
                border-color: #ff2a4b;
            }
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        act_row.addWidget(self._search_input)

        # Segmented Filter Buttons (ALL, ENABLED, DISABLED)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        self._filter_all = QPushButton("ALL")
        self._filter_enabled = QPushButton("ENABLED")
        self._filter_disabled = QPushButton("DISABLED")

        for i, btn in enumerate([self._filter_all, self._filter_enabled, self._filter_disabled]):
            btn.setFixedHeight(30)
            btn.setFixedWidth(80)
            btn.setFont(_F_PCC_LABEL)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_group.addButton(btn, i)

        self._filter_all.setChecked(True)
        self._apply_filter_styles()
        self._btn_group.idClicked.connect(self._on_filter_clicked)

        filter_box = QHBoxLayout()
        filter_box.setSpacing(4)
        filter_box.addWidget(self._filter_all)
        filter_box.addWidget(self._filter_enabled)
        filter_box.addWidget(self._filter_disabled)
        act_row.addLayout(filter_box)

        act_row.addStretch(1)

        # Counter Label
        self._count_lbl = QLabel(f"{len(plugins):02d} PLUGINS")
        self._count_lbl.setFont(_F_PCC_LABEL)
        self._count_lbl.setStyleSheet("color: #772432; background: transparent;")
        act_row.addWidget(self._count_lbl)
        main_lay.addLayout(act_row)

        # ── 3. Two-Column Body Layout ───────────────────────────────────────
        cols_lay = QHBoxLayout()
        cols_lay.setSpacing(16)

        # Left Column: INSTALLED MODULES
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        left_hdr = QHBoxLayout()
        lbl_inst = QLabel("INSTALLED MODULES")
        lbl_inst.setFont(_F_PCC_LABEL)
        lbl_inst.setStyleSheet("color: #8c2434; background: transparent;")
        left_hdr.addWidget(lbl_inst)

        left_hdr.addStretch(1)

        lbl_scroll = QLabel("SCROLL ↓")
        lbl_scroll.setFont(_F_PCC_CARD_TAG)
        lbl_scroll.setStyleSheet("color: #551622; background: transparent;")
        left_hdr.addWidget(lbl_scroll)
        left_col.addLayout(left_hdr)

        # Scroll Area for Cards (strictly NO horizontal scrollbar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #44141e;
                min-height: 24px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #882434;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        cards_container = QWidget()
        cards_container.setStyleSheet("background: transparent;")
        self._cards_container = cards_container
        self._cards_layout = QVBoxLayout(cards_container)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(8)

        # Instantiate cards once
        first_card = None
        for p in plugins:
            card = PluginCardWidget(p, parent=cards_container)
            card.selected.connect(self._on_card_selected)
            card.toggled.connect(self._on_card_toggled)
            self._cards_layout.addWidget(card)
            self._card_widgets[p["name"]] = card
            if first_card is None:
                first_card = card

        self._cards_layout.addStretch(1)
        scroll.setWidget(cards_container)
        left_col.addWidget(scroll)
        cols_lay.addLayout(left_col, stretch=4)

        # Right Column: SELECTED MODULE (houses in-place details & settings)
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        lbl_sel = QLabel("SELECTED MODULE")
        lbl_sel.setFont(_F_PCC_LABEL)
        lbl_sel.setStyleSheet("color: #8c2434; background: transparent;")
        right_col.addWidget(lbl_sel)

        self._right_stack = QStackedWidget(self)
        self._right_stack.setStyleSheet("background: transparent; border: none;")
        self._details_widget = _ModuleDetailsWidget(self)
        self._settings_widget = _ModuleSettingsWidget(self)

        self._details_widget.open_settings_requested.connect(self._show_settings_for_module)
        self._settings_widget.back_requested.connect(self._show_details_view)
        self._settings_widget.saved.connect(self._on_settings_saved)

        self._right_stack.addWidget(self._details_widget)
        self._right_stack.addWidget(self._settings_widget)
        right_col.addWidget(self._right_stack)
        cols_lay.addLayout(right_col, stretch=5)

        main_lay.addLayout(cols_lay, stretch=1)

        # Initialize selection
        if first_card:
            self._on_card_selected(first_card.plugin_data)

        self._rebuild_holographic_paths(self._OW, self._OH)

    def _rebuild_holographic_paths(self, w: int, h: int):
        """Pre-render chamfered polygon and bracket lines into a cached QImage for instantaneous paintEvent."""
        if w <= 1 or h <= 1:
            return
        dpr = max(1.0, float(self.devicePixelRatioF()))
        pw = max(1, math.ceil(w * dpr))
        ph = max(1, math.ceil(h * dpr))
        img = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)

        c = 18.0
        b_len = 22.0

        path = QPainterPath()
        path.moveTo(c, 0)
        path.lineTo(w - c, 0)
        path.lineTo(w, c)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(c, h)
        path.lineTo(0, h - c)
        path.lineTo(0, c)
        path.closeSubpath()

        ip = QPainter(img)
        ip.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ip.fillPath(path, QColor(0, 0, 0, 255))
        ip.setPen(QPen(QColor("#7a1622"), 1.0))
        ip.drawPath(path)

        bracket_lines = [
            QLineF(c, 0, c + b_len, 0),
            QLineF(0, c, 0, c + b_len),
            QLineF(w - c - b_len, 0, w - c, 0),
            QLineF(w, c, w, c + b_len),
            QLineF(0, h - c - b_len, 0, h - c),
            QLineF(c, h, c + b_len, h),
            QLineF(w - c - b_len, h, w - c, h),
            QLineF(w, h - c - b_len, w, h - c),
        ]
        ip.setPen(QPen(QColor("#ff2a4b"), 2.0))
        ip.drawLines(bracket_lines)
        ip.end()

        self._cached_bracket_lines = bracket_lines
        self._cached_frame_path = path
        self._cached_frame_image = img

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_holographic_paths(self.width(), self.height())

    def paintEvent(self, event):
        if getattr(self, "_cached_frame_image", None) is not None:
            painter = QPainter(self)
            painter.drawImage(0, 0, self._cached_frame_image)
            painter.end()

    def _apply_filter_styles(self):
        active_ss = """
            QPushButton {
                background: rgba(90, 18, 28, 230);
                color: #ffffff;
                border: 1px solid #ff2a4b;
                border-radius: 4px;
            }
        """
        inactive_ss = """
            QPushButton {
                background: rgba(20, 6, 10, 200);
                color: #772635;
                border: 1px solid #2e0c14;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #ff6680;
                border-color: #661825;
            }
        """
        self._filter_all.setStyleSheet(active_ss if self._current_filter == "ALL" else inactive_ss)
        self._filter_enabled.setStyleSheet(active_ss if self._current_filter == "ENABLED" else inactive_ss)
        self._filter_disabled.setStyleSheet(active_ss if self._current_filter == "DISABLED" else inactive_ss)

    def _on_filter_clicked(self, btn_id: int):
        modes = {0: "ALL", 1: "ENABLED", 2: "DISABLED"}
        self._current_filter = modes.get(btn_id, "ALL")
        self._apply_filter_styles()
        self._update_card_visibility()

    def _on_search_changed(self, text: str):
        self._search_text = (text or "").strip().lower()
        self._update_card_visibility()

    def refresh_plugins(self, plugins: list[dict]):
        self._raw_plugins = list(plugins)
        for p in plugins:
            name = p.get("name", "")
            if name in self._card_widgets:
                card = self._card_widgets[name]
                card.plugin_data = p
                card.setPluginEnabled(bool(p.get("enabled", True)))
            elif hasattr(self, "_cards_container"):
                card = PluginCardWidget(p, parent=self._cards_container)
                card.selected.connect(self._on_card_selected)
                card.toggled.connect(self._on_card_toggled)
                self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
                self._card_widgets[name] = card
        self._update_card_visibility()

    def _update_card_visibility(self):
        visible_count = 0
        for name, card in self._card_widgets.items():
            p = card.plugin_data
            matches_filter = (
                self._current_filter == "ALL"
                or (self._current_filter == "ENABLED" and p.get("enabled", True))
                or (self._current_filter == "DISABLED" and not p.get("enabled", True))
            )
            matches_search = (
                not self._search_text
                or self._search_text in p.get("name", "").lower()
                or self._search_text in p.get("description", "").lower()
                or self._search_text in p.get("category", "").lower()
            )
            is_vis = matches_filter and matches_search
            card.setVisible(is_vis)
            if is_vis:
                visible_count += 1

        self._count_lbl.setText(f"{visible_count:02d} PLUGINS")

    def _on_card_selected(self, p: dict):
        name = p.get("name", "")
        for n, card in self._card_widgets.items():
            card.setSelected(n == name)
        self._details_widget.update_module(p)
        self._right_stack.setCurrentIndex(0)

    def _show_settings_for_module(self, name: str):
        found = None
        target = (name or "").strip().lower()
        for p in self._raw_plugins:
            p_name = str(p.get("name", "")).strip().lower()
            ns = str((p.get("settings") or {}).get("namespace") or p.get("name", "")).strip().lower()
            if p_name == target or ns == target:
                found = p
                break
        if not found:
            found = self._details_widget.plugin_data

        if found:
            self._settings_widget.load_schema(found)
            self._right_stack.setCurrentIndex(1)
            self.open_settings.emit(found.get("name", name))

    def _show_details_view(self):
        self._right_stack.setCurrentIndex(0)

    def show_settings(self, target_ns: str = ""):
        """External entry point: opens settings view inside the SELECTED MODULE column."""
        target = (target_ns or "").strip().lower()
        if target:
            for p in self._raw_plugins:
                p_name = str(p.get("name", "")).strip().lower()
                ns = str((p.get("settings") or {}).get("namespace") or p.get("name", "")).strip().lower()
                if p_name == target or ns == target:
                    self._on_card_selected(p)
                    self._show_settings_for_module(p.get("name", ""))
                    return
        if self._details_widget.plugin_data:
            self._show_settings_for_module(self._details_widget.plugin_data.get("name", ""))

    def _on_settings_saved(self, namespace: str, values: dict):
        self._right_stack.setCurrentIndex(0)
        self.open_settings.emit(namespace)

    def _on_card_toggled(self, name: str, enabled: bool):
        save_plugin_enabled(name, enabled)
        card = self._card_widgets.get(name)
        if card:
            card.setPluginEnabled(enabled)
            if self._details_widget.plugin_data.get("name") == name:
                self._details_widget.update_module(card.plugin_data)
        self._update_card_visibility()

    def hideEvent(self, event):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        self.closed.emit()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._right_stack.currentIndex() == 1:
                self._show_details_view()
                event.accept()
                return
            self.closed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class PluginManagerOverlay(QWidget):
    """Expanding holographic Plugin Control Center modal (~200 ms smooth slide animation).

    Uses a clip-viewport container so the inner panel maintains fixed width
    during the 200 ms cubic ease-out slide (zero text reflow, zero QPixmap rebuild,
    and zero layout thrashing). Synchronized to HudCanvas.pacedFrame.
    """

    DURATION = 0.20  # 200 ms smooth cubic ease-out transition
    _OW = 840
    _OH = 560

    closed = pyqtSignal()
    open_settings = pyqtSignal(str)

    def __init__(self, plugins: list[dict], anchor_panel: QWidget | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._anchor = anchor_panel
        self._hud = None
        self._progress = 0.0
        self._target = 0.0
        self._anim_from = 0.0
        self._anim_start: float | None = None
        self._animating = False
        self._full_width = self._OW
        self._full_height = self._OH
        self._cached_metrics: tuple[int, int, int, int] | None = None

        self.setObjectName("PluginManagerOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._surface = _PluginManagerSurface(plugins, parent=self)
        self._surface.closed.connect(self.close_drawer)
        self._surface.open_settings.connect(self.open_settings)

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
        """Drive the 200 ms slide from HudCanvas.pacedFrame without adding rogue QTimers."""
        if self._hud is hud:
            return
        if self._hud is not None:
            try:
                self._hud.pacedFrame.disconnect(self._on_paced_frame)
            except (TypeError, RuntimeError):
                pass
        self._hud = hud
        if hud is not None:
            hud.pacedFrame.connect(self._on_paced_frame)

    def refresh_plugins(self, plugins: list[dict]) -> None:
        self._surface.refresh_plugins(plugins)

    def is_open(self) -> bool:
        return self._target > 0.5 or (self._progress > 0.01 and not self.isHidden())

    def _invalidate_metrics(self) -> None:
        self._cached_metrics = None

    def _get_metrics(self) -> tuple[int, int, int, int]:
        if self._cached_metrics is None:
            self._cached_metrics = self._compute_metrics()
        return self._cached_metrics

    def open_drawer(self, *, animate: bool = True) -> None:
        self._target = 1.0
        self._invalidate_metrics()
        if not animate or self._hud is None:
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
                self._progress = 0.01
            self.show()
            self.reposition()
            self.raise_()

    def close_drawer(self, *, immediate: bool = False) -> None:
        if not self.is_open() and not self._animating and self._progress <= 0.001:
            self.hide()
            self.closed.emit()
            return
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

    def _compute_metrics(self) -> tuple[int, int, int, int]:
        parent = self.parentWidget()
        if parent is None:
            return 204, 60, self._OW, self._OH
        pw, ph = parent.width(), parent.height()

        if self._anchor is not None and self._anchor.width() > 0 and self._anchor.height() > 0:
            tl = parent.mapFromGlobal(self._anchor.mapToGlobal(self._anchor.rect().topLeft()))
            left_x = tl.x() + self._anchor.width() + 8
            top_y = tl.y()
        else:
            left_x = 204
            top_y = 60

        avail_w = max(360, pw - left_x - 14)
        full_w = min(self._OW, avail_w)
        avail_h = max(360, ph - top_y - 74)
        full_h = min(self._OH, avail_h)
        self._full_width = full_w
        self._full_height = full_h
        return left_x, top_y, full_w, full_h

    def reposition(self) -> None:
        if self._progress <= 0.0 and not self._animating and not self.is_open():
            if not self.isHidden():
                self.hide()
            return
        left_x, top_y, full_w, full_h = self._get_metrics()
        vis_w = max(1, int(round(full_w * max(0.0, min(1.0, self._progress)))))

        if self._surface.width() != full_w or self._surface.height() != full_h:
            self._surface.resize(full_w, full_h)

        self.setGeometry(left_x, top_y, vis_w, full_h)
        self._surface.move(vis_w - full_w, 0)
        # Note: self.raise_() is only called in open_drawer(), never on 60 FPS animation ticks

    def show_settings(self, target_ns: str = ""):
        self._surface.show_settings(target_ns)

    def eventFilter(self, watched, event):
        if watched is not self and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._invalidate_metrics()
            if not self.isHidden():
                self.reposition()
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._invalidate_metrics()
        if hasattr(self, "_surface") and self._surface is not None and not self._animating:
            self._surface.resize(event.size())

    def keyPressEvent(self, event):
        self._surface.keyPressEvent(event)

    def __getattr__(self, name: str):
        surface = self.__dict__.get('_surface')
        if surface is not None and hasattr(surface, name):
            return getattr(surface, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
