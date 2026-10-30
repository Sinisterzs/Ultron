"""Dedicated update helper UI, independent of the app being replaced."""
from __future__ import annotations
import threading
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton


class ApplyWorker(QObject):
    progress = pyqtSignal(str, int, int)
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, path, cancel):
        super().__init__()
        self.path, self.cancel = path, cancel

    def run(self):
        try:
            from core.update_apply import apply_request
            apply_request(self.path, self.progress.emit, self.cancel.is_set)
            self.succeeded.emit()
        except Exception as exc:
            from core.install_manager import redact_install_output
            self.failed.emit(redact_install_output(str(exc)))


class UpdateWindow(QWidget):
    running = True

    def closeEvent(self, event):
        if self.running:
            if self.cancel_button.isEnabled():
                self.stop.set()
            event.ignore()
        else:
            super().closeEvent(event)


def build_update_window():
    window = UpdateWindow()
    window.setWindowTitle("ULTRON — Atualização")
    window.setFixedSize(560, 250)
    window.setStyleSheet("""
        QWidget { background:#000; color:#bbbbbb; font:13px 'Segoe UI'; }
        QLabel#title { color:#ff2034; font-size:18px; font-weight:700; }
        QPushButton { color:#ff2034; border:1px solid #60141f; padding:8px; }
        QProgressBar { border:1px solid #40101a; background:#070000; height:5px; }
        QProgressBar::chunk { background:#ed1736; }
    """)
    box = QVBoxLayout(window); box.setContentsMargins(28, 24, 28, 24)
    title = QLabel("ULTRON  /  ATUALIZANDO"); title.setObjectName("title")
    status = QLabel("Preparando atualização"); status.setWordWrap(True)
    bar = QProgressBar(); bar.setRange(0, 0); bar.setTextVisible(False)
    cancel = QPushButton("Cancelar")
    box.addWidget(title); box.addWidget(status); box.addWidget(bar); box.addWidget(cancel)
    stop = threading.Event()
    window.stop, window.cancel_button = stop, cancel
    return window, status, bar, cancel, stop


def run_update(path, launch):
    app = QApplication([])
    app.setStyle("Fusion")
    window, status, bar, cancel, stop = build_update_window()
    worker = ApplyWorker(path, stop)
    # Keep worker/thread references alive for queued Qt signals.
    window.worker = worker

    def progress(text, current, total):
        status.setText(text)
        bar.setRange(0, 100 if total else 0)
        if total:
            bar.setValue(min(100, int(current * 100 / total)))
        if text == "Aplicando a atualização":
            cancel.setEnabled(False)

    def complete():
        from core.install_manager import installation_root
        try:
            launch(installation_root())
            window.running = False
            window.close()
        except Exception:
            failed("Atualização aplicada, mas não foi possível reabrir. Use o atalho do ULTRON.")

    def failed(message):
        window.running = False
        bar.setRange(0, 100); bar.setValue(0)
        status.setText(message + "\nA cópia anterior permanece disponível para recuperação.")
        cancel.setText("Fechar"); cancel.setEnabled(True)
        try:
            cancel.clicked.disconnect()
        except TypeError:
            pass
        cancel.clicked.connect(window.close)

    cancel.clicked.connect(stop.set)
    worker.progress.connect(progress); worker.succeeded.connect(complete); worker.failed.connect(failed)
    window.show()
    thread = threading.Thread(target=worker.run, daemon=False, name="ultron-apply-update")
    window.thread = thread
    thread.start()
    # Close requests during preparation cancel gracefully before files are swapped.
    app.aboutToQuit.connect(stop.set)
    return app.exec()
