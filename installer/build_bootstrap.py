"""Build with either normal tooling or the worktree's isolated .build-tools."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tools = ROOT / ".build-tools"
if tools.is_dir():
    sys.path.insert(0, str(tools))
from PyInstaller.__main__ import run

if __name__ == "__main__":
    os.chdir(ROOT)
    os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(ROOT / ".build-tools/pyinstaller-cache"))
    run(["--noconfirm", str(ROOT / "installer/Bootstrap.spec")])
