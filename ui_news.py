"""Painel gráfico NEWS DRAWER (DAILY BRIEFING): octógono chanfrado #000000 retrátil.

Sem timers: eventos do Qt reposicionam o overlay e a rolagem é a do QScrollArea.
"""
import re

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

COLLAPSED_ROWS = 2
_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
_SOURCE_RE = re.compile(r"^(.*?)\s*\[([^\[\]]+)\]\s*$")


def parse_news_text(text):
    """Extrai itens do texto de `web_search._format_news`.

    Retorna [] quando o texto não segue esse formato (ex.: resposta livre do
    Gemini); o chamador deve então usar o painel de texto tradicional.
    """
    items, current = [], None
    for line in str(text or "").splitlines():
        match = _ITEM_RE.match(line)
        if match and not line.startswith("   "):
            title = match.group(2)
            source = ""
            src = _SOURCE_RE.match(title)
            if src:
                title, source = src.group(1).strip(), src.group(2).strip()
            current = {"title": title, "snippet": "", "source": source, "url": ""}
            items.append(current)
        elif current is not None and line.strip():
            value = line.strip()
            if value.lower().startswith(("http://", "https://")):
                current["url"] = value
            elif not current["snippet"]:
                current["snippet"] = value
    return [i for i in items if i["title"]]


