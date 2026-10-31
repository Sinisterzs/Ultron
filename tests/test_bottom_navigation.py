"""Qt dock regression tests without importing main/ui or starting services."""
import ast
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtTest import QTest
from ui_sidebar import BottomNavBar


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        from PyQt6.QtGui import QFontDatabase, QFont
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "seguisym.ttf", "consola.ttf"):
            if (fonts/name).is_file():
                QFontDatabase.addApplicationFont(str(fonts/name))
        cls.app.setFont(QFont("Segoe UI", 10))
        tree = ast.parse((Path(__file__).resolve().parents[1] / "ui.py").read_text(encoding="utf-8"))
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
        method = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == "_place_drawer")
        scope = {"QPoint": QPoint}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "ui._place_drawer", "exec"), scope)
        cls.place_drawer = staticmethod(scope["_place_drawer"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ULTRON_DATA_DIR": self.temp.name})
        self.env.start()
        self.host = QWidget()
        self.host.resize(1000, 700)
        self.host.setStyleSheet("background: black; color: #eeeeee;")
        self.nav = BottomNavBar(parent=self.host)
        self.nav.update_viewport_width(1000)
        self.nav.setGeometry(0, 596, 1000, 104)
        self.drawer = QWidget(self.host)
        self.drawer.setStyleSheet("background: #100004; color: #eeeeee; border: 1px solid #a00020;")
        layout = QVBoxLayout(self.drawer)
        for text in ("CONTROLES", "FULLSCREEN [F11]", "WAKE WORD", "PUSH TO TALK", "HUD"):
            layout.addWidget(QLabel(text))
        self.drawer.hide()
        self.context = SimpleNamespace(_bottom_nav=self.nav, _side_rail=self.nav, _ctrl_drawer=self.drawer)
        self.host.show()
        self.app.processEvents()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.app.processEvents()
        self.env.stop()
        self.temp.cleanup()

    def click_cell(self, name):
        from ui_sidebar import PAGES
        view = self.nav._view
        point = view._cell(PAGES.index(name)).center().toPoint()
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()

    def test_settings_navigation_never_reemits_compatibility_click(self):
        calls = []
        pages = []
        def legacy_click(checked):
            calls.append(checked)
            if len(calls) < 3:
                self.nav.request_page("Ajustes")
        self.nav.buttons["Ajustes"].clicked.connect(legacy_click)
        self.nav.pageRequested.connect(pages.append)
        self.click_cell("Ajustes")
        self.assertEqual(pages, ["Ajustes"])
        self.assertEqual(calls, [])
        self.assertTrue(self.nav.buttons["Ajustes"].isChecked())
        self.nav.request_page("Ajustes")
        self.assertEqual(pages, ["Ajustes", "Ajustes"])

    def test_controls_click_opens_then_closes_visible_panel(self):
        states = []
        def toggle(checked):
            states.append(checked)
            self.place_drawer(self.context, self.drawer, 0)
            self.drawer.setVisible(checked)
            self.drawer.raise_()
        self.nav.buttons["Controles"].clicked.connect(toggle)
        self.click_cell("Controles")
        self.assertTrue(self.drawer.isVisible())
        self.assertTrue(self.host.rect().contains(self.drawer.geometry()))
        self.assertLess(self.drawer.geometry().bottom(), self.nav.popup_anchor("Controles", self.host).y())
        self.click_cell("Controles")
        self.assertFalse(self.drawer.isVisible())
        self.assertEqual(states, [True, False])

    def test_panel_stays_inside_resized_window(self):
        for width, height in ((700, 450), (1000, 700), (1600, 900)):
            self.host.resize(width, height)
            self.nav.update_viewport_width(width)
            self.nav.setGeometry(0, height-104, width, 104)
            self.app.processEvents()
            self.place_drawer(self.context, self.drawer, 0)
            self.assertTrue(self.host.rect().contains(self.drawer.geometry()), (width, height))
