"""Explicit allowlist for the setup payload. Never package the project directory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def payload_files(root):
    root = Path(root)
    names = ["ultron_entry.py", "installed_entry.py", "main.py", "launcher.py", "ui.py", "ui_setup.py", "ui_updates.py",
             "ui_update_install.py", "ui_theme.py", "ui_titlebar.py", "ui_activity.py", "ui_chat.py", "ui_sidebar.py", "crystal_pulse.py",
             "requirements.txt", "release_config.json", "LICENSE", "core/prompt.txt", "core/face_model.obj",
             "config/jarvis.ico", "config/jarvis.png", "config/setup.ico"]
    for package in ("core", "actions", "plugins", "providers", "memory", "config", "dashboard"):
        names.extend(p.relative_to(root).as_posix() for p in (root / package).glob("*.py") if p.name != "_tests.py")
    names.extend(p.relative_to(root).as_posix() for p in (root / "dashboard/static").iterdir()
                 if p.is_file() and p.suffix in {".html", ".js", ".css"})
    return sorted(set(names))


def create_manifest(root, launcher=None):
    root = Path(root)
    files = {}
    for name in payload_files(root):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or unsafe payload file: " + name)
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"schema": 1, "files": files}
    if launcher is not None:
        manifest["launcher_sha256"] = hashlib.sha256(Path(launcher).read_bytes()).hexdigest()
    return manifest


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    dest = root / "installer/generated/manifest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(create_manifest(root), indent=2), encoding="utf-8")
    print(dest)
