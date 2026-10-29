"""Render the onboarding draft without importing main/ui or saving configuration."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtGui import QFontDatabase, QFont
from ui_setup import SetupOverlay


def main():
    app = QApplication([])
    # The offscreen Windows platform may not discover native fonts itself.
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ["segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"]:
        if (fonts / name).is_file():
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    window = SetupOverlay(preview=True)
    window.resize(960, 660)
    # Only synthetic display values; the wizard is never submitted.
    window._key_input.setText("visual-preview-not-a-real-api-key")
    window.user_name.setText("Você")
    output = ROOT / "installer/previews"
    output.mkdir(parents=True, exist_ok=True)
    window.show()
    for index, name in enumerate(["01-boas-vindas", "02-inteligencia", "03-integracoes", "04-concluir"]):
        window._index = index
        window._display()
        app.processEvents()
        path = output / f"{name}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError("Could not save preview")
        print(path)
    window.pages.setCurrentIndex(window._preparation_page_index)
    window.progress_box.show(); window.cancel.show()
    window._on_progress("Prévia visual • baixando componentes do aplicativo", 46, 100)
    window.next.setText("Preparando…"); window.next.setEnabled(False)
    app.processEvents()
    window.grab().save(str(output / "05-preparacao.png"))
    from ui_updates import UpdateToast
    from core.updates import Release
    host = QWidget(); host.resize(1000, 650); host.setStyleSheet("background:#000000;")
    title = QLabel("PRÉVIA DO AVISO — SEM CONSULTA DE REDE", host)
    title.move(28, 26); title.setStyleSheet("color:#60141f;font:12px 'Segoe UI';")
    toast = UpdateToast(Release("1.1.0", "https://github.com/example/project/releases/tag/v1.1.0"), host)
    toast.move(host.width() - toast.width() - 20, host.height() - toast.height() - 80)
    host.show(); toast.show(); app.processEvents()
    host.grab().save(str(output / "06-aviso-atualizacao.png")); host.close()
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
