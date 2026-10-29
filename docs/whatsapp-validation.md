# WhatsApp Desktop: validation and limits

No real messages are sent by the automated tests:

```powershell
python -m unittest discover -s tests -p test_whatsapp_desktop.py -v
```

## Manual validation (only when the user chooses to send a real message)

1. Use your own test conversation and a unique, harmless message per run.
2. Start Mark LVI from a terminal and leave WhatsApp already open for the first run.
3. Request exactly one send. Do not interact with the keyboard/mouse during it.
4. Read the `[PERF]` detection, startup, search, input, confirmation and total
   lines. These are measured with `perf_counter`, not estimated performance.
5. Check the contact, message and outgoing state manually. `done` means evidence
   of a new outgoing message with a sent state, not recipient delivery.
6. Repeat with WhatsApp closed and a different message. Compare startup vs the
   already-open run. A zero launch count is covered by mocks; no live benchmark
   or speedup claim is made by this change.
7. If `unverified`, inspect the conversation before doing anything else. Never
   retry automatically. Identical recipient/text attempts are suppressed in RAM
   for 120 seconds after any send attempt, including successful sends.
8. For a negative test, request a nonexistent contact: there must be no send.

## Limits

## Query regression fix

- Queries resolve the accessible Document through a bounded child traversal,
  rather than enumerating the entire outer host window. Search queries request
  Edit/ComboBox controls and check the chat-search label and Tab/Button sibling
  structure observed in the installed application's accessibility tree.
- RuntimeId deduplication is local to each enumeration. IDs are never persisted
  or reused as selectors. Each control query resolves the Document again, and
  controls are reacquired after search, composition and at the send boundary.
  Two distinct candidates/documents still cause refusal.
- Each stage now checks its absolute deadline before and after queries; an
  exhausted budget cannot start another probe, and late successes are rejected.
  A native/COM call already running cannot always be interrupted: its elapsed
  time can exceed the stage budget, but its result cannot authorize the next
  action. The existing total caller deadline and cancellation lock still apply.
- Wrappers are constructed directly from HWNDs, avoiding implicit window-find
  retries (`wrapper_object()` has no timeout argument in version 0.6.9). Global pywinauto Timings
  are not changed. No additional retries or second send are introduced.
- New diagnostics: `[PERF] WhatsApp root resolution`,
  `[PERF] WhatsApp control enumeration`,
  `[PERF] WhatsApp identity deduplication`, and
  `[UIA] enumeration raw=N unique=M`. These contain no contact/message names.
- Windows WhatsApp progress is logged as `[SendMessage][progress]`, not as a
  `status=started` outcome. Its actual tool return remains the final outcome.

## Remaining limits

- Opening 8 s, conversation 6 s, input verification 3 s, confirmation 3 s;
  caller deadline 24 s. Individual native/COM calls may not be interruptible.
  The caller returns at its deadline; a stalled worker retains the operation
  lock until it exits, and cancellation checks prevent subsequent send steps.
- UIA and Win32 control backends are tried. Keyboard/clipboard fallback only
  fills a resolved, focused, readable input; a send is never retried. Unknown
  controls/ambiguous recipients cause refusal, not blind typing.
- Supported names currently cover English and Portuguese. Header and outgoing
  message accessibility schemas must be recognized. These selectors have NOT
  been validated against a real WhatsApp installation. Unsupported header means
  no send; unsupported outgoing evidence means immediate `unverified` after the
  single send attempt. An empty composer alone is never evidence of sending.
- `delivery_confirmed` is deliberately false: the current adapter cannot bind
  a receipt to a stable ID of the new message. No delivered/read claim is made.
- Counts of matching outgoing messages reject old identical messages; dynamic
  virtualization or an unsupported schema can still prevent confirmation.
- Existing drafts are never overwritten. A timeout before sending may leave a
  composed draft. Inspect it rather than retrying blindly.
- Deduplication is process-local and expires; restarting Mark LVI clears it.
- No WhatsApp data, credentials or personal settings are written by the driver.
- Other platforms keep their existing background flow. The Windows WhatsApp
  path returns the final result through the existing action executor.