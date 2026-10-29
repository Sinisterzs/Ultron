from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from core import install_manager as install
from core import updates


class DownloadTests(unittest.TestCase):
    def test_bad_hash_never_commits_download(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "runtime.zip"
            response = MagicMock()
            response.__enter__.return_value = response
            response.geturl.return_value = "https://www.python.org/example"
            response.headers = {"Content-Length": "3"}
            response.read.side_effect = [b"bad", b""]
            with patch.object(install.urllib.request, "urlopen", return_value=response):
                with self.assertRaises(ValueError):
                    install.download_verified("https://www.python.org/example", "0" * 64, dest, lambda *a: None)
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_suffix(".zip.part").exists())

    def test_verified_cache_avoids_another_download(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "runtime.zip"; path.write_bytes(b"verified-cache")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(install.urllib.request, "urlopen") as network:
                self.assertEqual(install.download_verified("https://www.python.org/example", digest, path, lambda *a: None), path)
                network.assert_not_called()

    def test_runtime_zip_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escape.txt", "bad")
            with self.assertRaises(ValueError):
                install.extract_runtime(archive, Path(d) / "runtime")
            self.assertFalse((Path(d) / "escape.txt").exists())

    def test_cancel_stops_before_network(self):
        with self.assertRaises(install.InstallationCancelled):
            install.check_cancelled(lambda: True)


class ReleaseTests(unittest.TestCase):
    def test_numeric_versions_and_prereleases(self):
        self.assertGreater(updates.version_key("v1.10.0"), updates.version_key("1.9.9"))
        self.assertGreater(updates.version_key("1.0.0"), updates.version_key("1.0.0-preview.1"))
        self.assertGreater(updates.version_key("1.0.0-preview.10"), updates.version_key("1.0.0-preview.2"))
        with self.assertRaises(ValueError):
            updates.version_key("malicious release title")

    def test_unconfigured_repository_never_connects(self):
        with patch.object(updates.urllib.request, "urlopen") as network:
            self.assertIsNone(updates.check_release({"version": "1.0.0", "github_repository": ""}))
            network.assert_not_called()

    def test_release_url_is_derived_not_trusted_from_response(self):
        release = updates.parse_release({"tag_name": "v2.0.0", "html_url": "https://example.invalid"}, "owner/project", "1.0.0")
        self.assertEqual(release.url, "https://github.com/owner/project/releases/tag/v2.0.0")
        self.assertIsNone(updates.parse_release({"tag_name": "v2.0.0", "prerelease": True}, "owner/project", "1.0.0"))
        self.assertIsNone(updates.parse_release({"tag_name": "v1.0.0"}, "owner/project", "1.0.0"))

    def test_rate_limit_and_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "updates.json"
            response = MagicMock(); response.__enter__.return_value = response
            response.read.return_value = json.dumps({"tag_name": "v2.0.0"}).encode()
            config = {"version": "1.0.0", "github_repository": "owner/project", "check_interval_hours": 24}
            with patch.object(updates.urllib.request, "urlopen", return_value=response) as network:
                self.assertEqual(updates.check_release(config, state_path=state, now=100000).version, "2.0.0")
                self.assertIsNone(updates.check_release(config, state_path=state, now=100001))
                self.assertEqual(network.call_count, 1)
                self.assertNotIn("api_key", state.read_text())


class PayloadTests(unittest.TestCase):
    def test_allowlist_never_includes_personal_data_or_experiments(self):
        import runpy
        root = Path(__file__).resolve().parent.parent
        helper = runpy.run_path(str(root / "installer/prepare_payload.py"))
        manifest = helper["create_manifest"](root)
        names = set(manifest["files"])
        for excluded in ["config/api_keys.json", "memory/long_term.json", "config/.spotify_token_cache", ".env"]:
            self.assertNotIn(excluded, names)
        self.assertFalse(any(x.startswith(("prototypes/", "tests/", ".venv/", "logs/")) for x in names))
        self.assertIn("launcher.py", names)
        self.assertIn("ui_updates.py", names)


class InstallPlanTests(unittest.TestCase):
    def test_download_plan_targets_private_python_and_optional_browser(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); bundle = base / "payload"; app = bundle / "app"
            app.mkdir(parents=True)
            requirements = b"example-package==1.0\n"
            (app / "requirements.txt").write_bytes(requirements)
            (bundle / "manifest.json").write_text(json.dumps({"files": {
                "requirements.txt": hashlib.sha256(requirements).hexdigest()}}))
            spec = {"runtime_url": "https://www.python.org/runtime", "runtime_sha256": "0"*64,
                    "pip_url": "https://files.pythonhosted.org/pip", "pip_sha256": "1"*64,
                    "archive": "python313.zip"}
            (bundle / "runtime.json").write_text(json.dumps(spec))
            archive = base / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("python.exe", "test fixture, not executable")
            pip = base / "pip.whl"; pip.write_bytes(b"test fixture")
            target = base / "installed"
            with patch.object(install, "data_root", return_value=base / "data"), \
                    patch.object(install, "download_verified", side_effect=[archive, pip]), \
                    patch.object(install, "run_task") as run:
                result = install._install(lambda *args: None, bundle_root=bundle, target=target, browser=True)
            self.assertEqual(result, target)
            self.assertEqual(len(run.call_args_list), 4)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertTrue(all(command[0] == str(target / "runtime/python.exe") for command in commands))
            self.assertIn("setuptools>=70,<81", commands[0])
            self.assertIn("--only-binary=:all:", commands[0])
            self.assertIn("--no-build-isolation", commands[1])
            self.assertIn("https://pypi.org/simple", commands[1])
            self.assertEqual(commands[2][1:], ["-m", "playwright", "install", "chromium"])
            self.assertTrue((target / "app/requirements.txt").is_file())
            self.assertFalse((target / "config/api_keys.json").exists())

    def test_payload_corruption_prevents_network_or_installation(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); bundle = base / "payload"
            (bundle / "app").mkdir(parents=True)
            (bundle / "app/main.py").write_text("tampered")
            (bundle / "manifest.json").write_text(json.dumps({"files": {"main.py": "0"*64}}))
            (bundle / "runtime.json").write_text("{}")
            with patch.object(install, "download_verified") as network:
                with self.assertRaises(ValueError):
                    install._install(lambda *a: None, bundle_root=bundle, target=base / "target")
                network.assert_not_called()


class TaskDiagnosticsTests(unittest.TestCase):
    def test_build_backend_error_is_logged_and_not_blamed_on_connection(self):
        import sys
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "setup-install.log"
            script = "print(\"Cannot import 'setuptools.build_meta'\"); raise SystemExit(2)"
            with self.assertRaisesRegex(RuntimeError, "ferramentas de preparação"):
                install.run_task([sys.executable, "-c", script], lambda *a: None, log_path=log)
            self.assertIn("setuptools.build_meta", log.read_text(encoding="utf-8"))

    def test_log_redacts_credentials_from_failure_output(self):
        import sys
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "setup-install.log"
            line = "https://example-user:example-password@example.invalid password=example-secret Authorization: Bearer example-token"
            script = "print(" + repr(line) + "); raise SystemExit(1)"
            with self.assertRaises(RuntimeError):
                install.run_task([sys.executable, "-c", script], lambda *a: None, log_path=log)
            text = log.read_text(encoding="utf-8")
            for secret in ("example-password", "example-secret", "example-token"):
                self.assertNotIn(secret, text)
            self.assertIn("[REDACTED]", text)

    def test_pre_cancelled_task_does_not_start_a_process(self):
        with patch.object(install.subprocess, "Popen") as process:
            with self.assertRaises(install.InstallationCancelled):
                install.run_task(["unused"], lambda *a: None, cancel=lambda: True)
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
