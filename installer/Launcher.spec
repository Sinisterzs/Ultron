"""Standalone entry executable with application branding, without Qt/setup UI."""
from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis([str(root / "installed_entry.py")], pathex=[str(root)],
             binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=["PyQt6", "PySide6", "numpy", "google", "sounddevice", "tkinter"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="ULTRON",
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / "config/jarvis.ico"))
