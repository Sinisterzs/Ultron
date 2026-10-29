"""Read-only activity history fed by the existing log's formatted entries."""

from collections import deque

from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLineEdit, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)


class ActivityPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = deque(maxlen=2000)
        self._category = "Tudo"
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self._filters = QButtonGroup(self)
        self._filters.setExclusive(True)
        for name in ("Tudo", "SYS", "Você", "Ultron", "Plugin"):
            button = QPushButton(name, self)
            button.setCheckable(True)
            button.setProperty("markTheme", "button")
            button.setMinimumHeight(30)
            button.setChecked(name == "Tudo")
            self._filters.addButton(button)
            filters.addWidget(button)
        self._filters.buttonClicked.connect(self._select_filter)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Buscar no histórico…")
        self.search.textChanged.connect(self._rebuild)
        filters.addWidget(self.search, 1)
        clear = QPushButton("Limpar", self)
        clear.clicked.connect(self.clear_history)
        filters.addWidget(clear)
        layout.addLayout(filters)
        self.browser = QTextBrowser(self)
        self.browser.setReadOnly(True)
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setFont(QFont("Consolas", 9))
        self.browser.setProperty("markTheme", "log")
        layout.addWidget(self.browser, 1)

    def add_entry(self, text, category, html):
        full = len(self._entries) == self._entries.maxlen
        entry = (text, category, html)
        self._entries.append(entry)
        if full:
            self._rebuild()
        elif self._matches(entry):
            self._append_html(html)

    def _matches(self, entry):
        text, category, _html = entry
        return ((self._category == "Tudo" or category == self._category)
                and self.search.text().casefold() in text.casefold())

    def _select_filter(self, button):
        self._category = button.text()
        self._rebuild()

    def _append_html(self, html):
        cursor = self.browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.browser.document().isEmpty():
            cursor.insertBlock()
        cursor.insertHtml(html)
        self.browser.setTextCursor(cursor)
        self.browser.ensureCursorVisible()

    def _rebuild(self, *_args):
        self.browser.setUpdatesEnabled(False)
        try:
            self.browser.clear()
            for entry in self._entries:
                if self._matches(entry):
                    self._append_html(entry[2])
        finally:
            self.browser.setUpdatesEnabled(True)

    def clear_history(self):
        self._entries.clear()
        self.browser.clear()