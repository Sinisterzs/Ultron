"""Prototype: Single-Message Send via WhatsApp Web (Playwright).

Separate prototype script for controlled, single-shot message sending test.
Not connected to Mark LVI core/actions runtime.

Safety invariants:
- Uses existing Chromium persistent profile.
- Accepts strictly numeric test phone via WA_TEST_PHONE.
- Navigates to target conversation by URL.
- Verifies uniqueness of header and compose box within #main.
- Validates recipient identity elements (aborts if unconfirmed).
- Explicit manual confirmation prompt in terminal before typing/sending.
- Sends exactly one test message.
- Observes DOM for appearance of a new outbound node (does NOT claim delivery).
- Never retries automatically on ambiguous or failure results.
- Masked phone logging; zero leak of message content.
- Leaves core/ and actions/ completely untouched.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.app_paths import data_root
PROFILE_PATH = str(data_root() / "browser-profiles/whatsapp-web")


def _mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return "****"
    return f"...{phone[-4:]}"


def main() -> None:
    phone = os.getenv("WA_TEST_PHONE", "").strip()
    if not phone.isdigit() or len(phone) < 8:
        print("[ERROR] WA_TEST_PHONE must be set to a valid numeric phone number.")
        sys.exit(1)

    masked_phone = _mask_phone(phone)
    print("=" * 70)
    print("WhatsApp Web Prototype - Single Message Send")
    print(f"Target recipient: {masked_phone} (masked)")
    print("=" * 70)

    try:
        pw = sync_playwright().start()
        context = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_PATH,
            headless=False,
            no_viewport=True,
            args=["--start-maximized"],
        )
    except Exception as e:
        print(f"[ERROR] Failed to launch Chromium context: {type(e).__name__}")
        sys.exit(1)

    page = context.pages[0] if context.pages else context.new_page()

    try:
        print("[Prototype] Navigating to WhatsApp Web …")
        page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # 1. Block / unsupported-browser guard
        block_check = page.evaluate("""() => {
            const t = (document.body.innerText || '').toLowerCase();
            if (t.includes('browser version not supported') || t.includes('atualize o navegador') || t.includes('não suportado'))
                return 'unsupported_browser';
            if (t.includes('captcha') || t.includes('confirme que você não é um robô'))
                return 'captcha';
            return null;
        }""")
        if block_check:
            print(f"[ABORT] Bot-check or unsupported browser detected ({block_check}).")
            return

        # 2. QR Code gate
        is_qr = page.evaluate("""() => {
            return !!document.querySelector('canvas')
                || !!document.querySelector('[data-ref]')
                || (document.body.innerText || '').includes('Escaneie para entrar');
        }""")
        if is_qr:
            print("\n[AUTH REQUIRED] QR Code screen present. Scan with phone, then press Enter.")
            input("Press Enter after QR scan … ")
            time.sleep(3)

        # 3. Navigate to target chat
        print(f"[Prototype] Opening conversation for target {masked_phone} …")
        page.goto(f"https://web.whatsapp.com/send?phone={phone}", wait_until="domcontentloaded", timeout=60000)
        print("[Prototype] Waiting for UI to stabilize (10s) …")
        time.sleep(10)
        # 4. Verify exact uniqueness and recipient identity (you-label) within #main
        validation = page.evaluate("""() => {
            const main = document.querySelector('div[id="main"]');
            if (!main) return { ok: false, reason: "main_not_found" };

            // Exact count checks: each must match exactly 1 element
            const headerCount = main.querySelectorAll('header').length;
            const composerCount = main.querySelectorAll('[data-testid="conversation-compose-box-input"]').length;
            const youLabelCount = main.querySelectorAll('header [data-testid="you-label"]').length;

            const headerUnique = (headerCount === 1);
            const composerUnique = (composerCount === 1);
            const youLabelUnique = (youLabelCount === 1);

            // Baseline count of outbound nodes before sending
            const outNodes = main.querySelectorAll('div[data-id].message-out, div[data-id] [data-testid="tail-out"], div[data-id] [data-icon="tail-out"]');

            let reason = "ok";
            if (!headerUnique) reason = `header_not_unique (count=${headerCount})`;
            else if (!composerUnique) reason = `composer_not_unique (count=${composerCount})`;
            else if (!youLabelUnique) reason = `you_label_not_unique (count=${youLabelCount})`;

            return {
                ok: headerUnique && composerUnique && youLabelUnique,
                headerCount,
                composerCount,
                youLabelCount,
                baselineOutboundCount: outNodes.length,
                reason
            };
        }""")

        print(f"[Prototype] Validation: ok={validation.get('ok')}, reason={validation.get('reason')}")

        # 5. Abort if recipient identity/UI cannot be confirmed
        if not validation.get("ok"):
            print(f"[ABORT] Cannot confirm conversation safely: {validation.get('reason')}. Aborting.")
            return

        baseline_outbound = validation.get("baselineOutboundCount", 0)
        print(f"[Prototype] Identity and UI confirmed. Baseline outbound messages: {baseline_outbound}")

        # 6. Explicit manual confirmation in terminal
        test_message = "Teste automatizado Mark LVI"
        print("\n" + "=" * 70)
        print("CONFIRMATION REQUIRED:")
        print(f"Target: {masked_phone}")
        print(f"Action: Send 1 single test message ({len(test_message)} chars)")
        print("Safety: No retries will be performed regardless of outcome.")
        print("=" * 70)

        confirm = input("Type 'ENVIAR' to confirm message dispatch: ").strip()
        if confirm != "ENVIAR":
            print("[ABORT] Dispatch canceled by user. Nothing sent.")
            return

        # 7. Locate composer and dispatch single message
        composer_locator = page.locator('div[id="main"] [data-testid="conversation-compose-box-input"]')
        if composer_locator.count() != 1:
            print(f"[ABORT] Composer locator count != 1 immediately before typing (count={composer_locator.count()}). Aborting.")
            return

        print("[Prototype] Focusing composer and typing message …")
        composer_locator.click()
        time.sleep(0.5)
        composer_locator.fill(test_message)
        time.sleep(0.5)

        print("[Prototype] Pressing Enter to send …")
        composer_locator.press("Enter")
        time.sleep(4)

        # 8. Check for appearance of new outbound message node (does NOT claim delivery)
        observation = page.evaluate("""() => {
            const main = document.querySelector('div[id="main"]');
            if (!main) return { newOutboundCount: 0, composeCleared: false };

            const outNodes = main.querySelectorAll('div[data-id].message-out, div[data-id] [data-testid="tail-out"], div[data-id] [data-icon="tail-out"]');
            const composeBox = main.querySelector('[data-testid="conversation-compose-box-input"], footer div[contenteditable="true"]');
            const composeCleared = composeBox ? (composeBox.innerText || '').trim() === '' : false;

            return {
                newOutboundCount: outNodes.length,
                composeCleared
            };
        }""")

        new_outbound_count = observation.get("newOutboundCount", 0)
        compose_cleared = observation.get("composeCleared", False)

        print("-" * 70)
        print("[Prototype] Observation Result:")
        print(f"  Composer cleared: {compose_cleared}")
        print(f"  Outbound nodes: baseline={baseline_outbound} -> current={new_outbound_count}")

        if new_outbound_count > baseline_outbound:
            print("  Status: Outbound message node detected in DOM.")
            print("  Note: Confirms DOM dispatch only; NOT delivery or recipient receipt.")
        elif compose_cleared:
            print("  Status: Composer cleared, outbound message pending/rendering.")
            print("  Note: Outcome is pending; NO retry will be performed.")
        else:
            print("  Status: Ambiguous or failed dispatch.")
            print("  Note: Per safety rule, NO automatic retry will be performed.")
        print("-" * 70)

    except Exception as e:
        print(f"[ERROR] Prototype error during execution: {type(e).__name__}")
    finally:
        print("[Prototype] Closing browser context …")
        try:
            context.close()
            pw.stop()
        except Exception:
            pass
        print("[Prototype] Finished.")


if __name__ == "__main__":
    main()
