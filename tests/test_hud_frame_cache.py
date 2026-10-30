"""Actual HUD/crystal painting through AST, without app imports or services."""
import ast
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtTest import QTest
from core.crystal_pulse import HoloCrystal
from core.hud_diagnostics import HudDiagnostics


def load_hud(root):
    tree = ast.parse((Path(__file__).resolve().parents[1] / "ui.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
             and node.name in {"C", "qcol", "HudCanvas"}]
    scope = dict(math=math, time=time, random=random, HoloAvatar=None, HoloEye=None,
                 HoloOrb=None, HoloCrystal=HoloCrystal, BASE_DIR=Path(root),
                 _D22G=SimpleNamespace(hud_start=time.perf_counter_ns, hud_draw_ns=[]))
    for module in (QtCore, QtGui, QtWidgets):
        scope.update({name: getattr(module, name) for name in dir(module)
                      if name.startswith("Q") or name.startswith("pyqt")})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "ui.HudCanvas", "exec"), scope)
    return scope


class HudFrameCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setStyle("Fusion")
        for name in ("consola.ttf", "segoeui.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(path))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.scope = load_hud(self.temp.name)
        fake_config = SimpleNamespace(get_hud_style=lambda: "crystal")
        with patch.dict(sys.modules, {"memory.config_manager": fake_config}):
            self.hud = self.scope["HudCanvas"]("unused.png", "ULTRON")
        self.hud._tmr.stop()
        self.hud.state = "LISTENING"
        self.host = QtWidgets.QWidget()
        self.host.setStyleSheet("background: black;")
        self.host.resize(540, 540)
        self.hud.setParent(self.host)
        self.hud.setGeometry(10, 10, 520, 520)
        self.host.show()
        QTest.qWait(30)

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_unpaced_repaints_restore_crystal_without_new_frames(self):
        before = self.hud.grab().toImage()
        frames = self.hud._fps_frames
        image = self.hud._frame_image
        for _ in range(6):
            self.hud.repaint()
        after = self.hud.grab().toImage()
        self.assertEqual(before, after)
        self.assertIs(self.hud._frame_image, image)
        self.assertEqual(self.hud._fps_frames, frames)
        self.assertGreater(self.hud._paint_skips, 0)
        # A missing draw would leave the all-black parent visible.
        self.assertTrue(any(before.pixelColor(x, y).red() > 40
                            for y in range(80, 430, 8) for x in range(120, 400, 8)))
        self.assertFalse((Path(self.temp.name) / "logs").exists())
        button = self.hud._fps_button.geometry()
        dpr = before.devicePixelRatioF()
        self.assertGreater(before.pixelColor(round(button.x() * dpr),
                                            round(button.center().y() * dpr)).red(), 30)

    def test_hover_and_tooltip_keep_crystal_visible(self):
        tick = self.hud._tick
        baseline = self.hud.grab().toImage().copy(70, 90, 380, 330)
        for point in (QtCore.QPoint(260, 230), self.hud._fps_button.geometry().center(),
                      QtCore.QPoint(260, 230)):
            QTest.mouseMove(self.hud, point)
            QTest.qWait(20)
            self.assertEqual(self.hud.grab().toImage().copy(70, 90, 380, 330), baseline)
        self.assertEqual(self.hud._tick, tick)

    def test_paced_frame_advances_once_and_reuses_allocation(self):
        image = self.hud._frame_image
        frames = self.hud._fps_frames
        self.hud._step()
        self.app.processEvents()
        self.assertIs(self.hud._frame_image, image)
        self.assertEqual(self.hud._fps_frames, frames + 1)
        self.hud.grab()
        self.assertEqual(self.hud._fps_frames, frames + 1)

    def test_fps_control_keeps_single_shared_timer_and_switches_target(self):
        self.assertEqual(len(self.hud.findChildren(QtCore.QTimer)), 1)
        QTest.mouseClick(self.hud._fps_button, QtCore.Qt.MouseButton.LeftButton)
        self.assertEqual(self.hud._fps_target, 60)
        self.hud._tmr.stop()
        self.assertIn("60", self.hud._fps_button.text())
        QTest.mouseClick(self.hud._fps_button, QtCore.Qt.MouseButton.LeftButton)
        self.assertEqual(self.hud._fps_target, 47)
        self.hud._tmr.stop()

    def test_resize_dpr_and_theme_invalidate_cache(self):
        original = self.hud._frame_image
        self.hud.resize(501, 509)
        self.hud.grab()
        self.assertIsNot(original, self.hud._frame_image)
        self.assertEqual(self.hud._frame_image.width(), math.ceil(501 * self.hud.devicePixelRatioF()))
        frames = self.hud._fps_frames
        self.scope["C"].PRI = "#ffffff"
        self.hud.grab()
        self.assertEqual(self.hud._fps_frames, frames + 1)


class HudDiagnosticsTests(unittest.TestCase):
    def test_budget_modes_cache_and_suspension_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as folder:
            probe = HudDiagnostics(Path(folder) / "hud.csv")
            for target in (47, 60):
                for frame in range(101):
                    now = frame / target
                    probe.tick(now, target, .2, 0)
                    probe.frame(now, target, 2.0, frame == 0, 1048576)
                    probe.blit(target, .1, False)
                probe.blit(target, .1, True)
            rows = [dict(zip(probe.FIELDS, row)) for row in probe.rows()]
            for row, target in zip(rows, (47, 60)):
                self.assertAlmostEqual(row["effective_fps"], target, places=2)
                self.assertEqual(row["gaps_over_1_5_budget"], 0)
                self.assertEqual(row["cache_reuses"], 1)
                self.assertEqual(row["cache_mib"], 1)
            probe.suspend()
            probe.tick(200, 60, 0, 0)
            probe.frame(200, 60, 2, False, 1048576)
            self.assertEqual(len(probe.buckets[60]["frames"]), 100)
            probe.frame(200.1, 60, 4, False, 1048576)
            self.assertEqual(list(probe.rows())[-1][8], 1)
            self.assertFalse(probe.path.exists())
            probe.flush()
            self.assertTrue(probe.path.read_text().startswith("time,target_fps,"))
            self.assertFalse(probe.buckets)

    def test_sample_memory_is_bounded(self):
        probe = HudDiagnostics("unused.csv")
        for i in range(5000):
            probe.tick(i / 60, 60, 0, 0)
            probe.frame(i / 60, 60, 1, False, 100)
            probe.blit(60, .1, True)
        self.assertLessEqual(len(probe.buckets[60]["frames"]), 4096)
        self.assertLessEqual(len(probe.buckets[60]["blit"]), 4096)


if __name__ == "__main__":
    unittest.main()
