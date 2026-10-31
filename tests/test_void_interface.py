"""Offscreen unit tests for the D20 VOID OS interface and expanding side panels."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from installer.prepare_payload import payload_files
from ui_chat import HoloChat
from ui_core_status import CoreStatusPanel, derive_status, format_network_rate
from ui_news import NewsBriefingPanel
from ui_sidebar import BottomNavBar
from ui_titlebar import TitleBar
from ui_void_panels import VoidPrimaryPanel, VoidSubmenuDrawer, build_angular_polygon


class _FakeHudClock(QObject):
    pacedFrame = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.state = "LISTENING"
        self.muted = False
        self.speaking = False
        self._fps_reading = 60
        self._fps_target = 60
        self.now = 100.0

    def step(self, dt: float) -> None:
        self.now += dt
        self.pacedFrame.emit(self.now)


class VoidInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ULTRON_DATA_DIR": self.temp.name})
        self.env.start()

    def tearDown(self):
        self.app.processEvents()
        self.env.stop()
        self.temp.cleanup()

    def test_payload_allowlist_includes_ui_void_panels(self):
        root = Path(__file__).resolve().parents[1]
        rels = set(payload_files(root))
        self.assertIn("ui_void_panels.py", rels)

    def test_titlebar_renders_pure_black_with_crimson_corner_accents(self):
        host = QWidget()
        host.resize(980, 120)
        bar = TitleBar(host, QLabel("ULTRON"), QLabel("00:00:00"), QLabel("2026"))
        bar.setGeometry(0, 0, 980, TitleBar.BAR_HEIGHT)
        host.show()
        self.app.processEvents()

        img = bar.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        center_px = QColor(img.pixel(490, 17))
        self.assertEqual((center_px.red(), center_px.green(), center_px.blue()), (0, 0, 0))
        # Left top accent line sits around y=20..21, x=26..162
        line_px = QColor(img.pixel(60, 20))
        self.assertGreater(line_px.red(), 80)
        host.close()

    def test_core_telemetry_formats_network_throughput_and_preserves_3arg_compat(self):
        sys_txt, net_legacy, fps_txt = derive_status("LISTENING", 60, 60)
        self.assertEqual(sys_txt, "ONLINE")
        self.assertEqual(net_legacy, "STABLE")
        self.assertEqual(fps_txt, "60 FPS")

        self.assertEqual(format_network_rate(0.25), "256 KB/s")
        self.assertEqual(format_network_rate(2.4), "2.4 MB/s")
        _s, net_with_rate, _f = derive_status("SPEAKING", 59, 60, net_mbps=1.5)
        self.assertIn("STABLE", net_with_rate)
        self.assertIn("1.5 MB/s", net_with_rate)

        host = QWidget()
        host.resize(800, 400)
        anchor = QWidget(host)
        anchor.setGeometry(200, 60, 400, 260)
        hud = _FakeHudClock()
        panel = CoreStatusPanel(anchor, parent=host, net_provider=lambda: 0.5)
        panel.bind_hud_clock(hud)
        host.show()
        hud.step(0.016)
        self.app.processEvents()
        self.assertIn("ONLINE", panel.summary_text())
        self.assertIn("512 KB/s", panel.summary_text())
        self.assertIn("60 FPS", panel.summary_text())
        host.close()

    def test_expanding_side_panels_slide_reuse_close_and_create_zero_timers(self):
        host = QWidget()
        host.resize(1280, 760)
        host.setStyleSheet("background: #000000;")
        hud = _FakeHudClock()

        left = VoidPrimaryPanel(
            "left", "SYSTEM", ("IDENTITY", "CORE", "VOICE", "MEMORY", "PLUGINS"), parent=host
        )
        left.setGeometry(28, 72, 190, 560)

        right = VoidPrimaryPanel(
            "right", "INTERACTION", ("COMMANDS", "CHAT", "ACTIVITY", "TOOLS"), parent=host
        )
        right.setGeometry(1280 - 28 - 190, 72, 190, 560)

        sys_drawer = VoidSubmenuDrawer("left", "SYSTEM", anchor_panel=left, parent=host)
        sys_drawer.bind_hud_clock(hud)
        for sec in ("IDENTITY", "CORE", "VOICE", "MEMORY", "PLUGINS"):
            w = QWidget()
            QVBoxLayout(w).addWidget(QLabel(f"Section {sec}"))
            sys_drawer.add_section(sec, w)

        int_drawer = VoidSubmenuDrawer("right", "INTERACTION", anchor_panel=right, parent=host)
        int_drawer.bind_hud_clock(hud)
        for sec in ("COMMANDS", "CHAT", "ACTIVITY", "TOOLS"):
            w = QWidget()
            QVBoxLayout(w).addWidget(QLabel(f"Section {sec}"))
            int_drawer.add_section(sec, w)

        # Contract: zero independent QTimers inside primary panels or submenu drawers.
        for widget in (left, right, sys_drawer, int_drawer):
            self.assertEqual(widget.findChildren(QTimer), [])

        host.show()
        self.app.processEvents()

        # 1. Left submenu slides smoothly to the RIGHT over ~200 ms; SYSTEM stays visible.
        left.set_active_section("IDENTITY")
        sys_drawer.open_section("IDENTITY")
        hud.step(0.0)    # t = 0 ms
        hud.step(0.10)   # t = 100 ms (mid-slide)
        mid_w = sys_drawer.width()
        self.assertTrue(left.isVisible())
        self.assertTrue(sys_drawer.isVisible())
        self.assertGreater(mid_w, 20)
        self.assertLess(mid_w, sys_drawer.full_open_width())
        self.assertEqual(sys_drawer.x(), left.geometry().right() + 1 + VoidSubmenuDrawer.GAP)

        hud.step(0.12)   # t = 220 ms (complete)
        self.assertFalse(sys_drawer.is_animating())
        self.assertEqual(sys_drawer.width(), sys_drawer.full_open_width())

        # 2. Selecting another option reuses the open submenu without closing/re-animating.
        left.set_active_section("CORE")
        sys_drawer.open_section("CORE")
        self.assertFalse(sys_drawer.is_animating())
        self.assertEqual(sys_drawer.active_section(), "CORE")
        self.assertEqual(sys_drawer.width(), sys_drawer.full_open_width())
        self.assertIn("CORE", sys_drawer.header_label.text())
        self.assertTrue(left.button("CORE").isChecked())
        self.assertFalse(left.button("IDENTITY").isChecked())

        # 3. Right submenu slides smoothly to the LEFT; INTERACTION stays visible.
        right.set_active_section("COMMANDS")
        int_drawer.open_section("COMMANDS")
        hud.step(0.0)
        hud.step(0.10)
        right_anchor_edge = right.x() - VoidSubmenuDrawer.GAP
        self.assertTrue(right.isVisible())
        self.assertEqual(int_drawer.x() + int_drawer.width(), right_anchor_edge)
        hud.step(0.12)
        self.assertEqual(int_drawer.width(), int_drawer.full_open_width())

        # 4. Interior fill of both primary panel and submenu is pure #000000.
        left_img = left.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        px_left = QColor(left_img.pixel(left.width() // 2, left.height() - 40))
        self.assertEqual((px_left.red(), px_left.green(), px_left.blue()), (0, 0, 0))

        sub_img = sys_drawer.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        px_sub = QColor(sub_img.pixel(sys_drawer.width() // 2, sys_drawer.height() - 40))
        self.assertEqual((px_sub.red(), px_sub.green(), px_sub.blue()), (0, 0, 0))

        # 5. Clicking active item again (toggle_section) closes left submenu.
        still_open = sys_drawer.toggle_section("CORE")
        self.assertFalse(still_open)
        hud.step(0.0)
        hud.step(0.22)
        self.assertTrue(sys_drawer.isHidden())

        # 6. Clicking × button closes right submenu and emits closed signal.
        closed_events = []
        int_drawer.closed.connect(lambda: closed_events.append(True))
        QTest.mouseClick(int_drawer.close_button, Qt.MouseButton.LeftButton)
        hud.step(0.0)
        hud.step(0.22)
        self.assertTrue(closed_events)
        self.assertTrue(int_drawer.isHidden())

        # 7. Angular polygon inclines inward toward the crystal on both sides.
        poly_l = build_angular_polygon(200, 500, "left")
        poly_r = build_angular_polygon(200, 500, "right")
        self.assertGreater(poly_l.at(2).y(), poly_l.at(1).y())
        self.assertGreater(poly_r.at(1).y(), poly_r.at(2).y())

        host.close()

    def test_embedded_chat_stays_open_past_idle_timeout_and_emits_dialogue_signal(self):
        host = QWidget()
        host.resize(320, 420)
        lay = QVBoxLayout(host)
        hud = _FakeHudClock()
        chat = HoloChat(host, parent=host, embedded=True)
        chat.bind_hud_clock(hud)
        lay.addWidget(chat)
        arrived = []
        chat.dialogueArrived.connect(arrived.append)

        host.show()
        self.app.processEvents()

        chat.begin_entry("Status do sistema?", "Você")
        chat.update_entry("Status do sistema?", "Você", True)
        chat.begin_entry("Todos os subsistemas operacionais.", "Ultron")
        chat.update_entry("Todos os subsistemas operacionais.", "Ultron", True)
        self.assertEqual(arrived, ["Você", "Ultron"])

        # Advance 10 seconds — embedded chat must NOT auto-hide after 4s.
        for _ in range(25):
            hud.step(0.5)
        self.assertTrue(chat.isVisible())
        host.close()

    def test_docked_news_drawer_and_masked_void_dock_coexist_without_click_steal(self):
        host = QWidget()
        host.resize(1200, 760)
        anchor = QWidget(host)
        anchor.setGeometry(300, 60, 600, 540)

        news = NewsBriefingPanel(anchor, parent=host, docked=True, bottom_offset=58)
        nav = BottomNavBar(parent=host)
        nav.update_viewport_width(1200)
        nav.setGeometry(0, 760 - nav.height(), 1200, nav.height())
        nav._reposition()

        host.show()
        self.app.processEvents()

        self.assertTrue(news.isVisible())
        self.assertEqual(news.height(), NewsBriefingPanel.IDLE_H)
        # News drawer sits cleanly above the painted VOID DOCK mask
        dock_mask_bbox = nav.mask().boundingRect()
        dock_top_in_host = nav.y() + dock_mask_bbox.top()
        self.assertLess(news.geometry().bottom(), dock_top_in_host)

        # Clicking idle NEWS DRAWER expands it; hide_news returns it to compact pill.
        QTest.mouseClick(news, Qt.MouseButton.LeftButton, pos=QPoint(news.width() // 2, 20))
        self.app.processEvents()
        self.assertGreater(news.height(), NewsBriefingPanel.IDLE_H)
        news.hide_news()
        self.app.processEvents()
        self.assertTrue(news.isVisible())
        self.assertEqual(news.height(), NewsBriefingPanel.IDLE_H)

        host.close()


if __name__ == "__main__":
    unittest.main()
