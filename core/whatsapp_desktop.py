"""Conservative Windows WhatsApp automation; no network service or blind send."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
import threading
import time
import unicodedata

from core import appidentity, outcome


@dataclass(frozen=True)
class Timeouts:
    opening: float = 8.0
    conversation: float = 6.0
    input: float = 3.0
    confirmation: float = 3.0
    total: float = 24.0
    poll: float = 0.15


class UnsafeUI(RuntimeError):
    pass


class Operation:
    def __init__(self):
        self.cancelled = threading.Event()
        self.attempted = False
        self.gate = threading.Lock()
        self.deadline = None

    def check(self):
        if self.cancelled.is_set():
            raise TimeoutError("operation deadline exceeded")
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            raise TimeoutError("stage deadline exceeded")

    def query(self, callback):
        self.check()
        try:
            result = callback()
        except Exception:
            self.check()
            raise
        self.check()
        return result

    def commit(self):
        with self.gate:
            self.check()
            self.attempted = True


@contextmanager
def measured(label, logger=print):
    start = time.perf_counter()
    try:
        yield
    finally:
        logger(f"[PERF] {label}: {(time.perf_counter() - start) * 1000:.1f}ms")


def wait_for(probe, timeout, operation, poll=0.15):
    deadline = time.perf_counter() + timeout
    while True:
        operation.check()
        if time.perf_counter() >= deadline:
            raise TimeoutError("interface condition deadline exceeded")
        try:
            result = probe()
        except Exception:
            operation.check()
            if time.perf_counter() >= deadline:
                raise TimeoutError("interface query exceeded deadline") from None
            raise
        operation.check()
        if time.perf_counter() >= deadline:
            raise TimeoutError("interface query exceeded deadline")
        if result:
            return result
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError("interface condition not reached")
        operation.cancelled.wait(min(poll, remaining))


from core.whatsapp_driver import WhatsAppDriver

class WindowsUI(WhatsAppDriver):
    """UIA first, native Win32 controls second, guarded keyboard input last.

    Unknown/localized controls fail closed. No coordinate guessing or OCR.
    All COM wrappers belong to the dedicated worker that constructs this object.
    """

    SEARCH = {"search", "search or start new chat", "pesquisar",
              "pesquisar ou começar uma nova conversa", "pesquisar ou iniciar uma nova conversa"}
    COMPOSER = {"type a message", "digite uma mensagem", "message", "mensagem"}
    SEND = {"send", "send message", "enviar", "enviar mensagem"}
    SENT = {"sent", "enviada", "enviado", "delivered", "entregue", "read", "lida", "lido"}
    DELIVERED = {"delivered", "entregue", "read", "lida", "lido"}

    def __init__(self):
        # Load lazily on the COM-owning worker, without resolving a window yet.
        from pywinauto.controls.uiawrapper import UIAWrapper
        self._uia_wrapper = UIAWrapper
        self.window = None
        self.match = None
        self.backend = None
        self.operation = None
        self.logger = print

    def _query(self, callback):
        return self.operation.query(callback) if self.operation else callback()

    def _wrap_handle(self, hwnd, backend):
        # Direct construction avoids WindowSpecification's implicit find retry.
        # wrapper_object() has no per-call timeout argument in pywinauto 0.6.9.
        if backend == 0:
            from pywinauto.uia_element_info import UIAElementInfo
            return self._query(lambda: self._uia_wrapper(UIAElementInfo(hwnd)))
        from pywinauto.controls.hwndwrapper import HwndWrapper
        return self._query(lambda: HwndWrapper(hwnd))

    def _deduplicate(self, controls):
        # Identity is scoped to THIS enumeration only. Never cache RuntimeIds.
        seen = set()
        unique = []
        for control in controls:
            self._check()
            runtime = self._query(lambda: getattr(control.element_info, "runtime_id", None))
            handle = getattr(control, "handle", None)
            identity = ("uia", tuple(runtime)) if runtime else ("hwnd", handle) if handle else None
            if identity is None or identity not in seen:
                unique.append(control)
                if identity is not None:
                    seen.add(identity)
        self.logger(f"[UIA] enumeration raw={len(controls)} unique={len(unique)}")
        return unique

    def _document(self):
        # Walk children with local cycle detection, not all descendants of the
        # outer host: that provider exposes the same WebView many times.
        with measured("WhatsApp root resolution", self.logger):
            queue = [(self.window, 0)]
            seen = set()
            documents = []
            while queue:
                node, depth = queue.pop(0)
                runtime = self._query(lambda: getattr(node.element_info, "runtime_id", None))
                identity = tuple(runtime) if runtime else id(node)
                if identity in seen:
                    continue
                seen.add(identity)
                if len(seen) > 160:
                    raise UnsafeUI("accessibility root traversal limit exceeded")
                if self._query(lambda: self._kind(node)) == "Document":
                    if self._query(node.is_visible):
                        documents.append(node)
                    continue
                if depth < 12:
                    queue.extend((child, depth + 1) for child in self._query(node.children))
            if len(documents) > 1:
                raise UnsafeUI("multiple distinct accessible documents")
            return documents[0] if documents else None

    def _check(self):
        if self.operation is not None:
            self.operation.check()

    def detect(self):
        matches = appidentity.running("WhatsApp")
        for match in matches:
            for hwnd in appidentity._hwnds_for(match.pid):
                for index in range(2):
                    try:
                        window = self._wrap_handle(hwnd, index)
                        if window.is_visible():
                            self.match, self.window = match, window
                            self.backend = index
                            return True
                    except TimeoutError:
                        raise
                    except Exception:
                        continue
        return False

    # ------------------------------------------------------------
    # Implementação da API abstrata WhatsAppDriver (Fase 1)
    # ------------------------------------------------------------
    def search_recipient(self, target: str) -> str:
        """Busca o contato ou grupo solicitado.
        Ainda não implementado – devolve estado *unverified* para sinalizar
        que a lógica ainda será completada nas fases posteriores.
        """
        # Placeholder: a futura implementação usará `search_control`
        # e simulará a digitação segura via UIA somente para validação.
        return outcome.unverified("whatsapp_desktop", f"search not implemented for '{target}'")

    def verify_conversation(self, expected_target: str) -> bool:
        """Verifica se o cabeçalho da conversa ativa corresponde ao contato
        esperado. Por enquanto, retorna *False* indicando que a verificação ainda
        não está disponível.
        """
        # Placeholder – identificar header será implementado em fase posterior.
        return False

    def prepare_message(self, text: str) -> str:
        """Prepara o compositor com o texto fornecido sem enviá‑lo.
        Placeholder que devolve *unverified*.
        """
        return outcome.unverified("whatsapp_desktop", f"prepare_message not implemented for text length {len(text)}")

    def send_and_verify(self, timeout: float = 10.0) -> str:
        """Aciona o botão de envio e aguarda confirmação de entrega.
        Ainda como placeholder – devolve *unverified*.
        """
        return outcome.unverified("whatsapp_desktop", "send_and_verify not implemented")


    def launch(self):
        # Activate the registered app, not a search box or an unverified shell.
        self._check()
        os.startfile("whatsapp:")

    def focus(self):
        if self.match is None or not appidentity.focus(self.match):
            raise UnsafeUI("WhatsApp window could not be focused")

    def _controls(self, kinds=None):
        root = self._document() if self.backend == 0 else self.window
        if root is None:
            return []
        with measured("WhatsApp control enumeration", self.logger):
            if kinds and self.backend == 0:
                controls = []
                for kind in sorted(kinds):
                    controls.extend(self._query(lambda: root.descendants(control_type=kind)))
            else:
                controls = self._query(root.descendants)
        with measured("WhatsApp identity deduplication", self.logger):
            controls = self._deduplicate(controls)
        return [c for c in controls
                if self._query(c.is_visible) and self._query(c.is_enabled)]

    @staticmethod
    def _name(control):
        return control.window_text().strip()

    @staticmethod
    def _kind(control):
        kind = getattr(control.element_info, "control_type", None)
        return kind or control.friendly_class_name()

    def _unique(self, names, kinds):
        matches = [c for c in self._controls(kinds)
                   if self._query(lambda: self._kind(c)) in kinds
                   and self._query(lambda: self._name(c)).casefold() in names]
        if len(matches) > 1:
            raise UnsafeUI("ambiguous interface controls")
        return matches[0] if matches else None

    def search_control(self):
        # Generic "Search" also labels in-conversation search. Only the chat
        # list label plus its observed Tab/Button sibling structure qualifies.
        names = self.SEARCH - {"search", "pesquisar"}
        candidates = []
        for c in self._controls({"Edit", "ComboBox"}):
            if (self._query(lambda: self._kind(c)) not in {"Edit", "ComboBox"}
                    or self._query(lambda: self._name(c)).casefold() not in names):
                continue
            parent = self._query(c.parent)
            siblings = self._deduplicate(self._query(parent.children))
            kinds = {self._query(lambda: self._kind(s)) for s in siblings}
            if "Tab" in kinds and "Button" in kinds:
                candidates.append(c)
        if len(candidates) > 1:
            raise UnsafeUI("multiple distinct conversation search controls")
        control = candidates[0] if candidates else None
        if control is None and self.backend == 0:
            # A UIA provider may expose nothing while native child HWNDs work.
            native = self._wrap_handle(self.window.handle, 1)
            original = self.window
            self.window = native
            original_backend = self.backend
            self.backend = 1
            control = self._unique(names, {"Edit", "ComboBox"})
            if control is None:
                self.window = original
                self.backend = original_backend
            else:
                self.backend = 1
        return control

    @staticmethod
    def read_edit(control):
        try:
            return control.get_value()
        except (AttributeError, NotImplementedError):
            return control.window_text()

    def replace_text(self, control, text):
        try:
            self._check()
            control.set_edit_text(text)
            return
        except Exception:
            # Filling is idempotent; sending is not. Never use this after send.
            self.focus()
            control.set_focus()
            if not control.has_keyboard_focus():
                raise UnsafeUI("input control focus could not be verified")
            import pyautogui
            import pyperclip
            previous = pyperclip.paste()
            try:
                self._check()
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "a")
                self._check()
                pyautogui.hotkey("ctrl", "v")
                # Clipboard stays valid until the paste has actually arrived.
                deadline = time.perf_counter() + 1.0
                while self.read_edit(control) != text:
                    self._check()
                    if time.perf_counter() >= deadline:
                        raise UnsafeUI("pasted text could not be verified")
                    threading.Event().wait(0.05)
            finally:
                if pyperclip.paste() == text:
                    pyperclip.copy(previous)

    def contact(self, receiver):
        # Exact normalized contact only, never the first fuzzy search result.
        matches = [c for c in self._controls()
                   if self._kind(c) in {"ListItem", "DataItem"}
                   and appidentity.fold(self._name(c)) == appidentity.fold(receiver)]
        if len(matches) > 1:
            raise UnsafeUI("multiple contacts match; specify an unambiguous recipient")
        return matches[0] if matches else None

    def open_contact(self, control):
        try:
            self._check()
            control.select()
        except Exception:
            # Only a resolved control; click relative to it, not screen coordinates.
            self._check()
            control.click_input()

    def composer(self):
        return self._unique(self.COMPOSER, {"Edit"})

    def correct_conversation(self, receiver):
        # Require a header, not text in the search results or message body.
        for c in self._controls():
            info = c.element_info
            identifier = str(getattr(info, "automation_id", "")).casefold()
            header = self._kind(c) in {"Header", "HeaderItem"} or identifier in {
                "conversationheader", "chatheader", "conversationtitle", "chattitle"}
            if header and appidentity.fold(self._name(c)) == appidentity.fold(receiver):
                return True
        return False

    def outgoing(self, message):
        """Evidence is scoped to outgoing message containers, not arbitrary text.

        Unsupported accessibility schemas produce no proof, never guessed proof.
        """
        rows = []
        supported = False
        for c in self._controls():
            identifier = str(getattr(c.element_info, "automation_id", "")).casefold()
            if identifier not in {"outgoingmessage", "outgoingmessagebubble", "sentmessage"}:
                continue
            supported = True
            children = c.descendants()
            texts = [self._name(child) for child in children]
            if message not in texts:
                continue
            states = {text.casefold() for text in texts}
            if states & self.SENT:
                rows.append(bool(states & self.DELIVERED))
        return Counter(rows) if supported else None

    def send_control(self):
        return self._unique(self.SEND, {"Button"})

    def send_once(self, button, composer):
        if button is not None:
            # No retry if Invoke raises: the application may have processed it.
            self._check()
            button.click_input()
        else:
            self.focus()
            composer.set_focus()
            if not composer.has_keyboard_focus():
                raise UnsafeUI("composer focus lost before sending")
            import pyautogui
            self._check()
            pyautogui.press("enter")


def run(receiver, message, ui, operation, timeouts=Timeouts(), logger=print):
    facts = {"platform": "WhatsApp", "to": receiver, "delivery_confirmed": False}
    stages = set()
    if isinstance(ui, WindowsUI):
        ui.operation = operation
        ui.logger = logger

    @contextmanager
    def stage(name):
        stages.add(name)
        budget = {"WhatsApp window detection": timeouts.opening,
                  "WhatsApp startup": timeouts.opening,
                  "Contact search": timeouts.conversation,
                  "Message input": timeouts.input,
                  "Send confirmation": timeouts.confirmation}[name]
        operation.deadline = time.perf_counter() + budget
        try:
            with measured(name, logger):
                operation.check()
                yield
                operation.check()
        finally:
            operation.deadline = None

    try:
        operation.check()
        with stage("WhatsApp window detection"):
            opened = operation.query(ui.detect)
        with stage("WhatsApp startup"):
            operation.check()
            if not opened:
                operation.query(ui.launch)
                wait_for(ui.detect, timeouts.opening, operation, timeouts.poll)
            operation.query(ui.focus)
        with stage("Contact search"):
            deadline = time.perf_counter() + timeouts.conversation

            def remaining():
                return max(0, deadline - time.perf_counter())

            search = wait_for(ui.search_control, remaining(), operation, timeouts.poll)
            operation.check()
            operation.query(lambda: ui.replace_text(search, receiver))
            # Reacquire after search changes the document state.
            search = wait_for(ui.search_control, remaining(), operation, timeouts.poll)
            wait_for(lambda: ui.read_edit(search) == receiver, remaining(), operation, timeouts.poll)
            contact = wait_for(lambda: ui.contact(receiver), remaining(), operation, timeouts.poll)
            operation.check()
            operation.query(lambda: ui.open_contact(contact))
            search = contact = None
            wait_for(lambda: ui.correct_conversation(receiver), remaining(), operation, timeouts.poll)
            composer = wait_for(ui.composer, remaining(), operation, timeouts.poll)
        with stage("Message input"):
            operation.check()
            if operation.query(lambda: ui.read_edit(composer)):
                raise UnsafeUI("existing draft found; nothing overwritten or sent")
            operation.query(lambda: ui.replace_text(composer, message))
            composer = wait_for(ui.composer, timeouts.input, operation, timeouts.poll)
            wait_for(lambda: ui.read_edit(composer) == message, timeouts.input, operation, timeouts.poll)
            if not operation.query(lambda: ui.correct_conversation(receiver)):
                raise UnsafeUI("conversation changed before sending")
            before = operation.query(lambda: ui.outgoing(message))
            button = operation.query(ui.send_control)
        with stage("Send confirmation"):
            if not operation.query(lambda: ui.correct_conversation(receiver)):
                raise UnsafeUI("conversation changed at send boundary")
            composer = operation.query(ui.composer)
            button = operation.query(ui.send_control)
            if composer is None or operation.query(lambda: ui.read_edit(composer)) != message:
                raise UnsafeUI("composer changed at send boundary")
            operation.commit()
            operation.query(lambda: ui.send_once(button, composer))
            button = composer = None
            if before is None:
                return outcome.unverified(
                    "send_message", "outgoing message evidence is not exposed by this interface",
                    **facts, send_attempted=True, retry_safe=False)

            def evidence():
                if not ui.correct_conversation(receiver):
                    raise UnsafeUI("conversation changed after send attempt")
                after = ui.outgoing(message)
                if after is None:
                    raise UnsafeUI("outgoing message evidence became unavailable")
                # Count increases avoid matching an old identical message.
                return after if sum(after.values()) > sum(before.values()) else None

            wait_for(evidence, timeouts.confirmation, operation, timeouts.poll)
            # A receipt on an older identical message could change concurrently.
            # Without a stable message ID do not attribute delivery to this send.
            delivered = False
            return outcome.done("send_message", platform="WhatsApp", to=receiver,
                                verified=True, evidence="new_outgoing_message_with_sent_state",
                                sent_in_ui=True, delivery_confirmed=delivered)
    except Exception as exc:
        if operation.attempted:
            return outcome.unverified("send_message", str(exc), **facts,
                                      send_attempted=True, retry_safe=False)
        return outcome.failed("send_message", str(exc), **facts, send_attempted=False)
    finally:
        for name in ("WhatsApp window detection", "WhatsApp startup", "Contact search",
                     "Message input", "Send confirmation"):
            if name not in stages:
                logger(f"[PERF] {name}: skipped")


_lock = threading.Lock()
_recent = {}
_REPEAT_WINDOW = 120.0


def _normalize_text(text: str) -> str:
    """Normalize text to block trivial variations in capitalization, accents and whitespace."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.casefold().split())


