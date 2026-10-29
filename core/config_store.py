"""Atomic settings with protected credential values. No plaintext fallback.

Windows uses per-user DPAPI. Other platforms use an explicitly selected native
keyring backend. The JSON is created only on an explicit save, never on import.
"""
from __future__ import annotations

import base64
import copy
import ctypes
import json
import os
import tempfile
import threading
from pathlib import Path

from core.app_paths import config_path

_LOCK = threading.RLock()
_MARKER = "__ultron_credential__"
_META = "__ultron_protected__"
_SENSITIVE = {"api_key", "gemini_api_key", "client_secret", "password", "remote_key",
              "access_token", "refresh_token", "token", "oauth_cache"}


def _is_secret(key: str) -> bool:
    key = key.lower()
    return key in _SENSITIVE or key.endswith(("_api_key", "_secret", "_password", "_token"))


def _dpapi(payload: bytes, *, decrypt: bool = False) -> bytes:
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    source, target = Blob(len(payload), buffer), Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("Windows could not protect or unlock ULTRON credentials")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


def _native_keyring():
    import sys
    if sys.platform == "darwin":
        from keyring.backends.macOS import Keyring
    else:
        from keyring.backends.SecretService import Keyring
    return Keyring()


def _protect(values: dict, path: Path) -> dict:
    raw = json.dumps(values, ensure_ascii=False).encode("utf-8")
    if os.name == "nt":
        return {"backend": "dpapi-user", "value": base64.b64encode(_dpapi(raw)).decode("ascii")}
    # Versioned immutable records keep a failed JSON write from damaging old data.
    import uuid
    account = str(uuid.uuid4())
    _native_keyring().set_password("ULTRON", account, raw.decode("utf-8"))
    return {"backend": "native-keyring", "account": account}


def _unprotect(record: dict) -> dict:
    if record.get("backend") == "dpapi-user" and os.name == "nt":
        raw = _dpapi(base64.b64decode(record["value"], validate=True), decrypt=True)
    elif record.get("backend") == "native-keyring" and os.name != "nt":
        raw = _native_keyring().get_password("ULTRON", record["account"])
        if raw is None:
            raise OSError("ULTRON credentials are missing from the system keyring")
    else:
        raise OSError("These credentials belong to another operating system/user")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Invalid protected credentials")
    return result


def load_config(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else config_path()
    with _LOCK:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("ULTRON configuration must be a JSON object")
        record = data.pop(_META, None)
        secrets = _unprotect(record) if record else {}

        def restore(value):
            if isinstance(value, dict):
                if set(value) == {_MARKER}:
                    return copy.deepcopy(secrets[value[_MARKER]])
                return {k: restore(v) for k, v in value.items()}
            if isinstance(value, list):
                return [restore(v) for v in value]
            return value

        return restore(data)


def save_config(data: dict, path: Path | None = None) -> None:
    path = Path(path) if path is not None else config_path()
    if not isinstance(data, dict) or _META in data:
        raise ValueError("Invalid ULTRON configuration")
    with _LOCK:
        # A failed decryption must never silently replace existing credentials.
        if path.exists():
            load_config(path)
        secrets = {}

        def split(value):
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    if key == _MARKER:
                        raise ValueError("Reserved configuration field")
                    if _is_secret(key) and item is not None and item != "":
                        ref = str(len(secrets))
                        secrets[ref] = copy.deepcopy(item)
                        result[key] = {_MARKER: ref}
                    else:
                        result[key] = split(item)
                return result
            if isinstance(value, list):
                return [split(v) for v in value]
            return value

        public = split(data)
        if secrets:
            public[_META] = _protect(secrets, path)
        payload = json.dumps(public, indent=2, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".ultron-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def update_config(values: dict, path: Path | None = None) -> dict:
    with _LOCK:
        current = load_config(path)
        current.update(values)
        save_config(current, path)
        return current
