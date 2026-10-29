"""Frozen entry point: splash and application always run in separate processes."""
from __future__ import annotations

import sys


def main():
    if "--preview-setup" in sys.argv:
        from PyQt6.QtWidgets import QApplication
        from ui_setup import SetupOverlay
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        window = SetupOverlay(preview=True)
        window.resize(960, 660)
        window.setWindowTitle("ULTRON — Prévia da primeira configuração")
        window.done.connect(lambda *_: window.show_error("Prévia: nenhum dado será salvo e o assistente não será iniciado."))
        window.show()
        return app.exec()
    if "--app" in sys.argv:
        from main import main as run_app
        from core.runtime_lock import application_lock
        with application_lock():
            run_app()
        return 0
    from launcher import main as run_launcher
    return run_launcher()


if __name__ == "__main__":
    raise SystemExit(main())
