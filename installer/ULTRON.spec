# Windows baseline build: Gemini, desktop tools, dashboard and Spotify.
from pathlib import Path

root = Path(SPECPATH).parent
hidden = []
datas = []
for package in ("actions", "plugins", "providers", "memory", "core", "dashboard", "config"):
    for file in (root / package).glob("*.py"):
        if file.name == "_tests.py":
            continue
        hidden.append(f"{package}.{file.stem}" if file.stem != "__init__" else package)
        if package in ("actions", "plugins"):
            datas.append((str(file), package))  # File-based discovery uses real .py paths.
datas += [(str(root / "core/prompt.txt"), "core"),
          (str(root / "core/face_model.obj"), "core"),
          (str(root / "config/jarvis.ico"), "config"),
          (str(root / "config/jarvis.png"), "config"),
          (str(root / "config/setup.ico"), "config"),
          (str(root / "release_config.json"), "."),
          (str(root / "dashboard/static"), "dashboard/static"),
          (str(root / "LICENSE"), ".")]

a = Analysis([str(root / "ultron_entry.py")], pathex=[str(root)],
             binaries=[], datas=datas, hiddenimports=hidden,
             hookspath=[], runtime_hooks=[],
             excludes=["PySide6", "PyQt5", "tkinter", "torch", "tensorflow",
                       "faster_whisper", "piper", "openwakeword", "kokoro", "vosk"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ULTRON",
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / "config/jarvis.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ULTRON")
