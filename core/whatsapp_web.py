"""core/whatsapp_web.py — WhatsApp Web automation via Playwright.

Single-message dispatch with strict DOM validation, recipient verification,
deduplication lock, and conservative outcome reporting.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import threading
import time
import unicodedata
from typing import Any, Callable

from core import outcome

from core.app_paths import data_root
PROFILE_PATH = str(data_root() / "browser-profiles/whatsapp-web")
_REPEAT_WINDOW = 120.0
_lock = threading.Lock()
_recent: dict[str, tuple[float, str]] = {}


def _normalize_text(text: str) -> str:
    """Normalize text to block trivial variations in capitalization, accents and whitespace."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = " ".join(normalized.casefold().split())
    return normalized


def _mask_phone(phone: str) -> str:
    cleaned = re.sub(r"\D", "", phone or "")
    if len(cleaned) <= 4:
        return "****"
    return f"...{cleaned[-4:]}"


def _sanitize_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


class PlaywrightSession:
    """Encapsulates the persistent browser context for WhatsApp Web."""

    def __init__(self, profile_path: str = PROFILE_PATH, headless: bool = False):
        self.profile_path = profile_path
        self.headless = headless
        self.pw = None
        self.context = None
        self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.context = self.pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_path,
            headless=self.headless,
            no_viewport=True,
            args=["--start-maximized"],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
