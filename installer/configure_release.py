"""Set public build identity. No tokens or credentials are accepted."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.updates import version_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("repository must be owner/name")
    version = args.version.removeprefix("v")
    version_key(version)
    (ROOT / "release_config.json").write_text(json.dumps({"version": version,
        "github_repository": args.repository, "check_interval_minutes": 5}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
