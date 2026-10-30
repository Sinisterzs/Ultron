"""Real Qt text batching without importing the application or starting services."""
import ast
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QTextDocument
from PyQt6.QtWidgets import QApplication, QTextEdit


class Clock(QObject):
    pacedFrame = pyqtSignal(float)


def load_log_class(path, clock):
    tree=ast.parse(Path(path).read_text(encoding="utf-8"))
    nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))
           and n.name in {"C","qcol","LogWidget"}]
    scope={"QTextEdit":QTextEdit,"QFont":QFont,"QBrush":QBrush,"QColor":QColor,
           "pyqtSignal":pyqtSignal,"QTimer":QTimer,
           "time":SimpleNamespace(perf_counter=lambda:clock.now)}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"ui.LogWidget","exec"),scope)
    return scope["LogWidget"]


class LogBatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.time=SimpleNamespace(now=100.0)
        cls.widget_class=load_log_class(Path(__file__).resolve().parents[1]/"ui.py",cls.time)

    def setUp(self):
        self.time.now=100.0
        self.log=self.widget_class()
        self.clock=Clock()
        self.log.bind_hud_clock(self.clock)
        self.completed=[];self.changes=[]
        self.log.entry_completed.connect(lambda *args:self.completed.append(args))
        self.log.textChanged.connect(lambda:self.changes.append(self.log.toPlainText()))

    def tearDown(self):
        self.log.close();self.log.deleteLater()
        self.app.processEvents()

    def frame(self,now):
        self.time.now=now
        self.clock.pacedFrame.emit(now)

    def test_typing_speed_and_one_document_change_per_frame(self):
        text="Mensagem de teste "+ "abc"*100
        for fps in (47,60):
            with self.subTest(fps=fps):
                self.log.clear();self.changes.clear();self.completed.clear()
                self.log._typing=False;self.log._entry_cursor=None
                self.time.now=100.0
                self.log.append_log(text)
                count=math.ceil(len(text)*.006*fps)
                for i in range(1,count+1):
                    now=100+i/fps
                    before=len(self.changes)
                    self.frame(now)
                    expected=min(len(text),int((i/fps+1e-9)/.006))
                    actual=self.log.toPlainText()
                    self.assertEqual(actual,text[:expected]+("\n" if expected==len(text) else ""))
                    self.assertLessEqual(len(self.changes)-before,1)
                self.assertEqual(len(self.completed),1)
                self.assertEqual(self.completed[0][0],text)
                self.assertLessEqual(len(self.changes),count)
                self.assertLess(len(self.changes),len(text)/2)

    def test_delayed_frame_catches_up_without_losing_characters(self):
        text="x"*100
        self.log.append_log(text)
        self.frame(100.006)
        self.assertEqual(self.log.toPlainText(),"x")
        self.frame(100.300)
        self.assertEqual(self.log.toPlainText(),"x"*50)
        self.assertEqual(len(self.changes),2)
        self.frame(100.600)
        self.assertEqual(self.log.toPlainText(),text+"\n")
        self.frame(100.610)
        self.assertEqual(len(self.completed),1)

    def test_queue_pause_order_and_activity_html_are_preserved(self):
        first="ultron: Olá! 🦾 <texto> & música\nOutra linha."
        second="you: Certo!"
        self.log._ai_name_lc="ultron"
        self.log.append_log(first);self.log.append_log(second)
        end=100+len(first)*.006
        self.frame(end)
        self.assertEqual(len(self.completed),1)
        self.assertEqual(self.completed[0][:2],(first,"Ultron"))
        doc=QTextDocument();doc.setHtml(self.completed[0][2])
        self.assertEqual(doc.toPlainText(),first)
        self.frame(end+.019)
        self.assertEqual(self.log.toPlainText(),first+"\n")
        self.frame(end+.026)
        self.assertEqual(self.log.toPlainText(),first+"\ny")
        self.frame(end+.020+len(second)*.006)
        self.assertEqual([x[0] for x in self.completed],[first,second])
        self.assertEqual(self.completed[1][1],"Você")
        self.assertEqual(self.log.toPlainText(),first+"\n"+second+"\n")

    def test_idle_frames_do_not_change_document_or_create_timer(self):
        self.frame(101)
        self.assertEqual(self.changes,[])
        self.assertEqual(self.log.findChildren(QTimer),[])

    def test_rebinding_clock_does_not_duplicate_or_keep_old_connection(self):
        self.log.bind_hud_clock(self.clock)
        self.assertEqual(self.clock.receivers(self.clock.pacedFrame),1)
        other=Clock()
        self.log.bind_hud_clock(other)
        self.assertEqual(self.clock.receivers(self.clock.pacedFrame),0)
        self.assertEqual(other.receivers(other.pacedFrame),1)

    def test_empty_entry_completes_once_and_queue_continues(self):
        self.log.append_log("");self.log.append_log("OK")
        self.frame(100.010)
        self.frame(100.042)
        self.assertEqual([x[0] for x in self.completed],["","OK"])
        self.assertEqual(self.log.toPlainText(),"\nOK\n")
