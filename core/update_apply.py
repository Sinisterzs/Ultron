"""Independent Windows updater: stage first, swap only after graceful app exit."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

from core.app_paths import data_root, resource_root
from core.install_manager import installation_root, check_cancelled, _install
from core.runtime_lock import application_lock
from core.updates import version_key


def validate_request(path):
    path = Path(path).resolve()
    base = (data_root() / "updates").resolve()
    if path.name != "request.json" or not path.is_relative_to(base) or path.parent.parent != base:
        raise ValueError("Pedido de atualização fora da pasta esperada.")
    data = json.loads(path.read_text(encoding="utf-8"))
    root = Path(data["root"])
    if root.resolve() != installation_root().resolve():
        raise ValueError("Destino de atualização inválido.")
    if not getattr(sys, "frozen", False):
        raise RuntimeError("A atualização deve usar o Setup compilado.")
    moment = time.time()
    if not 0 <= moment - float(data["created_at"]) < 600:
        raise ValueError("O pedido de atualização expirou.")
    if int(data["parent_pid"]) <= 0:
        raise ValueError("Processo do aplicativo inválido.")
    version_key(data["version"])
    metadata = json.loads((resource_root() / "payload/app/release_config.json").read_text(encoding="utf-8"))
    if data["version"] != metadata["version"]:
        raise ValueError("O instalador não corresponde à versão solicitada.")
    if hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() != data["sha256"]:
        raise ValueError("O instalador não passou na verificação de integridade.")
    return path, data


def wait_for_app(path, pid, emit, cancel=lambda: False, *, timeout=90):
    """Hold a real process handle, preventing PID-reuse races; never force kill."""
    if os.name != "nt":
        raise RuntimeError("O atualizador é destinado ao Windows.")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    api.OpenProcess.restype = ctypes.c_void_p
    api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    api.WaitForSingleObject.restype = ctypes.c_uint32
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    api.CloseHandle.restype = ctypes.c_int
    handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        raise RuntimeError("Não foi possível acompanhar o fechamento do aplicativo.")
    try:
        check_cancelled(cancel)
        (path.parent / "ready").touch()
        emit("Aguardando o ULTRON encerrar com segurança", 0, 0)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_cancelled(cancel)
            result = api.WaitForSingleObject(handle, 100)
            if result == 0:
                return
            if result != 258:
                raise ctypes.WinError(ctypes.get_last_error())
        raise RuntimeError("O aplicativo não encerrou. Nenhum arquivo foi substituído.")
    finally:
        api.CloseHandle(handle)


def reject_links(root):
    """Never rename a junction, symlink or redirected installation."""
    root = Path(root)
    for path in (root, *root.parents):
        if path.is_symlink() or (path.exists() and getattr(path.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("A instalação usa um redirecionamento de pasta não suportado.")


COMPONENTS = ("app", "runtime", "ULTRON.exe")


def rename_with_retry(source, destination, cancel=lambda: False, *, timeout=5):
    """Allow transient Windows locks to settle, without killing processes."""
    deadline = time.monotonic() + timeout
    while True:
        check_cancelled(cancel)
        try:
            Path(source).rename(destination)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(.1)


def restore_components(root, stage, backup):
    """Restore each old component, including an interrupted promotion."""
    for name in reversed(COMPONENTS):
        old, current, pending = backup / name, root / name, stage / name
        if old.exists():
            if current.exists():
                if pending.exists():
                    raise RuntimeError("Recuperação interrompida: há arquivos conflitantes. Preserve as pastas e consulte o registro.")
                rename_with_retry(current, pending)
            rename_with_retry(old, current)


def stage_and_swap(root, emit, cancel=lambda: False, *, prepare=None, setup=None):
    """Keep the install container stable; promote app/runtime/launcher only."""
    root = Path(root).absolute()
    if root.resolve() != installation_root().resolve():
        raise ValueError("Destino de atualização inválido.")
    reject_links(root)
    if not (root / "install_state.json").is_file():
        raise ValueError("A instalação anterior não foi encontrada.")
    for name in COMPONENTS:
        reject_links(root / name)
        if not (root / name).exists():
            raise ValueError("A instalação atual está incompleta. Execute o Setup novamente.")
    prepare = prepare or _install
    setup = Path(setup or sys.executable)
    suffix = uuid.uuid4().hex
    stage = root.parent / (".ULTRON-stage-" + suffix)
    backup = root.parent / (".ULTRON-backup-" + suffix)
    stage.mkdir(exist_ok=False)
    with application_lock():
        prepare(emit, cancel, target=stage)
        check_cancelled(cancel)
        if not (stage / "ULTRON.exe").is_file():
            # Legacy payloads used the Setup itself as the installed launcher.
            shutil.copy2(setup, stage / "ULTRON.exe")
        shutil.copy2(root / "install_state.json", stage / "install_state.json")
        for relative in ("runtime/pythonw.exe", "app/ultron_entry.py", "ULTRON.exe"):
            if not (stage / relative).is_file():
                raise ValueError("A nova instalação está incompleta.")
        backup.mkdir(exist_ok=False)
        shutil.copy2(root / "install_state.json", backup / "install_state.json")
        journal = data_root() / "updates/pending.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        from core.config_store import save_config
        save_config({"schema": 2, "root": str(root), "stage": str(stage), "backup": str(backup)}, journal)
        emit("Aplicando a atualização", 0, 0)
        try:
            # Do not rename the installation container: a terminal/Explorer or
            # another directory handle can keep it open on Windows.
            for name in COMPONENTS:
                rename_with_retry(root / name, backup / name, cancel)
                rename_with_retry(stage / name, root / name, cancel)
        except BaseException as exc:
            try:
                restore_components(root, stage, backup)
            except Exception as recovery:
                raise RuntimeError("Não foi possível concluir a recuperação. As cópias e o registro foram preservados; feche o ULTRON e execute o Setup novamente.") from recovery
            journal.unlink(missing_ok=True)
            if getattr(exc, "winerror", None) in (5, 32, 33):
                raise RuntimeError("Há arquivos da instalação em uso ou sem acesso. A versão anterior foi restaurada. Feche outras instâncias do ULTRON e tente novamente.") from exc
            raise
        journal.unlink(missing_ok=True)
        emit("Atualização concluída", 1, 1)
    return backup


def recover_interrupted():
    """Recover both legacy whole-folder moves and component transactions."""
    journal = data_root() / "updates/pending.json"
    if not journal.is_file():
        return
    state = json.loads(journal.read_text(encoding="utf-8"))
    root = installation_root()
    backup, stage = Path(state["backup"]), Path(state["stage"])
    if Path(state["root"]).resolve() != root.resolve():
        raise ValueError("Registro de recuperação inválido.")
    for path, prefix in ((backup, ".ULTRON-backup-"), (stage, ".ULTRON-stage-")):
        if path.parent.resolve() != root.parent.resolve() or not path.name.startswith(prefix):
            raise ValueError("Pasta de recuperação inválida.")
        reject_links(path)
    with application_lock():
        if state.get("schema") == 2:
            if not root.is_dir():
                raise RuntimeError("A pasta instalada não foi encontrada para recuperação.")
            restore_components(root, stage, backup)
        elif not root.exists() and (backup / "install_state.json").is_file():
            backup.rename(root)
        journal.unlink(missing_ok=True)


def apply_request(path, emit, cancel=lambda: False):
    path, data = validate_request(path)
    def cancelled():
        return cancel() or (path.parent / "cancel").exists()
    wait_for_app(path, int(data["parent_pid"]), emit, cancelled)
    check_cancelled(cancelled)
    if not (path.parent / "proceed").is_file():
        raise RuntimeError("A atualização não foi confirmada pelo aplicativo.")
    return stage_and_swap(Path(data["root"]), emit, cancelled)
