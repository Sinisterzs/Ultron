"""Installation regressions without microphones, API calls or real credentials."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import app_paths, config_store


class PathsTests(unittest.TestCase):
    def test_import_and_lookup_do_not_create_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "not-created"
            with patch.dict(os.environ, {"ULTRON_DATA_DIR": str(root)}):
                self.assertEqual(app_paths.config_path(), root / "config/api_keys.json")
                self.assertEqual(config_store.load_config(), {})
                self.assertFalse(root.exists())

    def test_relative_override_rejected(self):
        with patch.dict(os.environ, {"ULTRON_DATA_DIR": "relative-folder"}):
            with self.assertRaises(ValueError):
                app_paths.data_root()

    def test_frozen_child_reenters_app_without_external_python(self):
        with patch.object(app_paths.sys, "frozen", True, create=True), \
                patch.object(app_paths.sys, "executable", r"C:\ULTRON\ULTRON.exe"):
            self.assertEqual(app_paths.child_command(), [r"C:\ULTRON\ULTRON.exe", "--app"])

    def test_source_child_uses_main_in_other_process(self):
        with patch.object(app_paths.sys, "frozen", False, create=True):
            command = app_paths.child_command()
            self.assertEqual(Path(command[1]).name, "main.py")
            self.assertTrue(Path(command[1]).is_file())


@unittest.skipUnless(os.name == "nt", "Windows DPAPI integration")
class ProtectedSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config/api_keys.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_nested_credentials_round_trip_without_plaintext(self):
        data = {"gemini_api_key": "not-a-real-key-testing", "user_name": "Test",
                "providers": {"creds": {"llm": {"api_key": "test-provider-key"}}},
                "plugin_config": {"spotify": {"client_id": "public-id", "oauth_cache": {
                    "access_token": "test-access-token", "refresh_token": "test-refresh-token"}}}}
        config_store.save_config(data, self.path)
        self.assertEqual(config_store.load_config(self.path), data)
        text = self.path.read_text(encoding="utf-8")
        for secret in ["not-a-real-key-testing", "test-provider-key", "test-access-token", "test-refresh-token"]:
            self.assertNotIn(secret, text)
        self.assertIn("public-id", text)

    def test_settings_update_preserves_existing_secrets_and_unknown_fields(self):
        config_store.save_config({"gemini_api_key": "test-existing-secret", "future_setting": {"x": 1}}, self.path)
        config_store.update_config({"voice_name": "Kore"}, self.path)
        self.assertEqual(config_store.load_config(self.path), {
            "gemini_api_key": "test-existing-secret", "future_setting": {"x": 1}, "voice_name": "Kore"})

    def test_protection_failure_leaves_old_file_unchanged(self):
        config_store.save_config({"gemini_api_key": "test-old-secret"}, self.path)
        before = self.path.read_bytes()
        with patch.object(config_store, "_protect", side_effect=OSError("simulated protection failure")):
            with self.assertRaises(OSError):
                config_store.save_config({"gemini_api_key": "test-new-secret"}, self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_undecryptable_file_cannot_be_silently_replaced(self):
        config_store.save_config({"gemini_api_key": "test-only-key"}, self.path)
        before = self.path.read_bytes()
        with patch.object(config_store, "_unprotect", side_effect=OSError("simulated unlock failure")):
            with self.assertRaises(OSError):
                config_store.save_config({"user_name": "Replacement"}, self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_invalid_json_is_not_overwritten(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            config_store.save_config({"user_name": "Test"}, self.path)
        self.assertEqual(self.path.read_text(), "{broken")

    def test_existing_configuration_helpers_preserve_protected_fields(self):
        from memory import config_manager
        with patch.object(config_manager, "CONFIG_FILE", self.path), \
                patch.object(config_manager, "CONFIG_DIR", self.path.parent):
            config_manager.save_api_keys("test-configuration-key")
            config_manager.save_plugin_config("spotify", {"client_secret": "test-spotify-secret"})
            config_manager.save_voice("Kore")
            self.assertEqual(config_manager.get_gemini_key(), "test-configuration-key")
            self.assertEqual(config_manager.get_plugin_setting("spotify", "client_secret"), "test-spotify-secret")
            self.assertNotIn("test-spotify-secret", self.path.read_text())


class SpotifyTests(unittest.TestCase):
    def test_pkce_auth_and_protected_cache_without_network(self):
        try:
            import spotipy
        except ImportError:
            self.skipTest("Spotipy not installed in this test environment")
        from plugins import spotify_control as plugin
        values = {"client_id": "test-client", "client_secret": "", "redirect_uri": "http://127.0.0.1:8888/callback"}
        with patch.object(plugin, "_sp_client", None), \
                patch.object(plugin, "get_plugin_setting", side_effect=lambda ns, key, default=None: values.get(key, default)), \
                patch.object(plugin, "SpotifyPKCE") as pkce, \
                patch.object(plugin, "SpotifyOAuth") as legacy, \
                patch.object(spotipy, "Spotify"):
            plugin._get_client()
            pkce.assert_called_once()
            legacy.assert_not_called()
            cache = pkce.call_args.kwargs["cache_handler"]
            from spotipy.cache_handler import CacheHandler
            self.assertIsInstance(cache, CacheHandler)
            with patch.object(plugin, "save_plugin_config") as save:
                cache.save_token_to_cache({"access_token": "test-token"})
                save.assert_called_once_with("spotify", {"oauth_cache": {"access_token": "test-token"}})


class WizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        try:
            from PyQt6.QtWidgets import QApplication
            from ui_setup import SetupOverlay
        except ImportError:
            raise unittest.SkipTest("PyQt6 not installed in this test environment")
        cls.app = QApplication.instance() or QApplication([])
        cls.widget_class = SetupOverlay

    def test_navigation_requires_key_and_only_emits_on_final_confirmation(self):
        window = self.widget_class()
        captured = []
        window.done.connect(lambda key, os_name: captured.append((key, os_name)))
        with patch.object(config_store, "save_config") as save:
            window._advance()  # Welcome -> Gemini.
            window._advance()  # Missing key must remain on Gemini.
            self.assertEqual(window._index, 1)
            self.assertFalse(captured)
            window._key_input.setText("synthetic-key-for-test-only")
            window._advance()
            window._advance()
            self.assertEqual(window._index, 3)
            self.assertFalse(captured)
            window._prepared = True  # Preparation worker is covered independently.
            window._advance()
            self.assertEqual(len(captured), 1)
            self.assertEqual(window.settings["onboarding_version"], 1)
            self.assertNotIn("plugin_config", window.settings)
            save.assert_not_called()  # Parent is responsible for the single commit.
        window.close()

    def test_preparation_failure_never_submits_credentials(self):
        def fail(emit, cancel):
            emit("Etapa de teste", 0, 0)
            raise RuntimeError("Falha simulada")
        window = self.widget_class(preparer=fail)
        captured = []
        window.done.connect(lambda *args: captured.append(args))
        window._index = 3
        window._key_input.setText("synthetic-key-for-test-only")
        window._advance()
        from PyQt6.QtTest import QTest
        for _ in range(100):
            QTest.qWait(10)
            if not window._preparing:
                break
        window._worker.wait(2000)
        self.assertFalse(captured)
        self.assertFalse(window._prepared)
        self.assertTrue(window.next.isEnabled())
        self.assertIn("Falha simulada", window.error.text())
        window.close()

    def test_update_toast_is_dismissible_and_does_not_take_focus(self):
        from ui_updates import UpdateToast
        from core.updates import Release
        from PyQt6.QtCore import Qt
        toast = UpdateToast(Release("1.2.3", "https://github.com/example/project/releases/tag/v1.2.3"))
        self.assertEqual(toast.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertTrue(toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        toast.show(); toast.hide()
        self.assertFalse(toast.isVisible())
        toast.close()


if __name__ == "__main__":
    unittest.main()
