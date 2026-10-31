"""Widget-only theme. Painted HUD palettes are deliberately left untouched."""

import re

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QTextEdit, QWidget

BG = "#000000"
SURFACE = "#000000"
SURFACE_2 = "#000000"
BORDER = "#2c0d14"
BORDER_HI = "#60141f"
TEXT = "#ececf2"
MUTED = "#767684"
DIM = "#46464f"
DEFAULT_ACCENT = "#ff2034"
_MARKER = "/* Mark LVI widget theme */"


def theme_tokens(accent):
    accent = (accent or DEFAULT_ACCENT).strip().lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", accent):
        accent = DEFAULT_ACCENT
    rgb = tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))

    def shade(factor):
        return "#" + "".join(f"{round(channel * factor):02x}" for channel in rgb)

    return {"ACCENT": accent, "ACCENT_DARK": shade(0.30),
            "ACCENT_DIM": shade(0.55), "ACCENT_SOFT": shade(0.12)}


def build_qss(accent):
    t = theme_tokens(accent)
    a, dark, soft = t["ACCENT"], t["ACCENT_DARK"], t["ACCENT_SOFT"]
    return f"""
    QWidget[markTheme="text"], QWidget[markTheme="card"],
    QWidget[markTheme="button"], QWidget[markTheme="field"] {{
        font-family: "Segoe UI Variable", "Segoe UI";
    }}
    QWidget[markTheme="background"] {{ background: {BG}; }}
    QWidget[markTheme="card"] {{
        background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 3px;
    }}
    QPushButton[markTheme="button"] {{
        background: {SURFACE_2}; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 3px;
    }}
    QPushButton[markTheme="button"]:hover {{
        background: {soft}; border-color: {a}; color: {TEXT};
    }}
    QPushButton[markTheme="button"]:pressed,
    QPushButton[markTheme="button"]:checked {{
        background: {dark}; border-color: {a};
    }}
    QPushButton[markTheme="button"]:disabled {{ color: {DIM}; }}
    QPushButton[markAction="microphone"] {{
        background: {dark}; border: 1px solid {a}; color: {TEXT};
    }}
    QPushButton[markAction="microphone"][markMuted="true"] {{
        background: {SURFACE_2}; color: {MUTED}; border-color: {BORDER_HI};
    }}
    QPushButton[markAction="interrupt"] {{
        background: transparent; color: {a}; border: 1px solid {a};
    }}
    QLineEdit[markTheme="field"], QTextEdit[markTheme="log"] {{
        background: {BG}; color: {TEXT}; border: 1px solid {BORDER};
        border-radius: 3px; selection-background-color: {dark};
    }}
    QLineEdit[markTheme="field"]:focus, QTextEdit[markTheme="log"]:focus {{
        border-color: {a};
    }}
    QTextEdit[markTheme="log"], QLabel[markTheme="number"] {{
        font-family: "Consolas";
    }}
    """


class WidgetTheme(QObject):
    """Keep local/state-dependent QSS in sync without changing widget geometry."""

    def __init__(self, window, palette):
        super().__init__(window)
        self.window = window
        self.palette = palette
        self.accent = DEFAULT_ACCENT
        self._busy = False
        self._sources = {}
        self._qss = build_qss(self.accent)
        self._styled = {}  # widget -> (source, role, accent, action, muted)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)

    def apply(self, accent):
        self.accent = theme_tokens(accent)["ACCENT"]
        self._qss = build_qss(self.accent)
        self._busy = True
        try:
            if self.window.styleSheet() != self._qss:
                self.window.setStyleSheet(self._qss)
            for widget in self.window.findChildren(QWidget):
                self._style(widget)
        finally:
            self._busy = False

    def _style(self, widget):
        hud = getattr(self.window, "hud", None)
        if hud is not None and (widget is hud or hud.isAncestorOf(widget)):
            return
        for attr in ("_core_status", "_news", "_bottom_nav", "_left_primary", "_right_primary"):
            chrome = getattr(self.window, attr, None)
            if chrome is not None and (widget is chrome or chrome.isAncestorOf(widget)):
                return
        bar = getattr(self.window, "_title_bar", None)
        in_bar = bar is not None and (widget is bar or bar.isAncestorOf(widget))
        if in_bar and widget not in (getattr(self.window, "_title_lbl", None),
                                     getattr(self.window, "_clock_lbl", None)):
            return
        current = widget.styleSheet()
        if _MARKER not in current:
            if widget not in self._sources:
                widget.destroyed.connect(lambda _=None, key=widget: (self._sources.pop(key, None), self._styled.pop(key, None)))
            self._sources[widget] = current
        source = self._sources.get(widget, current.split(_MARKER)[0])
        t = theme_tokens(self.accent)
        replacements = dict(zip(
            ("BG", "PANEL", "PANEL2", "DARK", "BAR_BG", "BORDER", "BORDER_B",
             "BORDER_A", "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "WHITE",
             "TEXT_MED", "TEXT_DIM", "GREEN", "GREEN_D"),
            (BG, SURFACE, SURFACE_2, BG, SURFACE_2, BORDER, BORDER_HI,
             BORDER, t["ACCENT"], t["ACCENT_DIM"], t["ACCENT_SOFT"], TEXT, TEXT,
             MUTED, DIM, t["ACCENT"], t["ACCENT_DIM"])))
        colors = {self.palette[key].lower(): value for key, value in replacements.items()}
        colors.update({"#00091a": SURFACE_2, "#00140a": t["ACCENT_DARK"],
                       "#001f10": t["ACCENT_SOFT"]})
        source = re.sub(r"#[0-9a-fA-F]{6}\b",
                        lambda match: colors.get(match[0].lower(), match[0]), source)
        role = None
        if not in_bar:
            if widget is self.window.centralWidget():
                role = "background"
            elif isinstance(widget, QPushButton):
                role = "button"
            elif isinstance(widget, QLineEdit):
                role = "field"
            elif isinstance(widget, QTextEdit):
                role = "log"
            elif isinstance(widget, QLabel):
                role = "number" if widget in (
                    getattr(self.window, "_uptime_lbl", None),
                    getattr(self.window, "_proc_lbl", None)) else "text"
            elif type(widget) is QWidget and "border" in source:
                role = "card"
        action = ("microphone" if widget is getattr(self.window, "_mute_btn", None)
                  else "interrupt" if widget is getattr(self.window, "_interrupt_btn", None)
                  else None)
        muted = bool(self.window._muted) if action == "microphone" else None
        signature = (source, role, self.accent, action, muted)
        if self._styled.get(widget) == signature and _MARKER in current:
            return  # Show/StyleChange often repeats with no effective change.

        if role and widget.property("markTheme") != role:
            widget.setProperty("markTheme", role)
        if action and widget.property("markAction") != action:
            widget.setProperty("markAction", action)
        if action == "microphone" and widget.property("markMuted") != muted:
            widget.setProperty("markMuted", muted)
        if source or role:
            result = source + "\n" + _MARKER + "\n" + self._qss
            if current != result:
                widget.setStyleSheet(result)
        self._styled[widget] = signature

    def eventFilter(self, watched, event):
        if (not self._busy and not sip.isdeleted(self.window)
                and isinstance(watched, QWidget)
                and self.window.isAncestorOf(watched)
                and event.type() in (QEvent.Type.StyleChange, QEvent.Type.Show)):
            self._busy = True
            try:
                self._style(watched)
            finally:
                self._busy = False
        return False