"""Small non-modal update notification. Workers emit signals; widgets stay on Qt."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QEvent, QTimer, Qt, pyqtSignal
import threading
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class UpdateToast(QFrame):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateToast")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(320)
        self.setStyleSheet("""
            QFrame#UpdateToast { background:#030303; border:1px solid #60141f; border-radius:10px; }
            QLabel { background:transparent; border:0; color:#aaaaaa; font:12px 'Segoe UI'; }
            QPushButton { background:transparent; border:0; color:#ff2034; font:12px 'Segoe UI'; padding:2px; }
            QPushButton:hover { color:#ff6677; }
        """)
        box = QVBoxLayout(self); box.setContentsMargins(16, 13, 16, 13)
        top = QHBoxLayout()
        title = QLabel("●  ATUALIZAÇÃO DISPONÍVEL")
        title.setStyleSheet("color:#ff2034;font-size:10px;font-weight:700")
        top.addWidget(title); top.addStretch()
        close = QPushButton("×"); close.setAccessibleName("Dispensar atualização")
        close.setFixedWidth(20); close.clicked.connect(self.hide); top.addWidget(close)
        box.addLayout(top)
        text = QLabel(f"ULTRON {release.version} está disponível.")
        text.setWordWrap(True); box.addWidget(text)
        row = QHBoxLayout(); row.addStretch()
        later = QPushButton("Depois"); later.clicked.connect(self.hide); row.addWidget(later)
        view = QPushButton("Ver atualização  ↗")
        view.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.url)))
        row.addWidget(view); box.addLayout(row)
        self.adjustSize()


class ReleaseWorker(QObject):
    available = pyqtSignal(object)

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="ultron-release-check").start()

    def run(self):
        try:
            from core.updates import check_release
            release = check_release()
            if release:
                self.available.emit(release)
        except Exception:
            pass  # Offline/rate limited/unconfigured must never interrupt the assistant.


class UpdateController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.toast = None
        self.worker = None
        self.started = False
        window.centralWidget().installEventFilter(self)

    def start(self):
        if self.started:
            return
        self.started = True
        QTimer.singleShot(12000, self._check)

    def _check(self):
        if not getattr(self.window, "_ready", False):
            self.started = False
            return
        self.worker = ReleaseWorker(self)
        self.worker.available.connect(self._show)
        self.worker.start()

    def _show(self, release):
        self.toast = UpdateToast(release, self.window.centralWidget())
        self._place(); self.toast.show(); self.toast.raise_()

    def _place(self):
        if self.toast:
            area = self.window.centralWidget()
            self.toast.move(max(8, area.width() - self.toast.width() - 18),
                            max(8, area.height() - self.toast.height() - 110))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self._place()
        return False
