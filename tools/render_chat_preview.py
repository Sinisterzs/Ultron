"""Render the implemented Qt chat/layout using isolated app components only."""
import ast
import argparse
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_hud_frame_cache import HudFrameCacheTests, QtCore, QtGui, QtWidgets
from ui_chat import HoloChat
from ui_theme import WidgetTheme
from ui_sidebar import BottomNavBar
from PyQt6 import sip


def add_panels(scope):
    tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
    classes = {"HoloFrame", "CornerAnchorButton", "PerspectiveSideView", "LogWidget",
               "FileDropZone", "_DropCanvas"}
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in classes]
    window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
    methods = [n for n in window.body if isinstance(n, ast.FunctionDef) and
               n.name in {"_build_left_panel", "_build_right_panel", "_build_input_row", "_style_mute_btn"}]
    scope["Path"] = Path
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "ui.panels", "exec"), scope)
    return methods


def render(output, width, height):
    fixture = HudFrameCacheTests()
    fixture.setUp()
    hud = fixture.hud
    scope = fixture.scope
    methods = add_panels(scope)
    cls = ast.ClassDef(name="PreviewWindow", bases=[ast.Name(id="QMainWindow", ctx=ast.Load())],
                       keywords=[], body=methods, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 "ui.preview_window", "exec"), scope)
    window = scope["PreviewWindow"]()
    window._muted = False
    for name in ("_send", "_do_interrupt", "_toggle_mute", "_on_file_selected"):
        setattr(window, name, lambda *args: None)
    window.resize(width, height)
    central = QtWidgets.QWidget()
    central.setStyleSheet("background: black;")
    window.setCentralWidget(central)
    root = QtWidgets.QVBoxLayout(central)
    root.setContentsMargins(0, 0, 0, 0)
    title = QtWidgets.QLabel("  ◇  ULTRON")
    title.setFixedHeight(36)
    title.setStyleSheet("color: #ff2034; font: bold 13px 'Segoe UI'; background: black;")
    root.addWidget(title)
    body = QtWidgets.QHBoxLayout()
    body.setContentsMargins(30, 12, 30, 92)
    body.setSpacing(24)
    left = window._build_left_panel()
    left_view = scope["PerspectiveSideView"](left, "left")
    left_view.setFixedWidth(220)
    body.addWidget(left_view)
    fixture.hud.setParent(None)
    stack = QtWidgets.QStackedWidget()
    stack.addWidget(hud)
    body.addWidget(stack, 5)
    right = window._build_right_panel()
    right_view = scope["PerspectiveSideView"](right, "right")
    right_view.setFixedWidth(320)
    body.addWidget(right_view)
    root.addLayout(body, 1)
    window.hud = hud
    chat = HoloChat(stack, accent=lambda: scope["C"].PRI, parent=central)
    chat.bind_hud_clock(hud)
    window._log.bind_hud_clock(hud)
    window._log.entry_started.connect(chat.begin_entry)
    window._log.entry_progress.connect(chat.update_entry)
    dock = BottomNavBar(parent=central)
    dock.update_viewport_width(width)
    dock.setGeometry(0, height - 90, width, 90)
    dock.bind_hud_clock(hud)
    theme = WidgetTheme(window, {key: value for key, value in vars(scope["C"]).items()
                                 if isinstance(value, str) and value.startswith("#")})
    theme.apply("#ff2034")
    window.show()
    chat.show()
    fixture.app.processEvents()
    chat.reposition()
    for category, text in (("Você", "You: Como ficou a nova interface?"),
                           ("Ultron", "ULTRON: Nossa conversa fica perto do cristal. Respostas longas ficam recolhidas para manter tudo compacto. Você pode expandir a mensagem quando quiser ler a resposta completa, sem aumentar o painel ou cobrir a tela.")):
        chat.begin_entry(text, category)
        chat.update_entry(text, category, True)
    from PyQt6.QtTest import QTest
    QTest.qWait(100)
    # Refresh the HUD once; its frame cache then survives snapshot repaints.
    hud._paint_permit = True
    hud.repaint()
    window.grab().save(str(output))
    with patch.object(chat, "_pointer_inside", return_value=False):
        chat._on_frame(chat._last_activity + chat.IDLE_SECONDS + .01)
    assert chat.isHidden()
    window.grab().save(str(output.with_stem(output.stem + "-idle")))
    assert not any(label.text() == "▸ ACTIVITY LOG" for label in right.findChildren(QtWidgets.QLabel))
    assert right.layout().itemAt(0).widget().text() == "▸ FILE UPLOAD"
    assert not window._log.isVisible()
    print("Rendered:", output, "chat:", chat.geometry().getRect())
    fixture.app.removeEventFilter(theme)
    left_view.release_embedded_widgets()
    right_view.release_embedded_widgets()
    window.close()
    sip.delete(window)
    fixture.tearDown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tools/reports/chat")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # BottomNavBar diagnostics and any component data stay in a disposable root.
    with tempfile.TemporaryDirectory() as folder:
        os.environ["ULTRON_DATA_DIR"] = folder
        HudFrameCacheTests.setUpClass()
        for width, height in ((1920, 1046), (1100, 720)):
            render(args.output / f"chat-{width}.png", width, height)


if __name__ == "__main__":
    main()
