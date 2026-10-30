"""Native compact-chat behavior without main/ui, audio or configuration."""
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtTest import QTest
from ui_chat import HoloChat
from ui_activity import ActivityPage
from test_log_batching import Clock, load_log_class


class HoloChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        for name in ("segoeui.ttf", "consola.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))

    def setUp(self):
        self.host = QWidget()
        self.host.resize(1200, 800)
        self.host.setStyleSheet("background: black;")
        self.chat = HoloChat(self.host)
        self.host.show()
        self.chat.show()
        QTest.qWait(20)

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.app.processEvents()

    def add(self, text, category="Ultron"):
        self.chat.begin_entry(text, category)
        self.chat.update_entry(text, category, True)
        QTest.qWait(10)

    def test_only_dialogue_is_visible_and_original_activity_contract_survives(self):
        clock = SimpleNamespace(now=100.0)
        cls = load_log_class(Path(__file__).resolve().parents[1] / "ui.py", clock)
        log = cls(self.host)
        log.hide()
        hud = Clock()
        log.bind_hud_clock(hud)
        activity = ActivityPage(self.host)
        activity.hide()
        log.entry_started.connect(self.chat.begin_entry)
        log.entry_progress.connect(self.chat.update_entry)
        log.entry_completed.connect(activity.add_entry)
        for text in ("SYS: Sistema pronto", "You: Olá!", "JARVIS: Olá, <texto> & 🦾!"):
            log.append_log(text)
            clock.now += 10
            hud.pacedFrame.emit(clock.now)
            clock.now += .021
            hud.pacedFrame.emit(clock.now)
        QTest.qWait(20)
        self.assertEqual(len(activity._entries), 3)
        self.assertEqual(len(self.chat._messages), 2)
        self.assertEqual(self.chat._messages[-1][1].text, "Olá, <texto> & 🦾!")
        self.assertEqual(self.chat._messages[-1][1].body.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(self.chat.findChildren(QTimer), [])

    def test_long_text_expands_inside_fixed_panel_and_remains_complete(self):
        height = self.chat.height()
        text = "JARVIS: " + "Resposta com acentuação e 🦾. " * 250
        self.add(text)
        bubble = self.chat._messages[-1][1]
        self.assertTrue(bubble.more.isVisible())
        self.assertLess(len(bubble.body.text()), 400)
        QTest.mouseClick(bubble.more, Qt.MouseButton.LeftButton)
        QTest.qWait(20)
        self.assertEqual(bubble.body.text(), text[len("JARVIS: "):])
        self.assertEqual(self.chat.height(), height)
        self.assertEqual(bubble.more.text(), "Ler menos")
        bubble.more.click()
        self.assertLess(len(bubble.body.text()), 400)

    def test_follow_pauses_when_reading_and_new_message_button_resumes(self):
        for i in range(12):
            self.add(f"JARVIS: Mensagem {i}. " + "Texto de exemplo. " * 8)
        bar = self.chat.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertEqual(bar.value(), bar.maximum())
        bar.setValue(0)
        self.assertFalse(self.chat._follow)
        self.add("JARVIS: Nova mensagem")
        self.assertEqual(bar.value(), 0)
        self.assertTrue(self.chat.new_messages.isVisible())
        self.chat.new_messages.click()
        QTest.qWait(20)
        self.assertEqual(bar.value(), bar.maximum())
        self.assertTrue(self.chat._follow)
        self.assertFalse(self.chat.new_messages.isVisible())

    def test_history_is_bounded_and_panel_tracks_parent(self):
        self.chat.MAX_MESSAGES = 5
        for i in range(8):
            self.add(f"You: Mensagem {i}", "Você")
        self.assertEqual(len(self.chat._messages), 5)
        for w, h in ((1200, 800), (420, 360), (300, 300)):
            self.host.resize(w, h)
            QTest.qWait(15)
            self.assertTrue(self.host.rect().contains(self.chat.geometry()))
            self.assertLessEqual(self.chat.width(), 280)
            self.assertLessEqual(self.chat.height(), 240)
        self.chat.minimize.click()
        self.assertEqual(self.chat.height(), 36)
        self.chat.minimize.click()
        self.assertGreater(self.chat.height(), 36)
        self.chat.on_page_changed(1)
        self.assertFalse(self.chat.isVisible())
        self.chat.on_page_changed(0)
        self.assertTrue(self.chat.isVisible())

    def test_narrow_window_uses_space_outside_crystal_canvas(self):
        anchor = QWidget(self.host)
        anchor.setGeometry(200, 20, 420, 600)
        overlay = HoloChat(anchor, parent=self.host)
        anchor.show()
        overlay.show()
        QTest.qWait(15)
        self.assertGreaterEqual(overlay.x(), anchor.geometry().right())
        self.assertTrue(self.host.rect().contains(overlay.geometry()))
        self.assertLessEqual(overlay.height(), 240)

    def test_idle_hides_after_four_seconds_and_new_dialogue_restores_history(self):
        clock = Clock()
        clock.speaking = False
        self.chat.bind_hud_clock(clock)
        with patch("ui_chat.time.perf_counter", return_value=100.0), \
                patch.object(self.chat, "_pointer_inside", return_value=False):
            self.add("JARVIS: Mensagem preservada")
            clock.pacedFrame.emit(103.99)
            self.assertTrue(self.chat.isVisible())
            clock.pacedFrame.emit(104.0)
            self.assertFalse(self.chat.isVisible())
            self.add("SYS: Isso não reabre o chat", "SYS")
            self.assertFalse(self.chat.isVisible())
            self.add("You: Nova mensagem", "Você")
            self.assertTrue(self.chat.isVisible())
            self.assertEqual(len(self.chat._messages), 2)
            self.assertEqual(self.chat.findChildren(QTimer), [])

    def test_speech_typing_and_child_interactions_restart_idle_deadline(self):
        clock = Clock()
        clock.speaking = True
        self.chat.bind_hud_clock(clock)
        self.chat.bind_hud_clock(clock)
        self.assertEqual(clock.receivers(clock.pacedFrame), 1)
        with patch.object(self.chat, "_pointer_inside", return_value=False):
            self.chat._last_activity = 100.0
            clock.pacedFrame.emit(110.0)
            self.assertTrue(self.chat.isVisible())
            clock.speaking = False
            clock.pacedFrame.emit(113.99)
            self.assertTrue(self.chat.isVisible())
            clock.pacedFrame.emit(114.0)
            self.assertFalse(self.chat.isVisible())
            with patch("ui_chat.time.perf_counter", return_value=120.0):
                self.chat.begin_entry("JARVIS: Digitando", "Ultron")
            clock.pacedFrame.emit(130.0)
            self.assertTrue(self.chat.isVisible())
            with patch("ui_chat.time.perf_counter", return_value=131.0):
                self.chat.update_entry("JARVIS: Digitando", "Ultron", True)
            with patch("ui_chat.time.perf_counter", return_value=134.0):
                self.chat.minimize.click()
            clock.pacedFrame.emit(137.99)
            self.assertTrue(self.chat.isVisible())
            clock.pacedFrame.emit(138.0)
            self.assertFalse(self.chat.isVisible())


if __name__ == "__main__":
    unittest.main()
