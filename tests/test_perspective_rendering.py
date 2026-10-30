"""Exercise the real perspective renderer without importing the application."""
import ast
import math
import os
from pathlib import Path
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout
from PyQt6.QtTest import QTest


def load_classes():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "ui.py").read_text(encoding="utf-8"))
    names = {"C", "qcol", "LogWidget", "HoloFrame", "CornerAnchorButton", "PerspectiveSideView"}
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    scope = {"math": math, "time": time}
    for module in (QtCore, QtGui, QtWidgets):
        scope.update({name: getattr(module, name) for name in dir(module) if name.startswith("Q") or name.startswith("pyqt")})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "ui.perspective", "exec"), scope)
    return scope


class PaintedLabel(QLabel):
    paints = 0

    def paintEvent(self, event):
        self.paints += 1
        super().paintEvent(event)


class PerspectiveRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("consola.ttf", "segoeui.ttf"):
            if (fonts / name).is_file():
                QtGui.QFontDatabase.addApplicationFont(str(fonts / name))
        cls.classes = load_classes()

    def setUp(self):
        self.panel = self.classes["HoloFrame"]("right")
        self.layout = QVBoxLayout(self.panel)
        self.header = PaintedLabel("ULTRON / ATIVIDADE")
        self.header.setStyleSheet("color: #ff3344; background: transparent")
        self.header.setFixedHeight(65)
        self.layout.addWidget(self.header)
        self.log = self.classes["LogWidget"]()
        self.layout.addWidget(self.log)
        self.button = self.classes["CornerAnchorButton"]("MICROFONE")
        self.button.setFixedHeight(45)
        self.layout.addWidget(self.button)
        base = self.classes["PerspectiveSideView"]

        class MeasuredView(base):
            def _render_scene_region(view, image, dirty, source, w, h):
                view.patches.append(QtCore.QRect(dirty))
                super()._render_scene_region(image, dirty, source, w, h)

        self.view = MeasuredView(self.panel, "right")
        self.view.patches = []
        self.view.resize(321, 641)
        self.view.show()
        self.flush()

    def flush(self):
        QTest.qWait(40)

    def tearDown(self):
        self.view.release_embedded_widgets()
        self.assertIsNone(self.view._scene_image)
        self.view.close()
        self.view.deleteLater()
        self.flush()

    def reference(self):
        """Full scene render, independent of the retained output/patch path."""
        vp = self.view.viewport()
        image = QImage(math.ceil(vp.width() * 1.5), math.ceil(vp.height() * 1.5),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(1.5)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.TextAntialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        painter.scale(image.width() / vp.width() / 1.5, image.height() / vp.height() / 1.5)
        self.view.scene().render(painter, QRectF(vp.rect()),
                                 self.view.mapToScene(vp.rect()).boundingRect(),
                                 Qt.AspectRatioMode.IgnoreAspectRatio)
        painter.end()
        return image

    def assert_matches_full_render(self):
        actual = self.view._scene_image
        expected = self.reference()
        self.assertEqual(actual, expected, "retained image differs from full rendering")

    def test_typing_reuses_image_and_skips_unrelated_header(self):
        image = self.view._scene_image
        self.view.patches.clear()
        self.header.paints = 0
        self.log.append_log("ultron: Mensagem com acentos e quebra automática. " * 8)
        for frame in range(1, 31):
            self.log._step(self.log._typing_started + frame / 60)
            self.flush()
        self.assertIs(self.view._scene_image, image)
        self.assertTrue(self.view.patches)
        self.assertEqual(self.header.paints, 0)
        self.assert_matches_full_render()

    def test_partial_exposure_reuses_native_pixels_and_preserves_output(self):
        self.header.paints = 0
        image = self.view._scene_image
        self.view.patches.clear()
        self.view.viewport().update(QtCore.QRect(95, 150, 75, 45))
        self.flush()
        self.assertIs(self.view._scene_image, image)
        self.assertEqual(self.header.paints, 0)
        self.assertTrue(self.view.patches)
        self.assertTrue(all(p.height() < 60 for p in self.view.patches))
        self.assert_matches_full_render()

    def test_clicks_use_the_original_transformed_proxy(self):
        clicked = []
        self.button.clicked.connect(lambda: clicked.append(True))
        local = self.button.mapTo(self.panel, self.button.rect().center())
        point = self.view.mapFromScene(self.view._proxy.mapToScene(QtCore.QPointF(local)))
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.flush()
        self.assertEqual(clicked, [True])
        self.assertIs(self.view._proxy.widget(), self.panel)

    def test_left_perspective_still_matches_full_composition(self):
        self.view._side = "left"
        self.view._update_geometry()
        self.flush()
        self.log.setPlainText("Painel esquerdo\n" * 15)
        self.flush()
        self.assert_matches_full_render()

    def test_wrapping_scroll_clear_and_selection_match_full_render(self):
        for text in ("Linha curta", "texto longo com acentuação e espaços " * 15,
                     "\n".join(f"Linha {i}" for i in range(75))):
            self.log.append_log(text)
            self.log._step(self.log._typing_started + len(text) * .006)
            self.flush()
            self.assert_matches_full_render()
            self.log._typing = False
        self.log.verticalScrollBar().setValue(0)
        self.flush()
        self.assert_matches_full_render()
        self.log.selectAll()
        self.flush()
        self.assert_matches_full_render()
        self.log.clear()
        self.flush()
        self.assert_matches_full_render()

    def test_resize_theme_and_hover_invalidate_visible_pixels(self):
        old = self.view._scene_image
        self.view.resize(367, 703)
        self.flush()
        self.assertIsNot(self.view._scene_image, old)
        self.assert_matches_full_render()
        self.log.setStyleSheet("QTextEdit { color: white; background: #220008; }")
        self.flush()
        self.assert_matches_full_render()
        self.button.hover_progress = .75
        self.flush()
        self.assert_matches_full_render()


if __name__ == "__main__":
    unittest.main()
