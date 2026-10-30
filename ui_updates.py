"""Small update notification; all I/O stays in workers and requires an explicit click."""
from __future__ import annotations

import threading
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar


class UpdateToast(QFrame):
    updateRequested = pyqtSignal(object)
    cancelRequested = pyqtSignal()

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release, self.busy = release, False
        self.setObjectName("UpdateToast")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(340)
        self.setStyleSheet("""
            QFrame#UpdateToast { background:#000; border:1px solid #60141f; border-radius:10px; }
            QLabel { background:transparent; border:0; color:#aaaaaa; font:12px 'Segoe UI'; }
            QPushButton { background:transparent; border:0; color:#ff2034; font:12px 'Segoe UI'; padding:2px; }
            QPushButton:hover { color:#ff6677; }
            QProgressBar { border:0; background:#210408; height:4px; }
            QProgressBar::chunk { background:#f0203d; }
        """)
        box = QVBoxLayout(self); box.setContentsMargins(16, 13, 16, 13)
        top = QHBoxLayout()
        title = QLabel("●  ATUALIZAÇÃO DISPONÍVEL")
        title.setStyleSheet("color:#ff2034;font-size:10px;font-weight:700")
        top.addWidget(title); top.addStretch()
        self.close_button = QPushButton("×")
        self.close_button.setAccessibleName("Dispensar atualização")
        self.close_button.setFixedWidth(20)
        self.close_button.clicked.connect(self._dismiss)
        top.addWidget(self.close_button); box.addLayout(top)
        self.status = QLabel(f"ULTRON {release.version} está disponível.")
        self.status.setWordWrap(True); box.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.hide()
        box.addWidget(self.progress)
        row = QHBoxLayout(); row.addStretch()
        self.later = QPushButton("Depois"); self.later.clicked.connect(self._dismiss); row.addWidget(self.later)
        self.downloadable = bool(release.installer_url and release.sha256)
        if self.downloadable:
            try:
                from core.update_download import installed_root
                installed_root()
            except Exception:
                self.downloadable = False
        self.action = QPushButton("Baixar e reiniciar" if self.downloadable else "Ver atualização  ↗")
        self.action.clicked.connect(self._activate); row.addWidget(self.action)
        box.addLayout(row); self.adjustSize()

    def _activate(self):
        if self.downloadable:
            self.updateRequested.emit(self.release)
        else:
            QDesktopServices.openUrl(QUrl(self.release.url))

    def _dismiss(self):
        if self.busy:
            self.cancelRequested.emit()
        self.hide()

    def show_progress(self, text, current, total):
        self.busy = True
        self.status.setText(text)
        self.action.setEnabled(False); self.later.setText("Cancelar")
        self.progress.show()
        self.progress.setRange(0, 100 if total else 0)
        if total:
            self.progress.setValue(min(100, int(current * 100 / total)))
        self.adjustSize()

    def show_error(self, text):
        self.busy = False; self.status.setText(text)
        self.progress.hide(); self.action.setEnabled(True); self.later.setText("Depois")
        self.adjustSize()


class ReleaseWorker(QObject):
    available = pyqtSignal(object)
    finished = pyqtSignal()

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="ultron-release-check").start()

    def run(self):
        try:
            from core.updates import check_release
            release = check_release()
            if release:
                self.available.emit(release)
        except Exception:
            pass  # Offline/rate limited/unconfigured never interrupts the assistant.
        finally:
            self.finished.emit()


class DownloadWorker(QObject):
    progress = pyqtSignal(str, int, int)
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, release, stop, parent=None):
        super().__init__(parent)
        self.release, self.stop = release, stop

    def run(self):
        try:
            from core.update_download import download_and_handoff
            folder = download_and_handoff(self.release, self.progress.emit, self.stop.is_set)
            self.ready.emit(folder)
        except Exception as exc:
            from core.install_manager import redact_install_output
            self.failed.emit(redact_install_output(str(exc)))


class UpdateController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.toast = None
        self.worker = None
        self.started = self.checking = self.downloading = False
        self.dismissed = set()
        self.stop = threading.Event()
        self.timer = QTimer(self)
        self.timer.setInterval(5 * 60 * 1000)
        self.timer.timeout.connect(self._check)
        window.centralWidget().installEventFilter(self)
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self.stop.set)

    def start(self):
        if self.started:
            return
        self.started = True
        self.timer.start()
        QTimer.singleShot(12000, self._check)

    def _check(self):
        if self.checking or self.downloading or not getattr(self.window, "_ready", False):
            return
        self.checking = True
        self.worker = ReleaseWorker(self)
        self.worker.available.connect(self._show)
        self.worker.finished.connect(self._check_finished)
        self.worker.start()

    def _check_finished(self):
        self.checking = False
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def _show(self, release):
        if release.version in self.dismissed or self.downloading:
            return
        self.dismissed.add(release.version)
        if self.toast:
            self.toast.hide(); self.toast.deleteLater()
        self.toast = UpdateToast(release, self.window.centralWidget())
        self.toast.updateRequested.connect(self._download)
        self.toast.cancelRequested.connect(self.stop.set)
        self._place(); self.toast.show(); self.toast.raise_()

    def _download(self, release):
        if self.downloading:
            return
        self.downloading = True; self.stop.clear()
        self.toast.show_progress("Baixando atualização. O app reiniciará ao concluir.", 0, 0)
        self._place()
        self.download_worker = DownloadWorker(release, self.stop, self)
        self.download_worker.progress.connect(self._progress)
        self.download_worker.failed.connect(self._failed)
        self.download_worker.ready.connect(self._handoff)
        threading.Thread(target=self.download_worker.run, daemon=True, name="ultron-update-download").start()

    def _progress(self, text, current, total):
        self.toast.show_progress(text, current, total)
        self._place()

    def _failed(self, message):
        self.downloading = False
        self.toast.show_error(message)
        self._place()
        self.download_worker.deleteLater()

    def _handoff(self, folder):
        # Calling close() preserves the existing async shutdown coordinator.
        # The independent helper waits for process exit; it never kills the app.
        if self.stop.is_set():
            (folder / "cancel").touch()
            self._failed("Atualização cancelada. O aplicativo continua aberto.")
            return
        (folder / "proceed").touch()
        self.toast.show_progress("Fechando o ULTRON para aplicar a atualização…", 0, 0)
        self.toast.later.setEnabled(False); self.toast.close_button.setEnabled(False)
        self.timer.stop()
        self.window.close()

    def _place(self):
        if self.toast:
            area = self.window.centralWidget()
            self.toast.move(max(8, area.width() - self.toast.width() - 18),
                            max(8, area.height() - self.toast.height() - 110))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self._place()
        return False
