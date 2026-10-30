"""Compact conversation overlay. Activity/history remains owned by LogWidget."""
from datetime import datetime
import time

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QTextDocument
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)


class ChatBubble(QFrame):
    readingRequested = pyqtSignal()

    def __init__(self, author, user=False, parent=None):
        super().__init__(parent)
        self.text = ""
        self.expanded = False
        self._display_key = None
        self._collapsed_cache = None
        self._size_key = None
        self.setObjectName("HoloChatBubble")
        self.setProperty("chatRole", "user" if user else "assistant")
        self.setStyleSheet('''
            QFrame#HoloChatBubble { background: #19060b; border: 1px solid #44101a; border-radius: 9px; }
            QFrame#HoloChatBubble[chatRole="user"] { background: #101013; border-color: #29292e; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(4)
        header = QHBoxLayout()
        label = QLabel(author, self)
        label.setObjectName("HoloChatAuthor")
        label.setStyleSheet("#HoloChatAuthor { color: #8a8a98; font: 9px 'Segoe UI'; border: none; background: transparent; }")
        header.addWidget(label)
        header.addStretch()
        stamp = QLabel(datetime.now().strftime("%H:%M"), self)
        stamp.setObjectName("HoloChatTime")
        stamp.setStyleSheet("#HoloChatTime { color: #5a5a68; font: 9px 'Segoe UI'; border: none; background: transparent; }")
        header.addWidget(stamp)
        layout.addLayout(header)
        self.body = QLabel(self)
        self.body.setObjectName("HoloChatText")
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setFont(QFont("Segoe UI", 9))
        self.body.setStyleSheet("#HoloChatText { color: #ececf2; font: 12px 'Segoe UI'; border: none; background: transparent; }")
        layout.addWidget(self.body)
        self.more = QPushButton("Ler mais", self)
        self.more.setObjectName("HoloChatMore")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.setStyleSheet("#HoloChatMore { color: #ff2034; font: 10px 'Segoe UI'; text-align: left; background: transparent; border: none; padding: 0; }")
        self.more.clicked.connect(self._toggle)
        layout.addWidget(self.more)
        self.more.hide()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self._refresh()

    def _preview(self, width):
        # Use Qt's actual line wrapping; positions are UTF-16 offsets (emoji).
        document = QTextDocument()
        document.setDefaultFont(self.body.font())
        document.setDocumentMargin(0)
        document.setPlainText(self.text)
        document.setTextWidth(width)
        document.documentLayout().documentSize()
        block = document.begin()
        lines = []
        while block.isValid():
            layout = block.layout()
            for index in range(layout.lineCount()):
                line = layout.lineAt(index)
                start = block.position() + line.textStart()
                end = start + line.textLength()
                lines.append((start, end))
                if len(lines) > 4:
                    encoded = self.text.encode("utf-16-le")
                    pieces = [encoded[a * 2:b * 2].decode("utf-16-le", errors="ignore").rstrip()
                              for a, b in lines[:4]]
                    pieces[-1] = self.body.fontMetrics().elidedText(
                        pieces[-1] + "…", Qt.TextElideMode.ElideRight, width)
                    return "\n".join(pieces), True
            block = block.next()
        return self.text, False

    def _refresh(self):
        width = max(40, self.width() - 20)
        key = (self.text, width, self.expanded, self.body.font().key())
        if key == self._display_key:
            return
        self._display_key = key
        font_key = self.body.font().key()
        cache = self._collapsed_cache
        if cache and cache[0] == (width, font_key) and self.text.startswith(cache[1]):
            preview, long = cache[2], True
        else:
            preview, long = self._preview(width)
            self._collapsed_cache = ((width, font_key), self.text, preview) if long else None
        display = (self.text if self.expanded else preview) or "…"
        size_key = (display, width, font_key, long)
        if size_key == self._size_key:
            return  # A growing collapsed reply keeps the same four-line preview.
        self._size_key = size_key
        self.body.setText(display)
        self.more.setVisible(long)
        self.more.setText("Ler menos" if self.expanded else "Ler mais")
        # Height is owned by the bubble, never by the fixed-size outer panel.
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.body.font())
        document.setPlainText(self.body.text())
        document.setTextWidth(width)
        self.body.setFixedHeight(max(self.body.fontMetrics().lineSpacing(),
                                     int(document.size().height()) + 2))
        self.setFixedHeight(14 + self.layout().itemAt(0).sizeHint().height() + 4
                            + self.body.height() + (20 if long else 0))

    def _toggle(self):
        self.readingRequested.emit()
        self.expanded = not self.expanded
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()


class HoloChat(QWidget):
    """Native child overlay, independent of HUD painting and proxy scenes."""
    MAX_MESSAGES = 100
    IDLE_SECONDS = 4.0

    def __init__(self, anchor, accent=lambda: "#ff2034", parent=None):
        super().__init__(parent or anchor)
        self._anchor = anchor
        self._accent = accent
        self._messages = []
        self._current = None
        self._current_prefix = 0
        self._follow = True
        self._adjusting = False
        self._unread = 0
        self._minimized = False
        self._hud_clock = None
        self._hud_page = True
        self._idle_hidden = False
        self._typing = False
        self._last_activity = time.perf_counter()
        self.setObjectName("HoloConversation")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("#HoloConversation { background: transparent; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 9)
        layout.setSpacing(6)
        header = QHBoxLayout()
        self.title = QLabel("●  ULTRON", self)
        self.title.setObjectName("HoloChatTitle")
        self.title.setStyleSheet("#HoloChatTitle { color: #ff2034; background: transparent; font: bold 10px 'Segoe UI'; }")
        header.addWidget(self.title)
        header.addStretch()
        self.minimize = QPushButton("−", self)
        self.minimize.setObjectName("HoloChatMinimize")
        self.minimize.setFixedSize(22, 19)
        self.minimize.setToolTip("Recolher conversa")
        self.minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimize.setStyleSheet("#HoloChatMinimize { color: #ff2034; font: 14px 'Segoe UI'; border: none; background: transparent; padding: 0; }")
        self.minimize.clicked.connect(self._toggle_minimized)
        header.addWidget(self.minimize)
        layout.addLayout(header)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("HoloChatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet('''
            QScrollArea#HoloChatScroll { background: transparent; border: none; }
            QScrollBar:vertical { width: 3px; background: #101013; margin: 0; }
            QScrollBar::handle:vertical { background: #60141f; min-height: 18px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        ''')
        self.scroll.viewport().setAutoFillBackground(False)
        self.messages = QWidget()
        self.messages.setObjectName("HoloChatMessages")
        self.messages.setStyleSheet("#HoloChatMessages { background: transparent; }")
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(0, 0, 7, 0)
        self.message_layout.setSpacing(9)
        self.message_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.empty = QLabel("Nossa conversa aparece aqui.", self.messages)
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color: #8a8a98; background: transparent; font: 11px 'Segoe UI';")
        self.message_layout.addWidget(self.empty)
        self.scroll.setWidget(self.messages)
        layout.addWidget(self.scroll, 1)
        self.new_messages = QPushButton("Novas mensagens ↓", self)
        self.new_messages.setObjectName("HoloChatNew")
        self.new_messages.setStyleSheet("#HoloChatNew { color: #ff2034; background: #19060b; border: 1px solid #44101a; border-radius: 5px; font: 10px 'Segoe UI'; padding: 3px; }")
        self.new_messages.clicked.connect(self.follow_latest)
        layout.addWidget(self.new_messages)
        self.new_messages.hide()
        bar = self.scroll.verticalScrollBar()
        bar.valueChanged.connect(self._scrolled)
        bar.rangeChanged.connect(self._range_changed)
        self.scroll.viewport().installEventFilter(self)
        self._anchor.installEventFilter(self)
        self._watch_activity(self)
        self.reposition()

    def bind_hud_clock(self, hud):
        """Check inactivity on the shared animation clock; no extra timer."""
        if self._hud_clock is hud:
            return
        if self._hud_clock is not None:
            self._hud_clock.pacedFrame.disconnect(self._on_frame)
        self._hud_clock = hud
        hud.pacedFrame.connect(self._on_frame)

    def _watch_activity(self, widget):
        for child in (widget, *widget.findChildren(QWidget)):
            child.setMouseTracking(True)
            child.installEventFilter(self)

    def _touch(self, now=None, reveal=False):
        self._last_activity = time.perf_counter() if now is None else now
        if reveal:
            self._idle_hidden = False
            if self._hud_page and self.isHidden():
                self.show()
                self.reposition()

    def _pointer_inside(self):
        return self.isVisible() and self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _on_frame(self, now):
        if not self._hud_page:
            return
        if self._typing or getattr(self._hud_clock, "speaking", False) or self._pointer_inside():
            self._touch(now)
        elif not self._idle_hidden and now - self._last_activity >= self.IDLE_SECONDS:
            self._idle_hidden = True
            self.hide()

    def begin_entry(self, text, category):
        self._current = None
        if category not in ("Você", "Ultron"):
            return
        self._typing = True
        self._touch(reveal=True)
        self.empty.hide()
        user = category == "Você"
        row = QWidget(self.messages)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        author = "Você" if user else (text.partition(":")[0].strip() if ":" in text else "ULTRON")
        bubble = ChatBubble(author, user, row)
        bubble.readingRequested.connect(self._pause_follow)
        if user:
            row_layout.addSpacing(20)
        row_layout.addWidget(bubble, 1)
        if not user:
            row_layout.addSpacing(20)
        self.message_layout.addWidget(row)
        self._messages.append((row, bubble))
        self._current = bubble
        self._watch_activity(row)
        self._current_prefix = len(text) - len(text.partition(":")[2].lstrip()) if ":" in text else 0
        if len(self._messages) > self.MAX_MESSAGES:
            old, _ = self._messages.pop(0)
            self.message_layout.removeWidget(old)
            old.deleteLater()
        if not self._follow:
            self._unread += 1
            self.new_messages.setVisible(not self._minimized)
        bubble._refresh()

    def update_entry(self, text, category, finished):
        if self._current is None or category not in ("Você", "Ultron"):
            return
        # Incoming text is a plain transcript. Never interpret model text as HTML.
        self._current.set_text(text[self._current_prefix:])
        self._typing = not finished
        self._touch(reveal=True)

    def _pause_follow(self):
        self._touch()
        self._follow = False

    def _scrolled(self, value):
        if not self._adjusting:
            self._follow = value >= self.scroll.verticalScrollBar().maximum() - 3
            if self._follow:
                self._unread = 0
                self.new_messages.hide()

    def _range_changed(self, minimum, maximum):
        if self._follow:
            self._adjusting = True
            try:
                self.scroll.verticalScrollBar().setValue(maximum)
            finally:
                self._adjusting = False

    def follow_latest(self):
        self._touch()
        self._follow = True
        self._unread = 0
        self.new_messages.hide()
        self._range_changed(0, self.scroll.verticalScrollBar().maximum())

    def _toggle_minimized(self):
        self._touch()
        self._minimized = not self._minimized
        self.scroll.setVisible(not self._minimized)
        self.new_messages.setVisible(not self._minimized and self._unread > 0)
        self.minimize.setText("+" if self._minimized else "−")
        self.minimize.setToolTip("Abrir conversa" if self._minimized else "Recolher conversa")
        self.reposition()

    def reposition(self):
        w, h = self._anchor.width(), self._anchor.height()
        width = min(280, max(200, int(w * .25)), max(1, w - 24))
        height = 36 if self._minimized else min(240, max(160, int(h * .29)), max(1, h - 24))
        x = min(w - width - 12, int(w * .67))
        y = int(h * .36) if w >= 650 else h - height - 12
        origin = self._anchor.mapTo(self.parentWidget(), QPoint(0, 0))
        if w < 650 and self.parentWidget() is not self._anchor:
            # Use the cleared lower sidebar space on narrow windows, instead
            # of covering the crystal or its listening/status label.
            x = min(origin.x() + w + 24, self.parentWidget().width() - width - 12)
            y += origin.y()
        else:
            x += origin.x()
            y = origin.y() + max(0, min(y, h - height - 8))
        self.setGeometry(max(0, x), max(0, y), width, height)
        self.raise_()

    def on_page_changed(self, index):
        self._hud_page = index == 0
        self.setVisible(self._hud_page and not self._idle_hidden)
        if self.isVisible():
            self._touch()
            self.reposition()

    def eventFilter(self, watched, event):
        if watched is not self._anchor and event.type() in (
                QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            self._touch()
        if watched is self._anchor and event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self.reposition()
        elif watched is self.scroll.viewport() and event.type() == QEvent.Type.Wheel:
            if event.angleDelta().y() > 0:
                self._pause_follow()
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, cut = self.width() - 1, self.height() - 1, 9
        path = QPainterPath()
        path.moveTo(cut, 1)
        for x, y in ((w - cut, 1), (w, cut), (w, h - cut), (w - cut, h),
                     (cut, h), (1, h - cut), (1, cut)):
            path.lineTo(x, y)
        path.closeSubpath()
        painter.fillPath(path, QColor(0, 0, 0, 235))
        color = QColor(self._accent())
        color.setAlpha(165)
        painter.setPen(QPen(color, .8))
        painter.drawPath(path)
        color.setAlpha(45)
        painter.setPen(QPen(color, .7))
        painter.drawLine(10, 31, w - 10, 31)
        painter.end()
