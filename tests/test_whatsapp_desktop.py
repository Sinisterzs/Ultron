import builtins
from collections import Counter
import threading
import unittest
from unittest.mock import Mock, patch

from core import whatsapp_desktop as wa
from actions import send_message as action


class FakeUI:
    def __init__(self, opened=True, confirm=True):
        self.opened = opened
        self.confirm = confirm
        self.sent = 0
        self.launches = 0
        self.fields = {"search": "", "composer": ""}

    def detect(self):
        return self.opened

    def launch(self):
        self.launches += 1
        self.opened = True

    def focus(self):
        pass

    def search_control(self):
        return "search"

    def replace_text(self, control, text):
        self.fields[control] = text

    def read_edit(self, control):
        return self.fields[control]

    def contact(self, receiver):
        return receiver

    def open_contact(self, control):
        pass

    def correct_conversation(self, receiver):
        return True

    def composer(self):
        return "composer"

    def outgoing(self, message):
        return Counter({False: 1 + (self.sent if self.confirm else 0)})

    def send_control(self):
        return "button"

    def send_once(self, button, composer):
        self.sent += 1


class WhatsAppTests(unittest.TestCase):
    def setUp(self):
        wa._recent.clear()
        self.timeouts = wa.Timeouts(opening=0.1, conversation=0.1, input=0.1,
                                    confirmation=0.1, total=1, poll=0.01)
        self.logs = []
        self._env_patch = patch.dict("os.environ", {"MARK_LVI_WA_BACKEND": "desktop"})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()

    def run_ui(self, ui):
        return wa.run("Alice", "Olá", ui, wa.Operation(), self.timeouts, self.logs.append)

    def test_open_reused_and_confirmed_not_delivered(self):
        ui = FakeUI()
        result = self.run_ui(ui)
        self.assertTrue(result.startswith("status=done "))
        self.assertIn("delivery_confirmed=false", result)
        self.assertEqual(ui.launches, 0)
        self.assertEqual(ui.sent, 1)
        self.assertEqual(len(self.logs), 5)

    def test_closed_launches_once(self):
        ui = FakeUI(opened=False)
        self.assertTrue(self.run_ui(ui).startswith("status=done "))
        self.assertEqual(ui.launches, 1)

    def test_contact_not_found(self):
        ui = FakeUI()
        ui.contact = lambda receiver: None
        self.assertTrue(self.run_ui(ui).startswith("status=failed "))
        self.assertEqual(ui.sent, 0)

    def test_launch_failure(self):
        ui = FakeUI(opened=False)
        ui.launch = Mock(side_effect=OSError("not installed"))
        self.assertIn("not installed", self.run_ui(ui))
        self.assertEqual(ui.sent, 0)

    def test_unconfirmed_and_old_identical_message(self):
        ui = FakeUI(confirm=False)
        self.assertTrue(self.run_ui(ui).startswith("status=unverified "))
        self.assertEqual(ui.sent, 1)

    def test_startup_timeout(self):
        ui = FakeUI(opened=False)
        ui.launch = lambda: None
        self.assertTrue(self.run_ui(ui).startswith("status=failed "))
        self.assertEqual(ui.sent, 0)

    def test_existing_draft_preserved(self):
        ui = FakeUI()
        ui.fields['composer'] = 'draft'
        self.assertIn('existing draft', self.run_ui(ui))
        self.assertEqual(ui.fields['composer'], 'draft')
        self.assertEqual(ui.sent, 0)

    def test_ambiguous_contact(self):
        ui = FakeUI()
        ui.contact = Mock(side_effect=wa.UnsafeUI('ambiguous'))
        self.assertIn('ambiguous', self.run_ui(ui))
        self.assertEqual(ui.sent, 0)

    def test_exception_after_click_never_retries(self):
        ui = FakeUI()
        def click(*args):
            ui.sent += 1
            raise RuntimeError('provider disconnected')
        ui.send_once = click
        self.assertTrue(self.run_ui(ui).startswith('status=unverified '))
        self.assertEqual(ui.sent, 1)

    def test_driver_import_failure_no_blind_fallback(self):
        original = builtins.__import__
        def fail(name, *args, **kwargs):
            if name == 'core.whatsapp_desktop':
                raise ImportError('missing driver')
            return original(name, *args, **kwargs)
        with patch.object(action.sys, 'platform', 'win32'), patch('builtins.__import__', side_effect=fail), patch.object(action, '_desktop_send') as blind:
            result = action._send_whatsapp('Alice', 'Olá')
        self.assertTrue(result.startswith('status=failed '))
        blind.assert_not_called()

    def test_duplicate_suppressed(self):
        ui = FakeUI(confirm=False)
        factory = Mock(return_value=ui)
        first = wa.send('Alice', 'Olá', ui_factory=factory, timeouts=self.timeouts, logger=self.logs.append)
        second = wa.send('Alice', 'Olá', ui_factory=factory, timeouts=self.timeouts, logger=self.logs.append)
        self.assertTrue(first.startswith('status=unverified '))
        self.assertIn('duplicate_suppressed=true', second)
        self.assertEqual(ui.sent, 1)
        self.assertEqual(factory.call_count, 1)

    def test_factory_failure(self):
        result = wa.send('Alice', 'Olá', ui_factory=Mock(side_effect=ImportError('pywinauto')), logger=self.logs.append)
        self.assertTrue(result.startswith('status=failed '))

    def test_overall_timeout_cancels_late_send(self):
        release = threading.Event()
        exited = threading.Event()
        ui = FakeUI()
        def factory():
            release.wait(1)
            exited.set()
            return ui
        result = wa.send('Alice', 'Olá', ui_factory=factory,
                         timeouts=wa.Timeouts(total=0.01), logger=self.logs.append)
        self.assertTrue(result.startswith('status=failed '))
        release.set()
        self.assertTrue(exited.wait(1))
        self.assertTrue(wa._lock.acquire(timeout=1))
        wa._lock.release()
        self.assertEqual(ui.sent, 0)

    def test_agent_receives_final_result(self):
        from core.action_loader import _call_handler
        expected = 'status=done action=send_message delivery_confirmed=false'
        with patch.object(action.sys, 'platform', 'win32'), patch.object(wa, 'send', return_value=expected):
            result = _call_handler(action.send_message,
                                   {'receiver': 'Alice', 'message_text': 'Olá', 'platform': 'WhatsApp'}, {})
        self.assertEqual(result, expected)

    def test_other_platform_keeps_background_flow(self):
        with patch.object(action, '_PYAUTOGUI', True), patch.object(action.threading, 'Thread') as thread:
            result = action.send_message({'receiver': 'Alice', 'message_text': 'Olá', 'platform': 'Telegram'})
        self.assertTrue(result.startswith('status=started '))
        thread.return_value.start.assert_called_once()

    def test_native_control_fallback_without_uia_tree(self):
        ui = object.__new__(wa.WindowsUI)
        original = Mock(handle=123)
        native = Mock()
        ui.window, ui.backend = original, 0
        ui.operation = None
        ui.logger = lambda text: None
        ui._controls = Mock(return_value=[])
        ui._desktops = [Mock(), Mock()]
        ui._desktops[1].window.return_value.wrapper_object.return_value = native
        ui._wrap_handle = Mock(return_value=native)
        ui._unique = Mock(return_value='native-search')
        self.assertEqual(ui.search_control(), 'native-search')
        self.assertIs(ui.window, native)

    def test_unavailable_evidence_returns_without_confirmation_wait(self):
        ui = FakeUI()
        ui.outgoing = lambda message: None
        result = self.run_ui(ui)
        self.assertIn('evidence is not exposed', result)
        self.assertTrue(result.startswith('status=unverified '))
        self.assertEqual(ui.sent, 1)

    def test_wrong_conversation_never_sends(self):
        ui = FakeUI()
        ui.correct_conversation = lambda receiver: False
        self.assertTrue(self.run_ui(ui).startswith('status=failed '))
        self.assertEqual(ui.sent, 0)

    def test_cancelled_operation_never_sends(self):
        ui = FakeUI()
        operation = wa.Operation()
        operation.cancelled.set()
        result = wa.run('Alice', 'Olá', ui, operation, self.timeouts, self.logs.append)
        self.assertTrue(result.startswith('status=failed '))
        self.assertEqual(ui.sent, 0)

    def test_concurrent_operation_is_not_started(self):
        factory = Mock()
        wa._lock.acquire()
        try:
            result = wa.send('Alice', 'Olá', ui_factory=factory, logger=self.logs.append)
        finally:
            wa._lock.release()
        self.assertTrue(result.startswith('status=failed '))
        factory.assert_not_called()

    def test_receipt_changes_on_old_message_are_not_new_send_evidence(self):
        ui = FakeUI()
        ui.outgoing = Mock(side_effect=[Counter({False: 1}), Counter({True: 1})])
        self.assertTrue(self.run_ui(ui).startswith('status=unverified '))
        self.assertEqual(ui.sent, 1)

    def test_native_control_type_without_uia_property(self):
        control = Mock()
        control.element_info = object()
        control.friendly_class_name.return_value = 'Edit'
        self.assertEqual(wa.WindowsUI._kind(control), 'Edit')

    def test_timeout_after_send_keeps_lock_and_returns_unverified(self):
        release = threading.Event()
        ui = FakeUI()
        def click(*args):
            ui.sent += 1
            release.wait(1)
        ui.send_once = click
        result = wa.send('Alice', 'Olá', ui_factory=lambda: ui,
                         timeouts=wa.Timeouts(total=0.05), logger=self.logs.append)
        try:
            self.assertTrue(result.startswith('status=unverified '))
            self.assertTrue(wa._lock.locked())
            self.assertEqual(ui.sent, 1)
        finally:
            release.set()
            self.assertTrue(wa._lock.acquire(timeout=1))
            wa._lock.release()
        again = wa.send('Alice', 'Olá', ui_factory=Mock(), logger=self.logs.append)
        self.assertIn('duplicate_suppressed=true', again)


