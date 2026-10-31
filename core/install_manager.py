"""Online bootstrap: a private runtime, verified payload and real preparation events.

Nothing installs on import. The caller explicitly invokes install() from a worker.
No command uses the application's frozen executable as a Python interpreter.
"""
from __future__ import annotations

import hashlib
from collections import deque
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from core.app_paths import data_root, resource_root


class InstallationCancelled(Exception):
    pass


def check_cancelled(cancel):
    if cancel():
        raise InstallationCancelled("Preparação cancelada. Você pode tentar novamente.")


def verified_launcher(bundle, manifest):
    """Verify the separately branded executable before any download/write."""
    digest = manifest.get("launcher_sha256")
    if digest is None:
        return None  # backward-compatible source fixtures/older payloads
    source = Path(bundle) / "ULTRON.exe"
    if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or source.is_symlink() or not source.is_file()
            or hashlib.sha256(source.read_bytes()).hexdigest() != digest):
        raise ValueError("O executável do aplicativo não passou na verificação de integridade.")
    return source


def checked_child(root: Path, relative: str) -> Path:
    rel = PurePosixPath(relative.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or ":" in relative:
        raise ValueError("Invalid installation payload path")
    target = root.joinpath(*rel.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Installation path escapes its destination")
    return target


def download_verified(url, digest, destination, emit, cancel=lambda: False):
    """Download over HTTPS; commit only after validating the pinned SHA-256."""
    from urllib.parse import urlsplit
    if urlsplit(url).scheme != "https" or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("A trusted HTTPS URL and SHA-256 are required")
    destination = Path(destination)
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
        emit("Download já verificado", 1, 1)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ULTRON-Setup/1"})
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open("wb") as stream:
            if not response.geturl().startswith("https://"):
                raise ValueError("Insecure download redirect")
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            checksum = hashlib.sha256()
            while True:
                check_cancelled(cancel)
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > 150 * 1024 * 1024:
                    raise ValueError("Runtime download exceeds expected size")
                stream.write(chunk); checksum.update(chunk)
                emit("Baixando ambiente do aplicativo", received, total)
            if total and received != total:
                raise OSError("Incomplete runtime download")
            if checksum.hexdigest() != digest:
                raise ValueError("O download não passou na verificação de integridade.")
        check_cancelled(cancel)
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def extract_runtime(archive, target):
    target = Path(target)
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 20000 or sum(x.file_size for x in entries) > 500 * 1024 * 1024:
            raise ValueError("Unexpected runtime archive size")
        for entry in entries:
            checked_child(target, entry.filename)
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Runtime links are not allowed")
        target.mkdir(parents=True, exist_ok=True)
        bundle.extractall(target)


def redact_install_output(text):
    """Keep local diagnostics useful without logging authentication material."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(?i)(https?://)[^/\s:@]+:[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)(authorization\s*:\s*)(?:Bearer|Basic)\s+\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\b((?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password)\s*[:=]\s*)[^\s,;]+",
                  r"\1[REDACTED]", text)
    return text


def run_task(command, emit, cancel=lambda: False, *, env=None, cwd=None, timeout=1800, log_path=None):
    """Run a setup stage off the GUI thread and preserve sanitized diagnostics."""
    check_cancelled(cancel)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    process = None
    logfile = None
    tail = deque(maxlen=50)
    try:
        if log_path is not None:
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "w" if path.exists() and path.stat().st_size > 2 * 1024 * 1024 else "a"
            logfile = path.open(mode, encoding="utf-8")
            logfile.write("\n=== Etapa de preparação ===\n")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd, **options)
        lines = queue.Queue()

        def read():
            try:
                for line in process.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        deadline = time.monotonic() + timeout
        while True:
            check_cancelled(cancel)
            if time.monotonic() > deadline:
                raise TimeoutError("Esta etapa excedeu o tempo limite. Tente novamente.")
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is None:
                break
            clean = redact_install_output(line)
            tail.append(clean)
            if logfile:
                logfile.write(clean); logfile.flush()
            match = re.search(r"^Collecting ([A-Za-z0-9_.-]+)", line)
            if match:
                emit("Baixando " + match.group(1)[:70], 0, 0)
            elif line.startswith("Installing collected packages"):
                emit("Instalando bibliotecas no ambiente privado", 0, 0)
        if process.wait(timeout=20) != 0:
            detail = "".join(tail)
            if "setuptools.build_meta" in detail or "BackendUnavailable" in detail:
                reason = "Não foi possível carregar as ferramentas de preparação das bibliotecas."
            elif "No matching distribution found" in detail:
                reason = "Uma biblioteca não tem uma versão compatível disponível neste ambiente."
            elif any(word in detail for word in ("ConnectionError", "ReadTimeout", "CERTIFICATE_VERIFY_FAILED", "Temporary failure")):
                reason = "Falha de conexão ao obter os componentes."
            else:
                reason = "Uma etapa de instalação falhou."
            raise RuntimeError(reason + " Consulte o registro de instalação para ver os detalhes.")
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill(); process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
        if logfile:
            logfile.close()


def installation_root():
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Este instalador é destinado ao Windows x64.")
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    return local / "Programs/ULTRON"


def configure_runtime(spec, archive, pip, runtime):
    runtime = Path(runtime)
    extract_runtime(archive, runtime)
    shutil.copy2(pip, runtime / "pip.whl")
    (runtime / "Lib/site-packages").mkdir(parents=True, exist_ok=True)
    pth = runtime / (spec["archive"].removesuffix(".zip") + "._pth")
    pth.write_text(spec["archive"] + "\n.\nLib/site-packages\npip.whl\n../app\nimport site\n", encoding="utf-8")


def install(emit, cancel=lambda: False, *, bundle_root=None, target=None, browser=False):
    from core.runtime_lock import application_lock
    with application_lock():
        return _install(emit, cancel, bundle_root=bundle_root, target=target, browser=browser)


def _install(emit, cancel=lambda: False, *, bundle_root=None, target=None, browser=False):
    """Prepare files and dependencies. Credentials are deliberately not an argument."""
    bundle = Path(bundle_root) if bundle_root else resource_root() / "payload"
    target = Path(target) if target else installation_root()
    if target.is_symlink():
        raise ValueError("Installation target cannot be a symbolic link")
    spec = json.loads((bundle / "runtime.json").read_text(encoding="utf-8"))
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    cache = data_root() / "downloads"
    runtime = target / "runtime"
    app = target / "app"
    emit("Verificando os arquivos do aplicativo", 0, 0)
    verified = []
    launcher = verified_launcher(bundle, manifest)
    if launcher is not None:
        verified.append((launcher, target / "ULTRON.exe"))
    for relative, digest in manifest["files"].items():
        check_cancelled(cancel)
        source = checked_child(bundle / "app", relative)
        dest = checked_child(app, relative)
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("O pacote do aplicativo foi alterado ou está incompleto.")
        verified.append((source, dest))
    archive = download_verified(spec["runtime_url"], spec["runtime_sha256"], cache / "python-runtime.zip", emit, cancel)
    emit("Preparando ambiente privado", 0, 0)
    pip = download_verified(spec["pip_url"], spec["pip_sha256"], cache / "pip.whl", emit, cancel)
    configure_runtime(spec, archive, pip, runtime)
    for source, dest in verified:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    python = runtime / "python.exe"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None)
    env["PYTHONUTF8"] = "1"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(data_root() / "browsers")
    log = data_root() / "logs/setup-install.log"
    emit("Preparando ferramentas de instalação", 0, 0)
    # Embedded Python ignores pip's temporary build environment paths. Install
    # the build backend in our own runtime before preparing source packages.
    # Keep setuptools below 81 for legacy packages that still use pkg_resources.
    run_task([str(python), "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
              "--no-warn-script-location", "--progress-bar", "off", "--only-binary=:all:",
              "--index-url", "https://pypi.org/simple", "setuptools>=70,<81", "wheel>=0.45,<1"],
             emit, cancel, env=env, cwd=app, log_path=log)
    emit("Baixando e instalando as bibliotecas necessárias", 0, 0)
    run_task([str(python), "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
              "--no-warn-script-location", "--progress-bar", "off", "--no-build-isolation",
              "--index-url", "https://pypi.org/simple", "-r", str(app / "requirements.txt")],
             emit, cancel, env=env, cwd=app, log_path=log)
    if browser:
        emit("Baixando navegador para automação web", 0, 0)
        run_task([str(python), "-m", "playwright", "install", "chromium"], emit, cancel, env=env, cwd=app, log_path=log)
    emit("Conferindo o ambiente instalado", 0, 0)
    run_task([str(python), "-c", "import numpy, sounddevice, spotipy, fastapi, pyautogui; from PyQt6.QtWidgets import QApplication; from google import genai"],
             emit, cancel, env=env, cwd=app, timeout=90, log_path=log)
    check_cancelled(cancel)
    emit("Ambiente preparado", 1, 1)
    return target


def check_local_environment(emit, cancel=lambda: False):
    """For an existing/source install: inspect actual availability, never fake a download."""
    import importlib.util
    for name in ("numpy", "sounddevice", "google.genai", "spotipy"):
        check_cancelled(cancel)
        emit("Conferindo componentes do aplicativo", 0, 0)
        try:
            available = importlib.util.find_spec(name)
        except ModuleNotFoundError:
            available = None
        if not available:
            raise RuntimeError("Faltam componentes. Execute o instalador completo para prepará-los.")
    emit("Componentes disponíveis", 1, 1)