def send(receiver, message, *, force_resend=False, ui_factory=WindowsUI, timeouts=Timeouts(), logger=print):
    """Called inside the existing action executor. Bound even stalled COM calls.

    A timed-out worker retains the lock until it exits; cancellation forbids a
    later send. Ambiguous attempts are remembered in RAM for two minutes.
    """
    with measured("Total", logger):
        if not _lock.acquire(blocking=False):
            return outcome.failed("send_message", "another WhatsApp operation is still running; not sent")
        norm_msg = _normalize_text(message)
        key = hashlib.sha256((appidentity.fold(receiver) + "\0" + norm_msg).encode()).hexdigest()
        now = time.perf_counter()
        for old in list(_recent):
            if now - _recent[old][0] > _REPEAT_WINDOW:
                del _recent[old]
        if not force_resend and key in _recent:
            result = _recent[key][1]
            _lock.release()
            return result + " duplicate_suppressed=true -- No new send attempted; check the previous message."
        operation = Operation()
        completed = threading.Event()
        results = []

        def worker():
            initialized = False
            try:
                if os.name == "nt":
                    import ctypes
                    hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
                    initialized = hr in (0, 1)
                    if not initialized:
                        raise RuntimeError(f"COM initialization failed: {hr}")
                ui = ui_factory()
                try:
                    result = run(receiver, message, ui, operation, timeouts, logger)
                finally:
                    del ui  # Release COM wrappers on their owning MTA thread.
            except Exception as exc:
                result = outcome.failed("send_message", f"WhatsApp driver unavailable: {exc}",
                                        send_attempted=False)
            finally:
                if initialized:
                    ctypes.windll.ole32.CoUninitialize()
            if operation.attempted:
                _recent[key] = (time.perf_counter(), result)
            results.append(result)
            _lock.release()
            completed.set()

        thread = threading.Thread(target=worker, daemon=True, name="whatsapp-ui")
        try:
            thread.start()
        except Exception:
            _lock.release()
            raise
        if completed.wait(timeouts.total):
            return results[0]
        with operation.gate:
            operation.cancelled.set()
            attempted = operation.attempted
        if attempted:
            return outcome.unverified("send_message", "overall timeout after send attempt",
                                      send_attempted=True, retry_safe=False, delivery_confirmed=False)
        return outcome.failed("send_message", "overall timeout before sending", send_attempted=False)