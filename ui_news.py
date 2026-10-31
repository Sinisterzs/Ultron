"""Painel gráfico NEWS / DAILY BRIEFING: recolhido por padrão, expansível, oculto fora de notícias.

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
    """Botão pintado: pílula com seta (alternar) ou círculo com X (fechar)."""

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
            self.setFixedSize(24, 24)
        else:
            self.setFixedHeight(24)

    def set_state(self, label, opened):
        self._label, self._open = label, opened
        if self._kind != "close":
            width = QFontMetrics(self._font()).horizontalAdvance(label) + 40
            self.setFixedWidth(width)
        self.update()

    def _font(self):
        font = QFont("Consolas")
        font.setPixelSize(11)
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
        fill.setAlpha(60 if self._hover else 22)
        edge = QColor(red)
        edge.setAlpha(255 if self._hover else 120)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2.0
        p.setPen(QPen(edge, 1.2))
        p.setBrush(fill)
        p.drawRoundedRect(rect, radius, radius)
        ink = QColor("#ffffff") if self._hover else QColor("#d6d6dc")
        p.setPen(QPen(ink, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = rect.center().x(), rect.center().y()
        if self._kind == "close":
            d = 4.0
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))
        else:
            p.setFont(self._font())
            text_rect = QRectF(rect.left() + 12, rect.top(), rect.width() - 30, rect.height())
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self._label)
            ax, ay = rect.right() - 14, cy
            tip = -2.0 if self._open else 2.0     # ^ minimizar, v expandir
            p.drawPolyline(QPolygonF([
                QPointF(ax - 4, ay - tip), QPointF(ax, ay + tip), QPointF(ax + 4, ay - tip)]))
        p.end()


class _NewsRow(QWidget):
    def __init__(self, number, item, accent, parent=None):
        super().__init__(parent)
        self.setObjectName("NewsRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 4, 3, 4)
        lay.setSpacing(12)
        num = QLabel(f"{number:02d}", self)
        num.setFixedWidth(22)
        num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        num.setStyleSheet(f"color: {accent}; font: 12px Consolas; background: transparent;")
        lay.addWidget(num)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.title = _ElideLabel(item["title"], self)
        self.title.setFixedHeight(17)
        self.title.setStyleSheet("color: #f2f2f6; font: 13px Consolas; background: transparent;")
        col.addWidget(self.title)
        self.sub = _ElideLabel(item["snippet"] or item["source"], self)
        self.sub.setFixedHeight(15)
        self.sub.setStyleSheet("color: #8d8d96; font: 10px Consolas; background: transparent;")
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.setStyleSheet("QWidget#NewsRow { border-bottom: 1px solid #2b0a10; }")
        self.set_compact(True)

    def set_compact(self, compact):
        self.sub.setVisible(not compact and bool(self.sub._full))
        self.setFixedHeight(32 if compact else 50)


class NewsBriefingPanel(QWidget):
    def __init__(self, anchor, accent=lambda: "#ff2034", parent=None):
        super().__init__(parent or anchor)
        self._anchor = anchor
        self._accent = accent
        self._items = []
        self._rows = []
        self._expanded = False
        self._wanted = False      # há notícias para mostrar
        self._hud_page = True
        self.setObjectName("NewsBriefingPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 9)
        outer.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(6)
        self._dot = QLabel("●", self)
        head.addWidget(self._dot)
        self._title = QLabel("NEWS / DAILY BRIEFING", self)
        head.addWidget(self._title)
        head.addStretch(1)
        self._toggle = _ModernButton("toggle", self._accent, self)
        self._toggle.set_state("EXPAND", False)
        self._toggle.clicked.connect(lambda: self.set_expanded(not self._expanded))
        head.addWidget(self._toggle)
        self._close = _ModernButton("close", self._accent, self)
        self._close.setToolTip("Ocultar notícias")
        self._close.clicked.connect(self.hide_news)
        head.addWidget(self._close)
        outer.addLayout(head)

        self._sep = QFrame(self)
        self._sep.setFixedHeight(1)
        outer.addWidget(self._sep)

        self._scroll = QScrollArea(self)
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
        # QScrollArea.setWidget reativa o preenchimento; precisa vir depois dele.
        self._scroll.viewport().setAutoFillBackground(False)
        self._body.setAutoFillBackground(False)
        outer.addWidget(self._scroll, 1)

        self._footer = QLabel("", self)
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._footer)
        bar = self._scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda *_: self._refresh_footer())
        bar.valueChanged.connect(lambda *_: self._refresh_footer())

        self.apply_theme()
        node = anchor
        while node is not None:           # ancestrais não notificam a âncora
            node.installEventFilter(self)
            if node is self.parentWidget():
                break
            node = node.parentWidget()
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
        self._refresh_footer()
        self.reposition()
        self.update()

    def on_page_changed(self, index):
        self._hud_page = index == 0
        self._sync_visibility()

    # ── interno ────────────────────────────────────────────────────────────
    def _sync_visibility(self):
        show = self._wanted and self._hud_page
        self.setVisible(show)
        if show:
            self.reposition()

    def _refresh_footer(self):
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
        self._dot.setStyleSheet(f"color: {red}; font: 10px Consolas; background: transparent;")
        self._title.setStyleSheet(
            f"color: {red}; font: bold 11px Consolas; background: transparent;")
        self._toggle.update()
        self._close.update()
        self._sep.setStyleSheet("background: #3a0d15; border: none;")
        self._footer.setStyleSheet(
            "color: #a07880; font: 10px Consolas; background: transparent; letter-spacing: 1px;")
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: #1c0a0e; width: 4px; border: none; margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {red}; border-radius: 2px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }")
        self.update()

    def reposition(self):
        w, h = self._anchor.width(), self._anchor.height()
        parent = self.parentWidget()
        avail = max(w + 44, min(350, parent.width() - 40)) if parent is not self._anchor else w - 16
        width = max(1, min(380, avail))
        wanted = 240 if self._expanded else 136
        height = max(1, min(wanted, h - 24))
        origin = parent.mapFromGlobal(self._anchor.mapToGlobal(self._anchor.rect().topLeft()))
        cx = origin.x() + w // 2
        x = cx - width // 2
        y = origin.y() + h - height - 4
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
        w, h, c, m = float(self.width()), float(self.height()), 14.0, 2.0
        outline = QPolygonF([
            QPointF(m + c, m), QPointF(w - m - c, m), QPointF(w - m, m + c),
            QPointF(w - m, h - m - c), QPointF(w - m - c, h - m), QPointF(m + c, h - m),
            QPointF(m, h - m - c), QPointF(m, m + c)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 242))
        p.drawPolygon(outline)
        red = QColor(self._accent())
        dim = QColor(red)
        dim.setAlpha(70)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(dim, 1.5))
        p.drawPolygon(outline)
        p.setPen(QPen(red, 3.0))
        seg = min(84.0, w * 0.2)
        p.drawPolyline(QPolygonF([QPointF(m, 60), QPointF(m, m + c), QPointF(m + c, m), QPointF(m + seg, m)]))
        p.drawPolyline(QPolygonF([QPointF(w - m - seg, m), QPointF(w - m - c, m), QPointF(w - m, m + c), QPointF(w - m, 60)]))
        p.drawPolyline(QPolygonF([QPointF(m, h - 60), QPointF(m, h - m - c), QPointF(m + c, h - m), QPointF(m + seg, h - m)]))
        p.drawPolyline(QPolygonF([QPointF(w - m - seg, h - m), QPointF(w - m - c, h - m), QPointF(w - m, h - m - c), QPointF(w - m, h - 60)]))
        p.end()
