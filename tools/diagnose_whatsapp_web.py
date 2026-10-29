"""Read-only structural diagnostic; target supplied privately via environment."""
import json
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.whatsapp_web import diagnose_message_structure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-chat", action="store_true",
                        help="Inspect the already selected conversation without navigation or recipient validation.")
    parser.add_argument("--interactive", action="store_true",
                        help="With --current-chat, wait up to 60 seconds for manual conversation selection.")
    args = parser.parse_args(argv)
    if args.interactive and not args.current_chat:
        parser.error("--interactive requires --current-chat")
    if args.current_chat:
        result = diagnose_message_structure(current_chat=True, interactive=args.interactive,
                                            progress=lambda message: print(message, file=sys.stderr, flush=True))
    else:
        result = diagnose_message_structure(os.getenv("WA_TEST_PHONE", ""))
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()