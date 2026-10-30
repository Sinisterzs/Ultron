"""Public release metadata only. No downloads, installs, tokens or modal prompts."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.app_paths import resource_root, data_root


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    installer_url: str = ""
    sha256: str = ""


def version_key(text):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", text)
    if not match:
        raise ValueError("Invalid release version")
    major, minor, patch, pre = match.groups()
    identifiers = tuple((0, int(x)) if x.isdigit() else (1, x) for x in pre.split(".")) if pre else ()
    return int(major), int(minor), int(patch), int(pre is None), identifiers


def read_release_config(path=None):
    path = Path(path) if path else resource_root() / "release_config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def parse_release(payload, repository, current):
    if payload.get("draft") or payload.get("prerelease"):
        return None
    tag = str(payload.get("tag_name", ""))
    if version_key(tag) <= version_key(current):
        return None
    # Derive the URL instead of trusting arbitrary release HTML supplied by metadata.
    from urllib.parse import quote
    page = f"https://github.com/{repository}/releases/tag/{quote(tag, safe='')}"
    expected = f"https://github.com/{repository}/releases/download/{quote(tag, safe='')}/ULTRON-Setup.exe"
    for asset in payload.get("assets", []):
        digest = str(asset.get("digest", ""))
        if (asset.get("name") == "ULTRON-Setup.exe" and
                asset.get("browser_download_url") == expected and
                re.fullmatch(r"sha256:[0-9a-f]{64}", digest) and
                0 < int(asset.get("size", 0)) <= 150 * 1024 * 1024):
            return Release(tag.removeprefix("v"), page, expected, digest[7:])
    return Release(tag.removeprefix("v"), page)


def check_release(config=None, *, state_path=None, now=None):
    config = config if config is not None else read_release_config()
    repo = config.get("github_repository", "")
    if not repo:
        return None  # Unconfigured builds do not phone home to the upstream repository.
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Expected a GitHub owner/repository")
    current = str(config["version"])
    version_key(current)
    path = Path(state_path) if state_path else data_root() / "updates/check.json"
    moment = time.time() if now is None else now
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    interval = max(300, float(config.get("check_interval_minutes", 5)) * 60)
    if moment - state.get("checked_at", 0) < interval and state.get("repository") == repo and state.get("version") == current:
        return None
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={
        "User-Agent": "ULTRON-UpdateCheck", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=6) as response:
        raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ValueError("Release metadata exceeds allowed size")
        payload = json.loads(raw)
    release = parse_release(payload, repo, current)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Only public timing metadata is saved. No installed version is changed here.
    from core.config_store import save_config
    save_config({"checked_at": moment, "repository": repo, "version": current}, path)
    return release
