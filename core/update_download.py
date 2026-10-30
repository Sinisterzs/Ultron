"""Explicit-click update download and independent helper handoff. No work on import."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from core.app_paths import data_root, resource_root
from core.install_manager import download_verified, installation_root, check_cancelled
from core.updates import version_key


def installed_root():
    root = resource_root().parent
    if os.name != "nt" or root.resolve() != installation_root().resolve():
        raise RuntimeError("Execute o Setup novo para habilitar atualizações neste aplicativo.")
    if not (root / "install_state.json").is_file():
        raise RuntimeError("A instalação não possui registro de configuração.")
    return root


def helper_environment():
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("_PYI_") or name in {
            "PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "MARK_LVI_BOOT_STATUS"
        }:
            env.pop(name, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        base = Path(bundle).resolve()
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
            if p and not Path(p).resolve().is_relative_to(base))
    return env


def download_and_handoff(release, emit, cancel=lambda: False):
    """Return only once the verified helper is ready to wait for this process."""
    root = installed_root()
    if not release.installer_url or not release.sha256:
        raise RuntimeError("Esta versão não possui um instalador verificável. Abra a página da versão.")
    version_key(release.version)
    folder = data_root() / "updates" / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    request = folder / "request.json"
    process = None
    try:
        path = download_verified(release.installer_url, release.sha256,
                                 folder / "ULTRON-Setup.exe", emit, cancel)
        check_cancelled(cancel)
        # Check again immediately before launching, including cached downloads.
        if hashlib.sha256(path.read_bytes()).hexdigest() != release.sha256:
            raise ValueError("O instalador foi alterado após o download.")
        request.write_text(json.dumps({"version": release.version, "sha256": release.sha256,
            "parent_pid": os.getpid(), "root": str(root.resolve()), "created_at": time.time()}),
            encoding="utf-8")
        emit("Preparando a reinicialização", 0, 0)
        process = subprocess.Popen([str(path), "--apply-update", str(request)],
            cwd=str(folder), env=helper_environment(), close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            check_cancelled(cancel)
            if (folder / "ready").is_file():
                check_cancelled(cancel)
                return folder
            if process.poll() is not None:
                raise RuntimeError("O atualizador não conseguiu iniciar. O aplicativo continua aberto.")
            time.sleep(.1)
        raise RuntimeError("O atualizador não respondeu. O aplicativo continua aberto.")
    except BaseException:
        # Helper must stop waiting instead of later applying a cancelled handoff.
        (folder / "cancel").touch()
        raise
