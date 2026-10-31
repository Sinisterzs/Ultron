# A single Setup containing only the wizard and source payload. Libraries download on install.
from pathlib import Path
import runpy
import json

root = Path(SPECPATH).parent
helper = runpy.run_path(str(root / "installer/prepare_payload.py"))
launcher = root / "dist/ULTRON.exe"
manifest = helper["create_manifest"](root, launcher=launcher)
generated = root / "installer/generated"
generated.mkdir(parents=True, exist_ok=True)
(generated / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
datas = [(str(root / name), str(Path("payload/app") / Path(name).parent)) for name in manifest["files"]]
datas += [(str(generated / "manifest.json"), "payload"),
          (str(root / "installer/runtime.json"), "payload"),
          (str(launcher), "payload"),
          (str(root / "config/setup.ico"), "config")]
a = Analysis([str(root / "bootstrap_entry.py")], pathex=[str(root)], datas=datas,
             binaries=[], hiddenimports=[], hookspath=[], runtime_hooks=[],
             excludes=["PySide6", "PyQt5", "numpy", "torch", "tensorflow", "google",
                       "sounddevice", "spotipy", "cryptography", "keyring", "tkinter"], noarchive=False)
# Qt uses Windows' ICU forwarding DLLs. An unrelated Poppler on PATH can make
# dependency discovery collect an incompatible ICU with the same filename.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.lower().startswith("icu")
              and Path(entry[0]).name.lower() != "qmodernwindowsstyle.dll"]
# Fusion is selected explicitly. The unused native Windows style plugin can
# retain a DLL handle during onefile cleanup; do not ship it in the bootstrap.
# Older build Pythons can ship a CRT older than the one required by current Qt.
# Windows loads the root runtime first; keep the ABI-compatible newer Qt copies there.
import PyQt6
qt_bin = Path(PyQt6.__file__).parent / "Qt6/bin"
for crt in ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
    newer = qt_bin / crt
    if newer.is_file():
        a.binaries = [entry for entry in a.binaries if entry[0].lower() != crt.lower()]
        a.binaries.append((crt, str(newer), "BINARY"))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="ULTRON-Setup",
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / "config/setup.ico"))