class _ElideLabel(QLabel):
    """Linha única com reticências; não força largura mínima ao layout."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setToolTip(text)

    def set_full_text(self, text):
        self._full = text
        self.setToolTip(text)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self.palette().windowText().color())
        shown = QFontMetrics(self.font()).elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(1, self.width()))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
        p.end()


class _ModernButton(QPushButton):
    """Botão pintado: retângulo angular com seta (alternar) ou X (fechar)."""

    def __init__(self, kind, accent, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._accent = accent
        self._label = ""
        self._open = False
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if kind == "close":
            self.setFixedSize(22, 22)
        else:
            self.setFixedHeight(22)

    def set_state(self, label, opened):
        self._label, self._open = label, opened
        if self._kind != "close":
            width = QFontMetrics(self._font()).horizontalAdvance(label) + 34
            self.setFixedWidth(width)
        self.update()

    def _font(self):
        font = QFont("Consolas")
        font.setPixelSize(10)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        return font

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        red = QColor(self._accent())
        fill = QColor(red)
        fill.setAlpha(42 if self._hover else 14)
        edge = QColor(red)
        edge.setAlpha(220 if self._hover else 125)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(edge, 1.0))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 3.0, 3.0)
        ink = QColor("#ffffff") if self._hover else QColor("#d6d6dc")
        p.setPen(QPen(ink, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = rect.center().x(), rect.center().y()
        if self._kind == "close":
            d = 3.8
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))
        else:
            p.setFont(self._font())
            text_rect = QRectF(rect.left() + 9, rect.top(), rect.width() - 24, rect.height())
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self._label)
            ax, ay = rect.right() - 11, cy
            tip = -2.0 if self._open else 2.0
            p.drawPolyline(QPolygonF([
                QPointF(ax - 3.5, ay - tip), QPointF(ax, ay + tip), QPointF(ax + 3.5, ay - tip)]))
        p.end()


class _NewsRow(QWidget):
    def __init__(self, number, item, accent, parent=None):
        super().__init__(parent)
        self.setObjectName("NewsRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 4, 3, 4)
        lay.setSpacing(10)
        num = QLabel(f"{number:02d}", self)
        num.setFixedWidth(22)
        num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        num.setStyleSheet(f"color: {accent}; font: 11px Consolas; background: transparent;")
        lay.addWidget(num)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = _ElideLabel(item["title"], self)
        self.title.setFixedHeight(16)
        self.title.setStyleSheet("color: #f2f2f6; font: 12px Consolas; background: transparent;")
        col.addWidget(self.title)
        self.sub = _ElideLabel(item["snippet"] or item["source"], self)
        self.sub.setFixedHeight(14)
        self.sub.setStyleSheet("color: #8d8d96; font: 10px Consolas; background: transparent;")
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.setStyleSheet("QWidget#NewsRow { background: #000000; border-bottom: 1px solid #2b0a10; }")
        self.set_compact(True)

    def set_compact(self, compact):
        self.sub.setVisible(not compact and bool(self.sub._full))
        self.setFixedHeight(30 if compact else 48)


class NewsBriefingPanel(QWidget):
    """Octógono chanfrado NEWS DRAWER posicionado entre ULTRON CORE e VOID DOCK."""

    IDLE_H = 48

    def __init__(self, anchor, accent=lambda: "#ff2034", parent=None, *,
                 docked: bool = False, bottom_offset: int = 58):
        super().__init__(parent or anchor)
        self._anchor = anchor
        self._accent = accent
        self._docked = bool(docked)
        self._bottom_offset = int(bottom_offset)
        self._items = []
        self._rows = []
        self._expanded = False
        self._wanted = False
        self._hud_page = True
        self.setObjectName("NewsBriefingPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        if self._docked:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 9, 16, 8)
        self._outer.setSpacing(4)

        # Idle compact wireframe state (NEWS DRAWER / COLLAPSIBLE)
        self._idle_box = QWidget(self)
        self._idle_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        idle_lay = QVBoxLayout(self._idle_box)
        idle_lay.setContentsMargins(0, 0, 0, 0)
        idle_lay.setSpacing(1)
        self._idle_title = QLabel("NEWS DRAWER", self._idle_box)
        self._idle_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idle_sub = QLabel("COLLAPSIBLE", self._idle_box)
        self._idle_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idle_lay.addWidget(self._idle_title)
        idle_lay.addWidget(self._idle_sub)
        self._outer.addWidget(self._idle_box)

        # Active/expanded briefing content
        self._active_box = QWidget(self)
        active_lay = QVBoxLayout(self._active_box)
        active_lay.setContentsMargins(0, 0, 0, 0)
        active_lay.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._dot = QLabel("●", self._active_box)
        head.addWidget(self._dot)
        self._title = QLabel("NEWS DRAWER", self._active_box)
        head.addWidget(self._title)
        head.addStretch(1)
        self._toggle = _ModernButton("toggle", self._accent, self._active_box)
        self._toggle.set_state("EXPAND", False)
        self._toggle.clicked.connect(lambda: self.set_expanded(not self._expanded))
        head.addWidget(self._toggle)
        self._close = _ModernButton("close", self._accent, self._active_box)
        self._close.setToolTip("Recolher notícias")
        self._close.clicked.connect(self.hide_news)
        head.addWidget(self._close)
        active_lay.addLayout(head)

        self._sep = QFrame(self._active_box)
        self._sep.setFixedHeight(1)
        active_lay.addWidget(self._sep)

        self._empty_hint = QLabel(
            "Nenhuma manchete carregada — peça 'notícias de hoje' ao ULTRON.",
            self._active_box,
        )
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        active_lay.addWidget(self._empty_hint)

        self._scroll = QScrollArea(self._active_box)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)
        self._body = QWidget()
        self._body.setAutoFillBackground(False)
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 8, 0)
        self._body_lay.setSpacing(0)
        self._body_lay.addStretch(1)
        self._scroll.setWidget(self._body)
        self._scroll.viewport().setAutoFillBackground(False)
        self._body.setAutoFillBackground(False)
        active_lay.addWidget(self._scroll, 1)

        self._footer = QLabel("", self._active_box)
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        active_lay.addWidget(self._footer)
        self._outer.addWidget(self._active_box, 1)

        bar = self._scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda *_: self._refresh_footer())
        bar.valueChanged.connect(lambda *_: self._refresh_footer())

        self.apply_theme()
        node = anchor
        while node is not None:
            node.installEventFilter(self)
            if node is self.parentWidget():
                break
            node = node.parentWidget()
        if self._docked:
            self._sync_mode_widgets()
            self._sync_visibility()
        else:
            self.hide()

    # ── API ────────────────────────────────────────────────────────────────
    def show_news(self, items):
        """Mostra os itens recolhidos. `items` é lista de dicts title/snippet/source."""
        self._items = [i for i in items if i.get("title")]
        if not self._items:
            return self.hide_news()
        while self._rows:
            self._rows.pop().deleteLater()
        for n, item in enumerate(self._items, 1):
            row = _NewsRow(n, item, self._accent(), self._body)
            self._body_lay.insertWidget(self._body_lay.count() - 1, row)
            self._rows.append(row)
        self._wanted = True
        self.set_expanded(False)
        self._scroll.verticalScrollBar().setValue(0)
        self._sync_visibility()

    def hide_news(self):
        self._wanted = False
        self._expanded = False
        self._sync_mode_widgets()
        self._sync_visibility()

    def is_expanded(self):
        return self._expanded

    def set_expanded(self, expanded):
        self._expanded = bool(expanded)
        self._toggle.set_state("MINIMIZE" if self._expanded else "EXPAND", self._expanded)
        for index, row in enumerate(self._rows):
            row.set_compact(not self._expanded)
            row.setVisible(self._expanded or index < COLLAPSED_ROWS)
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if self._expanded
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if not self._expanded:
            self._scroll.verticalScrollBar().setValue(0)
        self._sync_mode_widgets()
        self._refresh_footer()
        self.reposition()
        self.update()

    def on_page_changed(self, index):
        self._hud_page = index == 0
        self._sync_visibility()

    def mousePressEvent(self, event):
        if (self._docked and not self._wanted and not self._expanded
                and event.button() == Qt.MouseButton.LeftButton):
            self.set_expanded(True)
            event.accept()
            return
        super().mousePressEvent(event)

    # ── interno ────────────────────────────────────────────────────────────
    def _is_idle_pill(self) -> bool:
        return self._docked and not self._wanted and not self._expanded

    def _sync_mode_widgets(self):
        idle = self._is_idle_pill()
        self._idle_box.setVisible(idle)
        self._active_box.setVisible(not idle)
        if not idle:
            has_items = bool(self._wanted and self._items)
            self._empty_hint.setVisible(not has_items)
            self._scroll.setVisible(has_items)
            self._toggle.setVisible(has_items or self._expanded)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._outer.setContentsMargins(16, 10, 16, 8)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._outer.setContentsMargins(16, 7, 16, 6)

    def _sync_visibility(self):
        show = (self._wanted or self._docked) and self._hud_page
        self.setVisible(show)
        if show:
            self._sync_mode_widgets()
            self.reposition()

    def _refresh_footer(self):
        if not self._wanted or not self._items:
            self._footer.setVisible(False)
            return
        total = len(self._items)
        if not self._expanded:
            shown = min(COLLAPSED_ROWS, total)
            text = (f"{shown} DE {total} NOTÍCIAS • EXPANDIR PARA LER"
                    if total > shown else f"{total} NOTÍCIAS")
            self._footer.setText(text)
            self._footer.setVisible(True)
            return
        bar = self._scroll.verticalScrollBar()
        more = bar.maximum() > 0 and bar.value() < bar.maximum()
        self._footer.setText("SCROLL FOR MORE ↓")
        self._footer.setVisible(more)

    def apply_theme(self):
        red = self._accent()
        self._idle_title.setStyleSheet(
            f"color: {red}; font: bold 11px Consolas; letter-spacing: 2px; background: transparent;")
        self._idle_sub.setStyleSheet(
            "color: #9696a2; font: 10px Consolas; letter-spacing: 1.4px; background: transparent;")
        self._dot.setStyleSheet(f"color: {red}; font: 10px Consolas; background: transparent;")
        self._title.setStyleSheet(
            f"color: {red}; font: bold 11px Consolas; letter-spacing: 1.5px; background: transparent;")
        self._empty_hint.setStyleSheet(
            "color: #8a8a98; font: 10px Consolas; background: transparent; padding: 8px 4px;")
        self._toggle.update()
        self._close.update()
        self._sep.setStyleSheet("background: #3a0d15; border: none;")
        self._footer.setStyleSheet(
            "color: #a07880; font: 10px Consolas; background: transparent; letter-spacing: 1px;")
        self._scroll.setStyleSheet(
            "QScrollArea { background: #000000; border: none; }"
            "QScrollBar:vertical { background: #140609; width: 4px; border: none; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {red}; border-radius: 2px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }")
        self.update()

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        w, h = self._anchor.width(), self._anchor.height()
        avail = max(w + 24, min(376, parent.width() - 40)) if parent is not self._anchor else w - 16
        width = max(1, min(384, avail, max(1, parent.width() - 20)))
        if self._is_idle_pill():
            wanted = self.IDLE_H
        elif not self._wanted:
            wanted = 104
        else:
            wanted = 236 if self._expanded else 132
        max_h = max(self.IDLE_H, (parent.height() - self._bottom_offset - 70) if self._docked else (h - 24))
        height = max(1, min(wanted, max_h))

        if parent is not self._anchor and self._anchor.width() > 0:
            origin = parent.mapFromGlobal(self._anchor.mapToGlobal(self._anchor.rect().topLeft()))
            cx = origin.x() + w // 2
        else:
            origin = self._anchor.rect().topLeft()
            cx = parent.width() // 2

        x = max(8, min(parent.width() - width - 8, cx - width // 2))
        if self._docked and parent is not self._anchor:
            y = max(62, parent.height() - self._bottom_offset - height)
        else:
            y = max(0, origin.y() + h - height - 4)
        self.setGeometry(max(0, x), max(0, y), width, height)
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is not self and event.type() in (
                QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show,
                QEvent.Type.LayoutRequest):
            if self.isVisible():
                self.reposition()
        return False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        c = min(13.0, h * 0.27, w * 0.08)
        m = 1.5
        outline = QPolygonF([
            QPointF(m + c, m), QPointF(w - m - c, m), QPointF(w - m, m + c),
            QPointF(w - m, h - m - c), QPointF(w - m - c, h - m), QPointF(m + c, h - m),
            QPointF(m, h - m - c), QPointF(m, m + c)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 255))
        p.drawPolygon(outline)

        red = QColor(self._accent())
        edge = QColor(red)
        edge.setAlpha(150)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(edge, 1.25))
        p.drawPolygon(outline)

        hi = QColor(red)
        hi.setAlpha(230)
        p.setPen(QPen(hi, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(m, m + c), QPointF(m + c, m))
        p.drawLine(QPointF(w - m - c, m), QPointF(w - m, m + c))
        p.drawLine(QPointF(m, h - m - c), QPointF(m + c, h - m))
        p.drawLine(QPointF(w - m - c, h - m), QPointF(w - m, h - m - c))
        p.end()
