"""Proof of Concept: WhatsApp Web Read-Only DOM Inspection.
Strictly read-only: no sending, clicking, typing or draft changes.
Discovers stable selectors from the live DOM and writes a sanitised report.
"""
from __future__ import annotations

import os, sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.app_paths import data_root
PROFILE_PATH = str(data_root() / "browser-profiles/whatsapp-web")
REPORTS_DIR = Path("tools/reports")

# Only these attribute VALUES are written to the report.
# Every other attribute records only its name and value length.
_VALUE_WHITELIST = frozenset({"role", "data-icon", "data-testid", "contenteditable"})

def main() -> None:
    phone = os.getenv("WA_TEST_PHONE", "").strip()
    if not phone.isdigit():
        print("ERROR: WA_TEST_PHONE must be set to a numeric phone number.")
        sys.exit(1)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"whatsapp_dom_report_{int(time.time())}.json"

    print(f"[PoC] Launching Chromium with profile {PROFILE_PATH}")
    try:
        pw = sync_playwright().start()
        context = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_PATH,
            headless=False,
            no_viewport=True,
            args=["--start-maximized"],
        )
    except Exception:
        print("ERROR: Failed to launch browser (profile may already be in use).")
        sys.exit(1)

    page = context.pages[0] if context.pages else context.new_page()

    print("[PoC] Opening https://web.whatsapp.com/ …")
    try:
        page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"[PoC] Goto warning: {type(e).__name__}")

    time.sleep(3)

    # --- block / captcha / unsupported-browser guard ---
    block_check = page.evaluate("""() => {
        const t = document.body.innerText.toLowerCase();
        if (t.includes('browser version not supported') || t.includes('atualize o navegador') || t.includes('não suportado'))
            return 'unsupported_browser';
        if (t.includes('captcha') || t.includes('confirme que você não é um robô'))
            return 'captcha';
        return null;
    }""")
    if block_check:
        label = "Unsupported browser" if block_check == "unsupported_browser" else "Captcha/bot check"
        print(f"ERROR: {label} detected. Stopping without attempting to bypass.")
        context.close(); pw.stop()
        sys.exit(1)

    # --- QR code gate ---
    is_qr = page.evaluate("""() => {
        return !!document.querySelector('canvas')
            || !!document.querySelector('[data-ref]')
            || document.body.innerText.includes('Escaneie para entrar');
    }""")
    if is_qr:
        print("\n" + "=" * 70)
        print("⚠️  QR CODE PRESENT – scan with your phone, then press Enter.")
        print("=" * 70)
        input("Press Enter after QR scan … ")
        time.sleep(3)

    # --- navigate to target chat (number never printed) ---
    chat_url = f"https://web.whatsapp.com/send?phone={phone}"
    print("[PoC] Navigating to target chat URL (phone masked)")
    try:
        page.goto(chat_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"[PoC] Chat navigation warning: {type(e).__name__}")

    print("[PoC] Waiting 10 s for UI to settle …")
    time.sleep(10)


    # --- DOM extraction (strictly scoped to #main, whitelist-sanitised) ---
    dom = page.evaluate("""() => {
        const WHITELIST = ['role', 'data-icon', 'data-testid', 'contenteditable'];
        const attrInfo = (el) => {
            if (!el || !el.attributes) return {};
            const r = {};
            for (const a of el.attributes) {
                r[a.name] = WHITELIST.includes(a.name)
                    ? a.value
                    : {name: a.name, length: a.value ? a.value.length : 0};
            }
            return r;
        };

        const mainEl = document.querySelector('div[id="main"]');
        if (!mainEl) {
            return {
                mainFound: false,
                header: null,
                composer: [],
                messages: [],
                messageSummary: { totalElementsScopedToMain: 0, realMessages: 0, systemNotifications: 0, inbound: 0, outbound: 0 },
                deliveryStatusInvestigation: "main_container_not_found"
            };
        }

        // 1. Header (inside #main only)
        const hdr = mainEl.querySelector('header');
        let header = null;
        if (hdr) {
            const hdrSubs = [...hdr.querySelectorAll('[data-testid]')].slice(0, 15).map(s => ({
                tag: s.tagName,
                attributes: attrInfo(s)
            }));
            header = {tag: hdr.tagName, attributes: attrInfo(hdr), structuralChildren: hdrSubs};
        }

        // 2. Composer (inside #main footer only)
        const ftr = mainEl.querySelector('footer');
        const cEls = ftr ? ftr.querySelectorAll('div[contenteditable="true"], [role="textbox"], input') : [];
        const composer = [...cEls].map(el => ({
            tag: el.tagName,
            attributes: attrInfo(el),
            isBlank: (el.innerText || '').trim() === '',
            textLength: (el.innerText || '').length
        }));

        // 3. Messages & Conversation Area (strictly inside #main)
        // Primary unit is outer div[data-id] to avoid duplicating internal nodes (like [data-testid="msg-container"])
        const messageOuterNodes = mainEl.querySelectorAll('div[data-id]');

        const classifiedMessages = [];

        for (const el of messageOuterNodes) {
            // Check if this outer node is a system notification (e.g. encryption or system notice)
            const isSystem = !!(
                el.querySelector('[data-testid="msg-notification-container"]') ||
                el.querySelector('[data-testid="system_message"]') ||
                el.querySelector('[data-testid="system-message-container"]') ||
                el.querySelector('[role="alert"]')
            );

            if (isSystem) {
                classifiedMessages.push({
                    tag: el.tagName,
                    attributes: attrInfo(el),
                    classification: "system_notification",
                    hasDataId: true
                });
                continue;
            }

            // Real message: determine direction based on concrete DOM evidence
            const dataId = el.getAttribute('data-id') || '';
            const hasTailOut = !!(
                el.querySelector('[data-testid="tail-out"]') ||
                el.querySelector('[data-icon="tail-out"]')
            );
            const hasTailIn = !!(
                el.querySelector('[data-testid="tail-in"]') ||
                el.querySelector('[data-icon="tail-in"]')
            );
            const isOut = el.classList.contains('message-out') ||
                dataId.startsWith('true_') ||
                dataId.includes('_true_') ||
                hasTailOut;
            const isIn = el.classList.contains('message-in') ||
                dataId.startsWith('false_') ||
                dataId.includes('_false_') ||
                hasTailIn;

            let classification = 'unknown';
            if (isOut) {
                classification = 'outbound';
            } else if (isIn) {
                classification = 'inbound';
            }

            // Status indicators / meta inspection inside real messages
            const indicators = [...el.querySelectorAll('[data-icon], [data-testid]')].slice(0, 15).map(s => ({
                tag: s.tagName,
                attributes: attrInfo(s)
            }));
            const tickIcons = [...el.querySelectorAll('[data-icon]')].slice(0, 5).map(s => s.getAttribute('data-icon'));

            classifiedMessages.push({
                tag: el.tagName,
                attributes: attrInfo(el),
                classification,
                hasDataId: true,
                indicators,
                tickIcons
            });
        }

        const outboundCount = classifiedMessages.filter(m => m.classification === 'outbound').length;
        const inboundCount = classifiedMessages.filter(m => m.classification === 'inbound').length;
        const unclassifiedCount = classifiedMessages.filter(m => m.classification === 'unknown').length;
        const realCount = outboundCount + inboundCount + unclassifiedCount;
        const systemCount = classifiedMessages.filter(m => m.classification === 'system_notification').length;

        let deliveryInvestigation = "insufficient_outbound_messages_cannot_investigate_status_indicators";
        if (outboundCount > 0) {
            deliveryInvestigation = "outbound_messages_present_indicators_inspected";
        }

        return {
            mainFound: true,
            header,
            composer,
            messages: classifiedMessages.slice(-10),
            messageSummary: {
                totalMessageUnits: classifiedMessages.length,
                realMessages: realCount,
                systemNotifications: systemCount,
                inbound: inboundCount,
                outbound: outboundCount,
                unknown: unclassifiedCount
            },
            deliveryStatusInvestigation: deliveryInvestigation
        };
    }""")

    # --- selector uniqueness and presence checks (scoped to #main where appropriate) ---
    selector_tests = {}
    selectors = {
        "header_single": ['div[id="main"] header', 'div[id="main"] [data-testid="conversation-header"]'],
        "header_identity_single": ['div[id="main"] header [data-testid="conversation-info-header-chat-title"]'],
        "composer_single": ['div[id="main"] footer div[contenteditable="true"]', 'div[id="main"] [data-testid="conversation-compose-box-input"]'],
        "main_messages_collection": ['div[id="main"] div[data-id]', 'div[id="main"] div.message-in', 'div[id="main"] div.message-out', 'div[id="main"] [data-testid="msg-container"]'],
        "main_system_collection": ['div[id="main"] [data-testid="system-message-container"]'],
        "main_tick_icons": ['div[id="main"] [data-icon="msg-check"]', 'div[id="main"] [data-icon="msg-dblcheck"]', 'div[id="main"] [data-icon="msg-time"]'],
    }

    single_element_categories = {"header_single", "header_identity_single", "composer_single"}

    for cat, lst in selectors.items():
        selector_tests[cat] = []
        is_single = cat in single_element_categories
        for sel in lst:
            try:
                cnt = page.locator(sel).count()
                result_entry = {
                    "selector": sel,
                    "count": cnt,
                }
                if is_single:
                    result_entry["unique"] = (cnt == 1)
                else:
                    result_entry["present"] = (cnt > 0)
                selector_tests[cat].append(result_entry)
            except Exception:
                selector_tests[cat].append({"selector": sel, "error": "selector_check_failed"})

    report = {
        "timestamp": time.time(),
        "phone": "[MASKED]",
        "dom": dom,
        "selector_tests": selector_tests,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PoC] Report saved to {report_path}")
    print("[PoC] Read-only inspection complete. No actions performed.")
    context.close()
    pw.stop()


if __name__ == "__main__":
    main()