class QueryRegressionTests(unittest.TestCase):
    def ui(self):
        ui = object.__new__(wa.WindowsUI)
        ui.operation = wa.Operation()
        ui.logger = Mock()
        ui.backend = 0
        return ui

    def control(self, runtime, kind='Edit', name='Pesquisar ou começar uma nova conversa'):
        c = Mock(handle=0)
        c.element_info.runtime_id = runtime
        c.element_info.control_type = kind
        c.window_text.return_value = name
        c.is_visible.return_value = True
        c.is_enabled.return_value = True
        c.parent.return_value.children.return_value = [
            self.simple('Tab', (100,)), self.simple('Button', (101,))]
        return c

    def simple(self, kind, runtime):
        c = Mock(handle=0)
        c.element_info.control_type = kind
        c.element_info.runtime_id = runtime
        return c

    def test_eighty_references_are_one_identity(self):
        ui = self.ui()
        controls = [self.control((42, 1)) for _ in range(80)]
        self.assertEqual(len(ui._deduplicate(controls)), 1)

    def test_identity_is_not_cached_between_queries(self):
        ui = self.ui()
        first, second = self.control((42,)), self.control((42,))
        self.assertIs(ui._deduplicate([first])[0], first)
        self.assertIs(ui._deduplicate([second])[0], second)

    def test_two_real_searches_are_rejected(self):
        ui = self.ui()
        ui._controls = Mock(return_value=[self.control((1,)), self.control((2,))])
        with self.assertRaises(wa.UnsafeUI):
            ui.search_control()

    def test_chat_search_not_conversation_search(self):
        ui = self.ui()
        chat = self.control((1,))
        internal = self.control((2,), name='Pesquisar')
        ui._controls = Mock(return_value=[internal, chat])
        self.assertIs(ui.search_control(), chat)

    def test_root_resolution_deduplicates_document(self):
        ui = self.ui()
        root = self.control((1,), kind='Pane')
        doc = self.control((2,), kind='Document')
        root.children.return_value = [doc] * 80
        ui.window = root
        self.assertIs(ui._document(), doc)
        doc.children.assert_not_called()

    def test_root_resolution_refuses_two_documents(self):
        ui = self.ui()
        ui.window = self.control((1,), kind='Pane')
        ui.window.children.return_value = [self.control((2,), kind='Document'),
                                           self.control((3,), kind='Document')]
        with self.assertRaises(wa.UnsafeUI):
            ui._document()

    def test_new_document_resolved_each_query(self):
        ui = self.ui()
        ui.window = self.control((1,), kind='Pane')
        first = self.control((2,), kind='Document')
        second = self.control((3,), kind='Document')
        ui.window.children.side_effect = [[first], [second]]
        self.assertIs(ui._document(), first)
        self.assertIs(ui._document(), second)

    def test_zero_budget_does_not_call_probe(self):
        probe = Mock()
        with self.assertRaises(TimeoutError):
            wa.wait_for(probe, 0, wa.Operation())
        probe.assert_not_called()

    def test_late_positive_is_rejected(self):
        with patch.object(wa.time, 'perf_counter', side_effect=[0, 0, 2]):
            with self.assertRaises(TimeoutError):
                wa.wait_for(lambda: True, 1, wa.Operation())

    def test_late_exception_reports_deadline(self):
        with patch.object(wa.time, 'perf_counter', side_effect=[0, 0, 2]):
            with self.assertRaises(TimeoutError):
                wa.wait_for(Mock(side_effect=wa.UnsafeUI('ambiguous')), 1, wa.Operation())

    def test_query_checks_after_native_return(self):
        operation = wa.Operation()
        operation.deadline = 1
        with patch.object(wa.time, 'perf_counter', side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                operation.query(lambda: True)

    def test_query_expired_never_started(self):
        operation = wa.Operation()
        operation.deadline = 1
        probe = Mock()
        with patch.object(wa.time, 'perf_counter', return_value=2):
            with self.assertRaises(TimeoutError):
                operation.query(probe)
        probe.assert_not_called()

    def test_progress_does_not_print_started_result(self):
        with patch.object(action.sys, 'platform', 'win32'), patch.object(wa, 'send', return_value='status=failed action=send_message'), patch('builtins.print') as output:
            result = action.send_message({'receiver': 'Test', 'message_text': 'Test', 'platform': 'WhatsApp'})
        self.assertTrue(result.startswith('status=failed'))
        self.assertFalse(any('status=started' in str(call) for call in output.call_args_list))


if __name__ == '__main__':
    unittest.main()