def _diagnostic_profile_available(profile_path: str) -> bool:
    """Fail closed on busy/unknown ownership; never remove browser lock files."""
    import psutil

    if not os.path.isdir(profile_path):
        return False
    if any(os.path.lexists(os.path.join(profile_path, name))
           for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile")):
        return False
    target = os.path.normcase(os.path.realpath(profile_path))
    try:
        for process in psutil.process_iter():
            try:
                name = process.name().lower()
                if not any(browser in name for browser in ("chrome", "chromium", "msedge", "headless_shell")):
                    continue
                args = process.cmdline()
                if not args:
                    return False
                for index, arg in enumerate(args):
                    if arg.startswith("--user-data-dir="):
                        value = arg.split("=", 1)[1]
                    elif arg == "--user-data-dir":
                        if index + 1 >= len(args):
                            return False
                        value = args[index + 1]
                    else:
                        continue
                    if os.path.normcase(os.path.realpath(value.strip('"'))) == target:
                        return False
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                return False
    except Exception:
        return False
    return True


def _inspect_message_structure(page, phone_digits: str, *, current_chat: bool = False) -> dict:
    """Atomic structural read; current-chat mode explicitly does not verify identity."""
    return page.evaluate(r"""({target, currentChat}) => {
        const mains = Array.from(document.querySelectorAll('div[id="main"]'));
        const visible = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility === 'visible';
        const summary = {main_count: mains.length, visible_main_count: mains.filter(visible).length};
        const visibleMains = mains.filter(visible);
        if (currentChat && visibleMains.length === 0)
            return {...summary, status: 'info', reason: 'no_selected_conversation', recipient_confirmed: false};
        if (currentChat ? visibleMains.length !== 1 : (mains.length !== 1 || !visible(mains[0])))
            return {...summary, status: 'aborted', reason: 'main_not_unique_visible'};
        const main = currentChat ? visibleMains[0] : mains[0];
        if (!currentChat) {
        if (main.querySelectorAll('header').length !== 1 ||
            main.querySelectorAll('[data-testid="conversation-compose-box-input"]').length !== 1)
            return {...summary, status: 'aborted', reason: 'conversation_ui_not_unique'};
        const titles = main.querySelectorAll('header [data-testid="conversation-info-header-chat-title"], header [data-testid="chat-subtitle"]');
        // Exact full-number evidence only; a contact name or "you" label is insufficient.
        const confirmed = Array.from(titles).some(el => {
            const text = (el.innerText || '').trim();
            return /^[+\d\s().-]+$/.test(text) && text.replace(/\D/g, '') === target;
        });
        if (!confirmed) return {...summary, status: 'aborted', reason: 'recipient_not_confirmed', send_attempted: false, retry_safe: true};
        }
        const selector = ':scope div[data-id].message-out, :scope div[data-id] [data-testid="tail-out"], :scope div[data-id] [data-icon="tail-out"]';
        const matched = new Set(main.querySelectorAll(selector));
        const markerSelector = '[data-id], [data-testid="msg-container"], .message-out, .message-in, [data-testid="tail-out"], [data-icon="tail-out"], [data-icon="msg-check"], [data-icon="msg-dblcheck"], [data-icon="msg-time"]';
        const nodes = Array.from(main.querySelectorAll(markerSelector));
        const describe = el => ({
            tag: ['DIV', 'SPAN', 'SVG', 'PATH', 'SECTION', 'ARTICLE', 'LI', 'UL', 'BUTTON'].includes(el.tagName.toUpperCase()) ? el.tagName.toLowerCase() : 'other',
            classes: ['message-out', 'message-in'].filter(c => el.classList.contains(c)),
            has_data_id: el.hasAttribute('data-id'),
            msg_container: el.getAttribute('data-testid') === 'msg-container',
            tail_out: el.getAttribute('data-testid') === 'tail-out' || el.getAttribute('data-icon') === 'tail-out',
            status_marker: ['msg-check', 'msg-dblcheck', 'msg-time'].find(v => el.getAttribute('data-icon') === v) || null,
            matches_current_selector: matched.has(el)
        });
        // Last structural candidates in DOM order, not a claim of chronological order.
        const recent = nodes.slice(-30).map(el => {
            const ancestors = [];
            for (let p = el.parentElement; p && p !== main && main.contains(p); p = p.parentElement) {
                if (ancestors.length === 8) break;
                ancestors.push(describe(p));
            }
            return {node: describe(el), ancestors,
                descendants: Array.from(el.querySelectorAll(markerSelector)).slice(-12).map(describe)};
        });
        return {...summary, status: 'ok', recipient_confirmed: !currentChat,
            data_id_nodes: main.querySelectorAll('div[data-id]').length,
            msg_containers: main.querySelectorAll('[data-testid="msg-container"]').length,
            outbound_matches: matched.size, structural_candidates: nodes.length,
            sample_limit: 30, recent};
    }""", {"target": phone_digits, "currentChat": current_chat})


def _inspect_stabilized_current_chat(page) -> dict:
    """Read-only sampling: minimum 2s, 1s quiet counts, maximum 5s."""
    started = time.monotonic()
    sample = _inspect_message_structure(page, "", current_chat=True)
    if sample.get("status") != "ok":
        return sample
    counts = (sample.get("msg_containers", 0), sample.get("data_id_nodes", 0))
    last_change = started
    stable = False
    while True:
        now = time.monotonic()
        remaining = 5.0 - (now - started)
        if remaining <= 0:
            break
        page.wait_for_timeout(min(250, remaining * 1000))
        sample = _inspect_message_structure(page, "", current_chat=True)
        if sample.get("status") != "ok":
            return sample
        now = time.monotonic()
        current = (sample.get("msg_containers", 0), sample.get("data_id_nodes", 0))
        if current != counts:
            counts = current
            last_change = now
        if now - started >= 2.0 and now - last_change >= 1.0:
            stable = True
            break
    # Never return the initial snapshot; read the final structure afresh.
    result = _inspect_message_structure(page, "", current_chat=True)
    if result.get("status") == "ok":
        final_counts = (result.get("msg_containers", 0), result.get("data_id_nodes", 0))
        result["structure_stabilized"] = stable and final_counts == counts
    return result


def diagnose_message_structure(receiver: str = "", *, profile_path: str = PROFILE_PATH,
                               current_chat: bool = False, interactive: bool = False,
                               progress: Callable[[str], None] = lambda message: None) -> dict:
    """Navigate/read only. Never fill, click, press, retry, or call the send path.

    Opening a conversation can mark messages read; the browser can update profile
    storage. Read-only here means no DOM mutations or message dispatch by us.
    """
    if interactive and not current_chat:
        return {"status": "aborted", "reason": "interactive_requires_current_chat"}
    if not current_chat and not re.fullmatch(r"[0-9]{10,15}", receiver or ""):
        return {"status": "aborted", "reason": "full_numeric_phone_required"}
    if not _lock.acquire(blocking=False):
        return {"status": "aborted", "reason": "driver_busy"}
    session = None
    try:
        if not _diagnostic_profile_available(profile_path):
            return {"status": "aborted", "reason": "profile_busy_missing_or_unverifiable"}
        session = PlaywrightSession(profile_path=profile_path)
        # Chromium's own profile lock is the final guard against a startup race.
        session.__enter__()
        if current_chat:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            # No navigation: if the profile opens blank, the user must open WA.
            progress("Aguardando WhatsApp Web e seleção manual por até 60 segundos. "
                     "Se a página estiver vazia, abra web.whatsapp.com nesta aba e selecione uma conversa. "
                     "Nenhum envio será executado."
                     if interactive else
                     "Aguardando o WhatsApp Web carregar por até 30 segundos, sem navegação automática.")
            try:
                session.page.wait_for_function(r"""interactive => {
                    if (location.origin !== 'https://web.whatsapp.com') return false;
                    const visible = el => el.getClientRects().length > 0 &&
                        getComputedStyle(el).visibility === 'visible';
                    const mains = Array.from(document.querySelectorAll('div[id="main"]')).filter(visible);
                    if (interactive) return mains.length > 0;
                    return mains.length > 0 || Array.from(document.querySelectorAll('#pane-side')).some(visible);
                }""", arg=interactive, timeout=60000 if interactive else 30000)
            except PlaywrightTimeoutError:
                progress("Prazo encerrado; fechando o navegador sem selecionar conversa ou enviar mensagens.")
                return {"status": "info", "reason": "manual_selection_timeout" if interactive else "whatsapp_load_timeout",
                        "recipient_confirmed": False}
            progress("Interface disponível; aguardando estabilização das contagens de mensagens "
                     "por até 5 segundos antes de coletar o relatório sanitizado.")
            return _inspect_stabilized_current_chat(session.page)
        session.page.goto(f"https://web.whatsapp.com/send?phone={receiver}",
                          wait_until="domcontentloaded", timeout=60000)
        session.page.wait_for_selector('div[id="main"] [data-testid="conversation-compose-box-input"]',
                                       state="visible", timeout=30000)
        return _inspect_message_structure(session.page, receiver)
    except Exception:
        # Exception messages can include private URLs and browser arguments.
        return {"status": "aborted", "reason": "diagnostic_unavailable"}
    finally:
        if session is not None:
            session.__exit__(None, None, None)
            if session.pw:
                try:
                    session.pw.stop()
                except Exception:
                    pass
        _lock.release()


def _execute_send(
    phone_digits: str,
    message: str,
    session: PlaywrightSession,
    logger: Callable[[str], None] = print,
) -> str:
    masked = _mask_phone(phone_digits)
    facts = {"platform": "WhatsApp", "to": masked, "delivery_confirmed": False}
    page = session.page
    # Temporary, opt-in diagnostics: counts/booleans only, never DOM IDs or content.
    debug_observer = os.getenv("MARK_LVI_WA_OBSERVER_DEBUG") == "1"
    baseline_data_ids = set()

    def log_observation(phase, attempt, sample, ids, new_ids, matched):
        if not debug_observer:
            return
        try:
            data_ids = set(sample.get("dataIds") or [])
            logger(
                f"[wa-observer] phase={phase} attempt={attempt} "
                f"main_exists={bool(sample.get('mainExists', False))} "
                f"data_id_nodes={int(sample.get('dataIdCount', 0))} "
                f"outbound_matches={int(matched)} outbound_ids={len(ids)} "
                f"new_ids={len(new_ids)} "
                f"data_ids_added={len(data_ids - baseline_data_ids)} "
                f"data_ids_removed={len(baseline_data_ids - data_ids)} "
                f"msg_containers={int(sample.get('msgContainerCount', 0))} "
                f"main_count={int(sample.get('mainCount', 0))} "
                f"main_visible={bool(sample.get('mainVisible', False))} "
                f"composer_empty={bool(sample.get('composeCleared', False))}"
            )
        except Exception:
            # Diagnostic sinks must not affect dispatch or its outcome.
            pass

    # 1. Navigate to target chat
    chat_url = f"https://web.whatsapp.com/send?phone={phone_digits}"
    try:
        page.goto(chat_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        return outcome.failed(
            "send_message",
            f"failed to navigate to WhatsApp Web chat: {type(e).__name__}",
            **facts,
            send_attempted=False,
        )

    time.sleep(8)

    # 2. Check for bot-check or unsupported browser
    block_check = page.evaluate("""() => {
        const t = (document.body.innerText || '').toLowerCase();
        if (t.includes('browser version not supported') || t.includes('atualize o navegador') || t.includes('não suportado'))
            return 'unsupported_browser';
        if (t.includes('captcha') || t.includes('confirme que você não é um robô'))
            return 'captcha';
        return null;
    }""")
    if block_check:
        return outcome.failed(
            "send_message",
            f"WhatsApp Web blocked access: {block_check}",
            **facts,
            send_attempted=False,
        )

    # 3. Check for QR code (session not authenticated)
    is_qr = page.evaluate("""() => {
        return !!document.querySelector('canvas')
            || !!document.querySelector('[data-ref]')
            || (document.body.innerText || '').includes('Escaneie para entrar');
    }""")
    if is_qr:
        return outcome.failed(
            "send_message",
            "WhatsApp Web session requires QR code authentication; not logged in",
            **facts,
            send_attempted=False,
        )

    # 4. Strict UI and recipient identity validation inside #main
    validation = page.evaluate("""(targetPhone) => {
        const main = document.querySelector('div[id="main"]');
        if (!main) return { ok: false, reason: "main_container_not_found" };

        const headerCount = main.querySelectorAll('header').length;
        const composerCount = main.querySelectorAll('[data-testid="conversation-compose-box-input"]').length;

        if (headerCount !== 1) {
            return { ok: false, reason: `header_not_unique (count=${headerCount})` };
        }
        if (composerCount !== 1) {
            return { ok: false, reason: `composer_not_unique (count=${composerCount})` };
        }

        const titleEl = main.querySelector('header [data-testid="conversation-info-header-chat-title"]');
        const subtitleEl = main.querySelector('header [data-testid="chat-subtitle"]');

        const titleText = titleEl ? (titleEl.innerText || '').trim() : '';
        const subtitleText = subtitleEl ? (subtitleEl.innerText || '').trim() : '';

        // No verified account-number source: "you" alone cannot bind a target.
        // Only a full phone-number field is evidence, never a name or suffix.
        const recipientConfirmed = [titleText, subtitleText].some(text =>
            /^[+\\d\\s().-]+$/.test(text) && text.replace(/\\D/g, '') === targetPhone);

        if (!recipientConfirmed) {
            return {
                ok: false,
                reason: "recipient_identity_unconfirmed_no_safe_evidence"
            };
        }

        const outNodes = main.querySelectorAll(':scope div[data-id].message-out, :scope div[data-id] [data-testid="tail-out"], :scope div[data-id] [data-icon="tail-out"]');
        const outboundIds = [];
        for (const node of outNodes) {
            const el = node.hasAttribute('data-id') ? node : node.closest('div[data-id]');
            const did = el ? el.getAttribute('data-id') : null;
            if (did && !outboundIds.includes(did)) {
                outboundIds.push(did);
            }
        }

        return {
            ok: true,
            mainExists: true,
            dataIdCount: main.querySelectorAll('div[data-id]').length,
            composeCleared: (main.querySelector('[data-testid="conversation-compose-box-input"]').innerText || '').trim() === '',
            baselineOutboundCount: outNodes.length,
            dataIds: Array.from(main.querySelectorAll('div[data-id]'), node => node.getAttribute('data-id')),
            msgContainerCount: main.querySelectorAll('[data-testid="msg-container"]').length,
            mainCount: document.querySelectorAll('div[id="main"]').length,
            mainVisible: main.getClientRects().length > 0 && getComputedStyle(main).visibility === 'visible',
            baselineOutboundIds: outboundIds
        };
    }""", phone_digits)

    if not validation.get("ok"):
        reason = validation.get("reason", "validation_failed")
        return outcome.failed(
            "send_message",
            f"aborted before send: {reason}",
            **facts,
            send_attempted=False,
            retry_safe=True,
        )

    baseline_outbound = validation.get("baselineOutboundCount", 0)
    baseline_ids = set(validation.get("baselineOutboundIds") or [])
    baseline_data_ids = set(validation.get("dataIds") or [])
    log_observation("baseline", 0, validation, baseline_ids, set(), baseline_outbound)

    # 5. Locate composer immediately before typing
    composer_locator = page.locator('div[id="main"] [data-testid="conversation-compose-box-input"]')
    if composer_locator.count() != 1:
        return outcome.failed(
            "send_message",
            f"composer locator count != 1 immediately before typing (count={composer_locator.count()})",
            **facts,
            send_attempted=False,
        )

    # 6. Type and send (Point of No Return)
    try:
        composer_locator.click()
        time.sleep(0.3)
        composer_locator.fill(message)
        time.sleep(0.3)
        composer_locator.press("Enter")
    except Exception as e:
        return outcome.unverified(
            "send_message",
            f"exception while typing or dispatching message: {type(e).__name__}",
            **facts,
            send_attempted=True,
            retry_safe=False,
        )

    # 7. Observe DOM for appearance of a new outbound message node / data-id
    # Poll up to 6 seconds (checking every 0.5s) to detect a new outbound message id
    # Do NOT press Enter again if result is ambiguous.
    new_id_found = False
    new_outbound_count = 0
    compose_cleared = False

    poll_start = time.monotonic()
    timeout_s = 6.0
    attempt = 0
    while (time.monotonic() - poll_start) < timeout_s:
        attempt += 1
        time.sleep(0.5)
        observation = page.evaluate("""() => {
            const main = document.querySelector('div[id="main"]');
            if (!main) return { mainExists: false, dataIdCount: 0, dataIds: [], msgContainerCount: 0, mainCount: 0, mainVisible: false, newOutboundCount: 0, outboundIds: [], composeCleared: false };

            const outNodes = main.querySelectorAll(':scope div[data-id].message-out, :scope div[data-id] [data-testid="tail-out"], :scope div[data-id] [data-icon="tail-out"]');
            const outboundIds = [];
            for (const node of outNodes) {
                const el = node.hasAttribute('data-id') ? node : node.closest('div[data-id]');
                const did = el ? el.getAttribute('data-id') : null;
                if (did && !outboundIds.includes(did)) {
                    outboundIds.push(did);
                }
            }
            const composeBox = main.querySelector('[data-testid="conversation-compose-box-input"]');
            const composeCleared = composeBox ? (composeBox.innerText || '').trim() === '' : false;

            return {
                newOutboundCount: outNodes.length,
                dataIds: Array.from(main.querySelectorAll('div[data-id]'), node => node.getAttribute('data-id')),
                msgContainerCount: main.querySelectorAll('[data-testid="msg-container"]').length,
                mainCount: document.querySelectorAll('div[id="main"]').length,
                mainVisible: main.getClientRects().length > 0 && getComputedStyle(main).visibility === 'visible',
                mainExists: true,
                dataIdCount: main.querySelectorAll('div[data-id]').length,
                outboundIds,
                composeCleared
            };
        }""")
        if not observation:
            continue

        curr_ids = set(observation.get("outboundIds") or [])
        new_outbound_count = observation.get("newOutboundCount", 0)
        compose_cleared = observation.get("composeCleared", False)

        # Check if any new outbound id has appeared
        diff_ids = curr_ids - baseline_ids
        log_observation("poll", attempt, observation, curr_ids, diff_ids, new_outbound_count)
        if diff_ids:
            new_id_found = True
            break
        # Also fall back to outbound count increase if data-id is not yet populated
        if new_outbound_count > baseline_outbound:
            new_id_found = True
            break

    # 8. Return strictly typed outcome
    if new_id_found:
        return outcome.done(
            "send_message",
            platform="WhatsApp",
            to=masked,
            verified=True,
            evidence="new_outbound_message_node_in_dom",
            sent_in_ui=True,
            delivery_confirmed=False,
        )

    if compose_cleared:
        return outcome.unverified(
            "send_message",
            "composer was cleared after Enter, but new outbound DOM node was not yet rendered",
            **facts,
            send_attempted=True,
            retry_safe=False,
        )

    return outcome.unverified(
        "send_message",
        "message was dispatched to composer, but neither clearing nor new outbound node was observed",
        **facts,
        send_attempted=True,
        retry_safe=False,
    )


def send(
    receiver: str,
    message: str,
    *,
    force_resend: bool = False,
    session_factory: Callable[[], PlaywrightSession] = PlaywrightSession,
    logger: Callable[[str], None] = print,
) -> str:
    """Public entry point for sending a WhatsApp message via WhatsApp Web.

    Enforces:
    - Numeric full phone numbers with country code (DDI)
    - Anti-duplicate cache (normalizing trivial space/case variations) and single-flight lock
    - Zero automatic retries
    - Sanitized logging
    """
    phone_digits = _sanitize_digits(receiver)
    if not phone_digits or len(phone_digits) < 10:
        return outcome.failed(
            "send_message",
            "WhatsApp Web requires a full phone number with country code (DDI)",
            platform="WhatsApp",
            to=_mask_phone(receiver),
            send_attempted=False,
        )

    if not _lock.acquire(blocking=False):
        return outcome.failed(
            "send_message",
            "another WhatsApp operation is still running; not sent",
            platform="WhatsApp",
            to=_mask_phone(phone_digits),
            send_attempted=False,
        )

    norm_msg = _normalize_text(message)
    key = hashlib.sha256((phone_digits + "\0" + norm_msg).encode()).hexdigest()
    now = time.perf_counter()
    for old in list(_recent):
        if now - _recent[old][0] > _REPEAT_WINDOW:
            del _recent[old]

    if not force_resend and key in _recent:
        result = _recent[key][1]
        _lock.release()
        return result + " duplicate_suppressed=true -- No new send attempted; check the previous message."

    try:
        with session_factory() as session:
            result = _execute_send(phone_digits, message, session, logger=logger)
    except Exception as exc:
        result = outcome.failed(
            "send_message",
            f"WhatsApp Web driver error: {type(exc).__name__}",
            platform="WhatsApp",
            to=_mask_phone(phone_digits),
            send_attempted=False,
        )
    finally:
        if "send_attempted=true" in result or "status=done" in result:
            _recent[key] = (time.perf_counter(), result)
        _lock.release()

    return result

