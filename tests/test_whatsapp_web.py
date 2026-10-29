"""Unit tests for WhatsApp Web driver (core/whatsapp_web.py).

Verifies strict DOM validation, recipient verification, no automatic retries,
deduplication lock, masked logs, and outcome differentiation without live network sends.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock, patch

from core import whatsapp_web as wa_web
from actions import send_message as action


class FakeLocator:
    def __init__(self, count_val=1):
        self._count = count_val
        self.clicked = 0
        self.filled = None
        self.pressed = []

    def count(self):
        return self._count

    def click(self):
        self.clicked += 1

    def fill(self, text):
        self.filled = text

    def press(self, key):
        self.pressed.append(key)


class FakePage:
    def __init__(self, eval_responses=None, locator_count=1):
        self.eval_responses = list(eval_responses or [])
        self.locator_obj = FakeLocator(count_val=locator_count)
        self.gotos = []

    def goto(self, url, **kwargs):
        self.gotos.append(url)

    def evaluate(self, script, *args):
        if self.eval_responses:
            return self.eval_responses.pop(0)
        return None

    def locator(self, selector):
        return self.locator_obj


class FakeSession:
    def __init__(self, page):
        self.page = page
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestWhatsAppWeb(unittest.TestCase):
    def setUp(self):
        wa_web._recent.clear()
        if wa_web._lock.locked():
            wa_web._lock.release()

    def test_reject_short_or_invalid_phone(self):
        result = wa_web.send("Alice", "Olá")
        self.assertIn("status=failed", result)
        self.assertIn("requires a full phone number with country code", result)
        self.assertIn("to=****", result)
        self.assertIn("send_attempted=false", result)

    def test_reject_unauthenticated_qr(self):
        page = FakePage(eval_responses=[
            None,  # block check
            True,  # is_qr check
        ])
        factory = lambda: FakeSession(page)
        with patch("time.sleep"):
            result = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=failed", result)
        self.assertIn("QR code", result)
        self.assertIn("to=...8888", result)
        self.assertIn("send_attempted=false", result)

    def test_abort_unconfirmed_recipient(self):
        page = FakePage(eval_responses=[
            None,   # block check
            False,  # is_qr check
            {"ok": False, "reason": "recipient_identity_unconfirmed_no_safe_evidence"},
        ])
        factory = lambda: FakeSession(page)
        with patch("time.sleep"):
            result = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=failed", result)
        self.assertIn("recipient_identity_unconfirmed_no_safe_evidence", result)
        self.assertIn("to=...8888", result)
        self.assertIn("send_attempted=false", result)
        self.assertEqual(page.locator_obj.clicked, 0)

    def test_abort_non_unique_composer_or_header(self):
        page = FakePage(eval_responses=[
            None,   # block check
            False,  # is_qr check
            {"ok": False, "reason": "header_not_unique (count=2)"},
        ])
        factory = lambda: FakeSession(page)
        with patch("time.sleep"):
            result = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=failed", result)
        self.assertIn("header_not_unique", result)
        self.assertIn("send_attempted=false", result)
        self.assertEqual(page.locator_obj.clicked, 0)

    def test_successful_send_observed(self):
        page = FakePage(eval_responses=[
            None,   # block check
            False,  # is_qr check
            {"ok": True, "baselineOutboundCount": 3},
            {"newOutboundCount": 4, "composeCleared": True},
        ])
        factory = lambda: FakeSession(page)
        with patch("time.sleep"):
            result = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=done", result)
        self.assertIn("verified=true", result)
        self.assertIn("evidence=new_outbound_message_node_in_dom", result)
        self.assertIn("delivery_confirmed=false", result)
        self.assertIn("to=...8888", result)
        self.assertEqual(page.locator_obj.clicked, 1)
        self.assertEqual(page.locator_obj.filled, "Oi")
        self.assertEqual(page.locator_obj.pressed, ["Enter"])

    def test_ambiguous_outcome_when_node_not_observed(self):
        page = FakePage(eval_responses=[
            None,
            False,
            {"ok": True, "baselineOutboundCount": 3},
            {"newOutboundCount": 3, "outboundIds": [], "composeCleared": True},
        ])
        factory = lambda: FakeSession(page)
        with patch("time.sleep"), patch("time.monotonic", side_effect=[0.0, 0.0, 7.0]):
            result = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=unverified", result)
        self.assertIn("send_attempted=true", result)
        self.assertIn("retry_safe=false", result)
        self.assertIn("delivery_confirmed=false", result)
        self.assertEqual(page.locator_obj.clicked, 1)

    def test_duplicate_suppression_and_no_retry(self):
        page = FakePage(eval_responses=[
            None,
            False,
            {"ok": True, "baselineOutboundCount": 1},
            {"newOutboundCount": 2, "composeCleared": True},
        ])
        factory = Mock(return_value=FakeSession(page))
        with patch("time.sleep"):
            first = wa_web.send("+5511999998888", "Oi", session_factory=factory)
            second = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=done", first)
        self.assertIn("duplicate_suppressed=true", second)
        self.assertEqual(factory.call_count, 1)

    def test_duplicate_suppression_with_casing_and_whitespace(self):
        page = FakePage(eval_responses=[
            None,
            False,
            {"ok": True, "baselineOutboundCount": 1},
            {"newOutboundCount": 2, "composeCleared": True},
        ])
        factory = Mock(return_value=FakeSession(page))
        with patch("time.sleep"):
            first = wa_web.send("+5511999998888", "Teste de integração", session_factory=factory)
            second = wa_web.send("+5511999998888", "  teste de Integração \n", session_factory=factory)
        self.assertIn("status=done", first)
        self.assertIn("duplicate_suppressed=true", second)
        self.assertEqual(factory.call_count, 1)

    def test_explicit_force_resend_bypasses_cache(self):
        page = FakePage(eval_responses=[
            None,
            False,
            {"ok": True, "baselineOutboundCount": 1},
            {"newOutboundCount": 2, "composeCleared": True},
            None,
            False,
            {"ok": True, "baselineOutboundCount": 2},
            {"newOutboundCount": 3, "composeCleared": True},
        ])
        factory = Mock(return_value=FakeSession(page))
        with patch("time.sleep"):
            first = wa_web.send("+5511999998888", "Oi", session_factory=factory)
            second = wa_web.send("+5511999998888", "Oi", force_resend=True, session_factory=factory)
        self.assertIn("status=done", first)
        self.assertIn("status=done", second)
        self.assertNotIn("duplicate_suppressed=true", second)
        self.assertEqual(factory.call_count, 2)

    def test_new_outbound_data_id_detected(self):
        page = FakePage(eval_responses=[
            None,
            False,
            {"ok": True, "baselineOutboundCount": 2, "baselineOutboundIds": ["msg_1", "msg_2"]},
            {"newOutboundCount": 3, "outboundIds": ["msg_1", "msg_2", "msg_3"], "composeCleared": True},
        ])
        factory = lambda: FakeSession(page)
        with patch("time.sleep"):
            result = wa_web.send("+5511999998888", "Oi", session_factory=factory)
        self.assertIn("status=done", result)
        self.assertIn("evidence=new_outbound_message_node_in_dom", result)
        self.assertIn("delivery_confirmed=false", result)

    def test_action_routing_via_env_backend(self):
        with patch.dict("os.environ", {"MARK_LVI_WA_BACKEND": "web"}):
            with patch("core.whatsapp_web.send", return_value="status=done mock_web") as mock_web_send:
                res = action._send_whatsapp("+5511999998888", "Oi")
                self.assertEqual(res, "status=done mock_web")
                mock_web_send.assert_called_once_with("+5511999998888", "Oi", force_resend=False)

        with patch.dict("os.environ", {"MARK_LVI_WA_BACKEND": "desktop"}):
            with patch("core.whatsapp_desktop.send", return_value="status=done mock_desktop") as mock_desk_send:
                res = action._send_whatsapp("Alice", "Oi")
                self.assertEqual(res, "status=done mock_desktop")
                mock_desk_send.assert_called_once_with("Alice", "Oi", force_resend=False)


class TestWhatsAppWebDOM(unittest.TestCase):
    """Run the actual validation and observation scripts against a local DOM."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("Playwright is not installed") from exc
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.set_content('''
            <div id="outside" data-id="outside-ancestor">
                <div data-id="outside-old" class="message-out"></div>
                <div id="main">
                    <header>
                        <span data-testid="conversation-info-header-chat-title">5511999998888</span>
                    </header>
                    <div data-id="inside-old" class="message-out"></div>
                    <span data-testid="tail-out"></span>
                    <span data-icon="tail-out"></span>
                    <div data-testid="conversation-compose-box-input"></div>
                </div>
            </div>
        ''')

    def execute_send(self, after_enter, logger=lambda line: None, ticks=None):
        composer = FakeLocator()
        composer.press = Mock(side_effect=lambda key: self.page.evaluate(after_enter))
        page = Mock(wraps=self.page)
        page.goto = Mock()  # Never navigate to WhatsApp or send a real message.
        page.locator = Mock(return_value=composer)
        evaluations = []

        def evaluate(script, *args):
            result = self.page.evaluate(script, *args)
            if isinstance(result, dict) and "baselineOutboundIds" in result:
                self.assertEqual(composer.clicked, 0)
                self.assertIsNone(composer.filled)
                composer.press.assert_not_called()
            evaluations.append(result)
            return result

        page.evaluate = Mock(side_effect=evaluate)
        with patch.object(wa_web, "time") as clock:
            clock.monotonic.side_effect = ticks or [0.0, 0.0, 7.0]
            result = wa_web._execute_send("5511999998888", "Oi", FakeSession(page), logger=logger)
        return result, evaluations, composer

    def test_read_only_diagnostic_sanitizes_nested_structure(self):
        import json
        self.page.evaluate('''() => document.querySelector('#main').insertAdjacentHTML('beforeend',
            '<div data-id="private-identifier" data-testid="msg-container"><div class="message-out private-class">private-text<span data-icon="msg-dblcheck"></span></div></div>')''')
        before = self.page.content()
        result = wa_web._inspect_message_structure(self.page, "5511999998888")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["msg_containers"], 1)
        self.assertEqual(result["outbound_matches"], 1)
        nested = next(item for item in result["recent"] if item["node"]["classes"] == ["message-out"] and not item["node"]["has_data_id"])
        self.assertFalse(nested["node"]["matches_current_selector"])
        self.assertTrue(nested["ancestors"][0]["has_data_id"])
        for secret in ("private-identifier", "private-class", "private-text", "5511999998888", "outside-ancestor"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(before, self.page.content())

    def test_read_only_diagnostic_aborts_unconfirmed_recipient(self):
        result = wa_web._inspect_message_structure(self.page, "5511888887777")
        self.assertEqual(result["reason"], "recipient_not_confirmed")
        self.assertNotIn("recent", result)

    def test_reported_tail_structure_maps_to_message_id_in_both_phases(self):
        self.page.evaluate('''() => {
            document.querySelector('#main div[data-id]').outerHTML =
                '<div data-id="message-old"><div data-testid="msg-container"><span data-testid="tail-out"></span></div></div>';
        }''')
        mapping = self.page.evaluate('''() => {
            const main = document.querySelector('#main');
            const nodes = main.querySelectorAll(':scope div[data-id].message-out, :scope div[data-id] [data-testid="tail-out"], :scope div[data-id] [data-icon="tail-out"]');
            return Array.from(nodes, node => ({tag: node.tagName,
                ownId: node.hasAttribute('data-id'),
                closestId: node.closest('div[data-id]').getAttribute('data-id')}));
        }''')
        self.assertEqual(mapping, [{"tag": "SPAN", "ownId": False, "closestId": "message-old"}])
        diagnostic = wa_web._inspect_message_structure(self.page, "", current_chat=True)
        self.assertEqual(diagnostic["outbound_matches"], 1)
        result, evaluations, _ = self.execute_send('''() => {
            const wrapper = document.querySelector('#main div[data-id]');
            const replacement = wrapper.cloneNode(true);
            replacement.setAttribute('data-id', 'message-new');
            wrapper.replaceWith(replacement);
        }''')
        self.assertEqual(evaluations[2]["baselineOutboundIds"], ["message-old"])
        self.assertEqual(evaluations[3]["outboundIds"], ["message-new"])
        self.assertEqual(evaluations[2]["baselineOutboundCount"], evaluations[3]["newOutboundCount"])
        self.assertIn("status=done", result)

    def test_tail_with_own_data_id_bypasses_closest_message_wrapper(self):
        # Characterization of a conditional defect, NOT evidence of the live DOM.
        self.page.evaluate('''() => {
            document.querySelector('#main div[data-id]').outerHTML =
                '<div data-id="message-old"><div data-testid="msg-container"><span data-id="marker-stable" data-testid="tail-out"></span></div></div>';
        }''')
        closest_id = self.page.evaluate('''() => document.querySelector(
            '#main div[data-testid="msg-container"] span').closest('div[data-id]').getAttribute('data-id')''')
        self.assertEqual(closest_id, "message-old")
        result, evaluations, _ = self.execute_send('''() => {
            document.querySelector('#main div[data-id]').setAttribute('data-id', 'message-new');
        }''')
        self.assertEqual(evaluations[2]["baselineOutboundIds"], ["marker-stable"])
        self.assertEqual(evaluations[3]["outboundIds"], ["marker-stable"])
        self.assertIn("status=unverified", result)

    def test_send_and_diagnostic_require_full_number_even_with_you_label(self):
        for you_label in (False, True):
            for text, accepted in (
                ("+55 (11) 99999-8888", True),
                ("5511888887777", False),
                ("", False),
                ("999998888", False),
                ("Private name 5511999998888", False),
            ):
                with self.subTest(you_label=you_label, text=text):
                    self.page.evaluate('''({text, youLabel}) => {
                        const header = document.querySelector('#main header');
                        header.replaceChildren();
                        const title = document.createElement('span');
                        title.setAttribute('data-testid', 'conversation-info-header-chat-title');
                        title.textContent = text;
                        header.appendChild(title);
                        if (youLabel) {
                            const label = document.createElement('span');
                            label.setAttribute('data-testid', 'you-label');
                            header.appendChild(label);
                        }
                    }''', {"text": text, "youLabel": you_label})
                    diagnostic = wa_web._inspect_message_structure(self.page, "5511999998888")
                    result, _, composer = self.execute_send("() => {}")
                    if accepted:
                        self.assertEqual(diagnostic["status"], "ok")
                        composer.press.assert_called_once_with("Enter")
                    else:
                        self.assertEqual(diagnostic["reason"], "recipient_not_confirmed")
                        self.assertFalse(diagnostic["send_attempted"])
                        self.assertTrue(diagnostic["retry_safe"])
                        self.assertIn("status=failed", result)
                        self.assertIn("send_attempted=false", result)
                        self.assertIn("retry_safe=true", result)
                        self.assertEqual(composer.clicked, 0)
                        self.assertIsNone(composer.filled)
                        composer.press.assert_not_called()

    def test_diagnostic_you_label_without_number_does_not_bind_recipient(self):
        self.page.evaluate('''() => {
            document.querySelector('#main header').innerHTML =
                '<span data-testid="conversation-info-header-chat-title">Private name</span>' +
                '<span data-testid="you-label">You</span>';
        }''')
        result = wa_web._inspect_message_structure(self.page, "5511999998888")
        self.assertEqual(result["reason"], "recipient_not_confirmed")
        self.assertNotIn("recent", result)

    def test_diagnostic_you_label_cannot_override_mismatching_number(self):
        self.page.evaluate('''() => document.querySelector('#main header').insertAdjacentHTML(
            'beforeend', '<span data-testid="you-label">You</span>')''')
        result = wa_web._inspect_message_structure(self.page, "5511888887777")
        self.assertEqual(result["reason"], "recipient_not_confirmed")
        self.assertNotIn("recent", result)

    def test_diagnostic_you_label_with_matching_full_number_is_accepted(self):
        self.page.evaluate('''() => document.querySelector('#main header').insertAdjacentHTML(
            'beforeend', '<span data-testid="you-label">You</span>')''')
        result = wa_web._inspect_message_structure(self.page, "5511999998888")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["recipient_confirmed"])

    def test_read_only_diagnostic_aborts_duplicate_main(self):
        self.page.evaluate("() => document.body.insertAdjacentHTML('beforeend', '<div id=main></div>')")
        result = wa_web._inspect_message_structure(self.page, "5511999998888")
        self.assertEqual(result["reason"], "main_not_unique_visible")

    def test_diagnostic_busy_profile_never_launches(self):
        with patch.object(wa_web, "_diagnostic_profile_available", return_value=False), patch.object(wa_web, "PlaywrightSession") as session:
            result = wa_web.diagnose_message_structure("5511999998888")
        self.assertEqual(result["status"], "aborted")
        session.assert_not_called()

    def test_diagnostic_navigation_never_uses_composer(self):
        session = MagicMock()
        with patch.object(wa_web, "_diagnostic_profile_available", return_value=True), patch.object(wa_web, "PlaywrightSession", return_value=session), patch.object(wa_web, "_inspect_message_structure", return_value={"status": "ok"}):
            self.assertEqual(wa_web.diagnose_message_structure("5511999998888"), {"status": "ok"})
        self.assertEqual([call[0] for call in session.page.method_calls], ["goto", "wait_for_selector"])
        session.page.goto.assert_called_once()
        session.__exit__.assert_called_once()

    def test_current_chat_structure_without_identity_or_dom_changes(self):
        import json
        self.page.evaluate('''() => {
            document.querySelector('#main header').textContent = 'private-name';
            document.body.insertAdjacentHTML('beforeend',
                '<div id="main" style="display:none"><div data-id="private-id" class="message-out"></div></div>');
        }''')
        before = self.page.content()
        result = wa_web._inspect_message_structure(self.page, "", current_chat=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["main_count"], 2)
        self.assertEqual(result["visible_main_count"], 1)
        self.assertFalse(result["recipient_confirmed"])
        self.assertEqual(result["outbound_matches"], 1)
        for secret in ("private-name", "private-id", "inside-old", "outside-ancestor"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(before, self.page.content())

    def test_current_chat_missing_hidden_or_ambiguous_main(self):
        self.page.evaluate("() => document.querySelector('#main').style.display = 'none'")
        result = wa_web._inspect_message_structure(self.page, "", current_chat=True)
        self.assertEqual(result["reason"], "no_selected_conversation")
        self.assertNotIn("recent", result)
        self.page.evaluate("() => document.querySelector('#main').remove()")
        self.assertEqual(wa_web._inspect_message_structure(self.page, "", current_chat=True)["status"], "info")
        self.page.evaluate("() => document.body.insertAdjacentHTML('beforeend', '<div id=main>a</div><div id=main>b</div>')")
        result = wa_web._inspect_message_structure(self.page, "", current_chat=True)
        self.assertEqual(result["reason"], "main_not_unique_visible")
        self.assertNotIn("recent", result)

    def test_current_chat_never_navigates_or_interacts(self):
        session = MagicMock()
        with patch.object(wa_web, "_diagnostic_profile_available", return_value=True), patch.object(wa_web, "PlaywrightSession", return_value=session), patch.object(wa_web, "_inspect_message_structure", return_value={"status": "info"}) as inspect:
            self.assertEqual(wa_web.diagnose_message_structure(current_chat=True), {"status": "info"})
        self.assertEqual([call[0] for call in session.page.method_calls], ["wait_for_function"])
        self.assertEqual(session.page.wait_for_function.call_args.kwargs["timeout"], 30000)
        inspect.assert_called_once_with(session.page, "", current_chat=True)
        session.__exit__.assert_called_once()

    def test_current_chat_busy_profile_never_launches(self):
        with patch.object(wa_web, "_diagnostic_profile_available", return_value=False), patch.object(wa_web, "PlaywrightSession") as session:
            result = wa_web.diagnose_message_structure(current_chat=True)
        self.assertEqual(result["status"], "aborted")
        session.assert_not_called()

    def test_diagnostic_cli_modes(self):
        from tools import diagnose_whatsapp_web as cli
        with patch.object(cli, "diagnose_message_structure", return_value={"status": "info"}) as diagnose, patch("builtins.print"), patch.dict("os.environ", {}, clear=True):
            cli.main(["--current-chat"])
            self.assertTrue(diagnose.call_args.kwargs["current_chat"])
            self.assertFalse(diagnose.call_args.kwargs["interactive"])
        with patch.object(cli, "diagnose_message_structure", return_value={"status": "aborted"}) as diagnose, patch("builtins.print"), patch.dict("os.environ", {"WA_TEST_PHONE": "5511999998888"}):
            cli.main([])
            diagnose.assert_called_once_with("5511999998888")

    def test_interactive_diagnostic_waits_then_inspects_and_closes(self):
        session = MagicMock()
        progress = Mock()
        with patch.object(wa_web, "_diagnostic_profile_available", return_value=True), patch.object(wa_web, "PlaywrightSession", return_value=session), patch.object(wa_web, "_inspect_stabilized_current_chat", return_value={"status": "ok"}) as inspect:
            result = wa_web.diagnose_message_structure(current_chat=True, interactive=True, progress=progress)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(session.page.wait_for_function.call_args.kwargs, {"arg": True, "timeout": 60000})
        self.assertEqual([call[0] for call in session.page.method_calls], ["wait_for_function"])
        inspect.assert_called_once_with(session.page)
        session.__exit__.assert_called_once()
        session.pw.stop.assert_called_once()
        self.assertFalse(wa_web._lock.locked())
        self.assertEqual(progress.call_count, 2)

    def test_stabilization_reads_delayed_local_dom_and_preserves_composer(self):
        elapsed = [0.0]
        page = Mock(wraps=self.page)

        def advance(milliseconds):
            elapsed[0] += milliseconds / 1000
            if elapsed[0] == 1.5:
                self.page.evaluate('''() => document.querySelector('#main').insertAdjacentHTML(
                    'beforeend', '<div data-id="delayed" data-testid="msg-container"></div>')''')

        page.wait_for_timeout = Mock(side_effect=advance)
        with patch.object(wa_web, "time") as clock:
            clock.monotonic.side_effect = lambda: elapsed[0]
            result = wa_web._inspect_stabilized_current_chat(page)
        self.assertEqual(elapsed[0], 2.5)
        self.assertTrue(result["structure_stabilized"])
        self.assertEqual(result["msg_containers"], 1)
        self.assertEqual(result["data_id_nodes"], 2)
        self.assertGreater(page.evaluate.call_count, 2)
        self.assertEqual(self.page.locator('[data-testid="conversation-compose-box-input"]').inner_text(), "")

    def test_stabilization_changing_counts_stops_at_five_seconds(self):
        elapsed = [0.0]
        page = Mock()
        page.wait_for_timeout.side_effect = lambda milliseconds: elapsed.__setitem__(0, elapsed[0] + milliseconds / 1000)

        def sample(*args, **kwargs):
            return {"status": "ok", "msg_containers": int(elapsed[0] * 4), "data_id_nodes": 1}

        with patch.object(wa_web, "time") as clock, patch.object(wa_web, "_inspect_message_structure", side_effect=sample) as inspect:
            clock.monotonic.side_effect = lambda: elapsed[0]
            result = wa_web._inspect_stabilized_current_chat(page)
        self.assertEqual(elapsed[0], 5.0)
        self.assertFalse(result["structure_stabilized"])
        self.assertEqual(result["msg_containers"], 20)
        self.assertEqual(inspect.call_count, 22)

    def test_stabilization_empty_history_waits_minimum_and_main_loss_aborts(self):
        for disappears in (False, True):
            with self.subTest(disappears=disappears):
                elapsed = [0.0]
                page = Mock()
                page.wait_for_timeout.side_effect = lambda milliseconds: elapsed.__setitem__(0, elapsed[0] + milliseconds / 1000)

                def sample(*args, **kwargs):
                    if disappears and elapsed[0] > 0:
                        return {"status": "info", "reason": "no_selected_conversation"}
                    return {"status": "ok", "msg_containers": 0, "data_id_nodes": 0}

                with patch.object(wa_web, "time") as clock, patch.object(wa_web, "_inspect_message_structure", side_effect=sample):
                    clock.monotonic.side_effect = lambda: elapsed[0]
                    result = wa_web._inspect_stabilized_current_chat(page)
                self.assertEqual(elapsed[0], 0.25 if disappears else 2.0)
                self.assertEqual(result["status"], "info" if disappears else "ok")

    def test_diagnostic_load_and_selection_timeouts_close_session(self):
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        for interactive in (False, True):
            with self.subTest(interactive=interactive):
                session = MagicMock()
                session.page.wait_for_function.side_effect = PlaywrightTimeoutError("private details")
                with patch.object(wa_web, "_diagnostic_profile_available", return_value=True), patch.object(wa_web, "PlaywrightSession", return_value=session), patch.object(wa_web, "_inspect_message_structure") as inspect:
                    result = wa_web.diagnose_message_structure(current_chat=True, interactive=interactive)
                self.assertEqual(result["reason"], "manual_selection_timeout" if interactive else "whatsapp_load_timeout")
                self.assertNotIn("private", str(result))
                inspect.assert_not_called()
                session.__exit__.assert_called_once()
                session.pw.stop.assert_called_once()
                self.assertFalse(wa_web._lock.locked())

    def test_interactive_cli_is_explicit(self):
        from tools import diagnose_whatsapp_web as cli
        with patch.object(cli, "diagnose_message_structure", return_value={"status": "info"}) as diagnose, patch("builtins.print"):
            cli.main(["--current-chat", "--interactive"])
            self.assertTrue(diagnose.call_args.kwargs["interactive"])
        with patch.object(cli, "diagnose_message_structure") as diagnose, patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                cli.main(["--interactive"])
            diagnose.assert_not_called()

    def test_profile_guard_rejects_owner_and_unknown_process(self):
        import psutil
        process = Mock()
        process.name.return_value = "chrome.exe"
        process.cmdline.return_value = ["chrome.exe", "--user-data-dir=" + wa_web.PROFILE_PATH]
        with patch("os.path.isdir", return_value=True), patch("os.path.lexists", return_value=False), patch("psutil.process_iter", return_value=[process]):
            self.assertFalse(wa_web._diagnostic_profile_available(wa_web.PROFILE_PATH))
            process.cmdline.side_effect = psutil.AccessDenied()
            self.assertFalse(wa_web._diagnostic_profile_available(wa_web.PROFILE_PATH))

    def test_profile_guard_rejects_lock_and_accepts_idle_profile(self):
        with patch("os.path.isdir", return_value=True), patch("os.path.lexists", return_value=True), patch("psutil.process_iter") as processes:
            self.assertFalse(wa_web._diagnostic_profile_available(wa_web.PROFILE_PATH))
            processes.assert_not_called()
        with patch("os.path.isdir", return_value=True), patch("os.path.lexists", return_value=False), patch("psutil.process_iter", return_value=[]):
            self.assertTrue(wa_web._diagnostic_profile_available(wa_web.PROFILE_PATH))

    def test_outbound_messages_outside_main_are_ignored(self):
        result, evaluations, composer = self.execute_send('''() => {
            document.querySelector('#outside').insertAdjacentHTML('beforeend', `
                <div data-id="outside-new" class="message-out"></div>
                <div data-id="outside-tail"><span data-testid="tail-out"></span></div>
                <div data-id="outside-icon"><span data-icon="tail-out"></span></div>
            `);
        }''')
        self.assertEqual(evaluations[2]["baselineOutboundCount"], 1)
        self.assertEqual(evaluations[2]["baselineOutboundIds"], ["inside-old"])
        self.assertEqual(evaluations[3]["newOutboundCount"], 1)
        self.assertEqual(evaluations[3]["outboundIds"], ["inside-old"])
        self.assertIn("status=unverified", result)
        self.assertIn("retry_safe=false", result)
        composer.press.assert_called_once_with("Enter")

    def test_new_outbound_message_inside_main_is_detected(self):
        result, evaluations, _ = self.execute_send('''() => {
            document.querySelector('#main').insertAdjacentHTML('beforeend',
                '<div data-id="inside-new" class="message-out"></div>');
        }''')
        self.assertEqual(evaluations[3]["outboundIds"], ["inside-old", "inside-new"])
        self.assertIn("status=done", result)

    def test_missing_main_before_send_aborts(self):
        self.page.evaluate("() => document.querySelector('#main').remove()")
        result, _, composer = self.execute_send("() => {}")
        self.assertIn("status=failed", result)
        self.assertIn("main_container_not_found", result)
        composer.press.assert_not_called()

    def test_main_disappearing_after_send_is_unverified(self):
        result, evaluations, composer = self.execute_send(
            "() => document.querySelector('#main').remove()"
        )
        self.assertEqual(evaluations[3], {
            "mainExists": False, "dataIdCount": 0,
            "dataIds": [], "msgContainerCount": 0, "mainCount": 0, "mainVisible": False,
            "newOutboundCount": 0, "outboundIds": [], "composeCleared": False,
        })
        self.assertIn("status=unverified", result)
        self.assertIn("retry_safe=false", result)
        composer.press.assert_called_once_with("Enter")

    def test_nested_message_out_without_tail_is_not_recognized(self):
        logs = []
        with patch.dict("os.environ", {"MARK_LVI_WA_OBSERVER_DEBUG": "1"}):
            result, evaluations, composer = self.execute_send('''() => {
                document.querySelector('#main').insertAdjacentHTML('beforeend',
                    '<div data-id="private-id"><div class="message-out">private-content</div></div>');
            }''', logger=logs.append, ticks=[0.0, 0.0, 1.0, 7.0])
        self.assertIn("status=unverified", result)
        self.assertEqual(evaluations[3]["dataIdCount"], 2)
        self.assertEqual(evaluations[3]["outboundIds"], ["inside-old"])
        self.assertEqual(len(logs), 3)
        for attempt, line in enumerate(logs[1:], 1):
            self.assertEqual(line, (
                f"[wa-observer] phase=poll attempt={attempt} main_exists=True "
                "data_id_nodes=2 outbound_matches=1 outbound_ids=1 new_ids=0 "
                "data_ids_added=1 data_ids_removed=0 msg_containers=0 "
                "main_count=1 main_visible=True composer_empty=True"
            ))
        for secret in ("private-id", "private-content", "5511999998888", "inside-old", "Oi"):
            self.assertNotIn(secret, "\n".join(logs))
        composer.press.assert_called_once_with("Enter")

    def test_each_supported_structure_has_matching_baseline_and_poll_criteria(self):
        for marker in ('class="message-out"', 'data-testid="tail-out"', 'data-icon="tail-out"'):
            with self.subTest(marker=marker):
                self.page.evaluate('''marker => {
                    const main = document.querySelector('#main');
                    main.querySelectorAll('div[data-id]').forEach(node => node.remove());
                    main.insertAdjacentHTML('beforeend', marker.startsWith('class')
                        ? `<div data-id="old" ${marker}></div>`
                        : `<div data-id="old"><span ${marker}></span></div>`);
                }''', marker)
                script = '''() => {
                    const main = document.querySelector('#main');
                    const copy = main.querySelector('div[data-id]').cloneNode(true);
                    copy.setAttribute('data-id', 'new');
                    main.appendChild(copy);
                }'''
                logs = []
                with patch.dict("os.environ", {"MARK_LVI_WA_OBSERVER_DEBUG": "0"}):
                    result, evaluations, _ = self.execute_send(script, logger=logs.append)
                self.assertEqual(evaluations[2]["baselineOutboundIds"], ["old"])
                self.assertEqual(evaluations[2]["baselineOutboundCount"], 1)
                self.assertEqual(evaluations[3]["outboundIds"], ["old", "new"])
                self.assertEqual(evaluations[3]["newOutboundCount"], 2)
                self.assertIn("status=done", result)
                self.assertEqual(logs, [])

    def test_virtualized_unrecognized_message_changes_ids_not_counts(self):
        self.page.evaluate('''() => {
            document.querySelector('#main').insertAdjacentHTML('beforeend',
                '<div data-id="private-old" data-testid="msg-container"></div>');
        }''')
        logs = []
        with patch.dict("os.environ", {"MARK_LVI_WA_OBSERVER_DEBUG": "1"}):
            result, evaluations, composer = self.execute_send('''() => {
                document.querySelector('#main [data-id="private-old"]').remove();
                document.querySelector('#main').insertAdjacentHTML('beforeend',
                    '<div data-id="private-new" data-testid="msg-container"><div class="message-out">secret</div></div>');
            }''', logger=logs.append)
        self.assertEqual(evaluations[2]["dataIdCount"], evaluations[3]["dataIdCount"])
        self.assertIn("status=unverified", result)
        self.assertIn("data_ids_added=1 data_ids_removed=1 msg_containers=1", logs[1])
        self.assertIn("data_ids_added=0 data_ids_removed=0", logs[0])
        for secret in ("private-old", "private-new", "secret", "5511999998888"):
            self.assertNotIn(secret, "\n".join(logs))
        composer.press.assert_called_once_with("Enter")

    def test_replaced_main_is_read_fresh_and_outbound_replacement_is_detected(self):
        logs = []
        with patch.dict("os.environ", {"MARK_LVI_WA_OBSERVER_DEBUG": "1"}):
            result, evaluations, _ = self.execute_send('''() => {
                const main = document.querySelector('#main');
                const replacement = main.cloneNode(true);
                replacement.querySelector('[data-id="inside-old"]').setAttribute('data-id', 'replacement-id');
                main.replaceWith(replacement);
            }''', logger=logs.append)
        self.assertEqual(evaluations[2]["baselineOutboundCount"], evaluations[3]["newOutboundCount"])
        self.assertEqual(evaluations[3]["outboundIds"], ["replacement-id"])
        self.assertIn("status=done", result)
        self.assertIn("new_ids=1 data_ids_added=1 data_ids_removed=1", logs[1])

    def test_msg_container_without_data_id_is_diagnostic_only(self):
        logs = []
        with patch.dict("os.environ", {"MARK_LVI_WA_OBSERVER_DEBUG": "1"}):
            result, evaluations, _ = self.execute_send('''() => {
                document.querySelector('#main').insertAdjacentHTML('beforeend',
                    '<div data-testid="msg-container">secret</div>');
                document.querySelector('#outside').insertAdjacentHTML('beforeend',
                    '<div data-testid="msg-container"></div>');
            }''', logger=logs.append)
        self.assertEqual(evaluations[2]["dataIdCount"], evaluations[3]["dataIdCount"])
        self.assertIn("data_ids_added=0 data_ids_removed=0 msg_containers=1", logs[1])
        self.assertIn("status=unverified", result)


if __name__ == "__main__":
    unittest.main()


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
