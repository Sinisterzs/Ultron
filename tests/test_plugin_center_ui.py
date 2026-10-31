"""
tests/test_plugin_center_ui.py — Comprehensive tests for the Futuristic Plugin Control Center.

Verifies:
1. Offscreen instantiation and rendering.
2. SVG Icon Cache (load once, pre-render to QPixmap, cache by spec/size/color).
3. Pre-calculated holographic QPainterPath on resizeEvent only (zero path math in paintEvent).
4. Scalable plugin discovery without hardcoded mock modules ("Dev Agent" / "File Search" stay out).
5. Dynamic filtering and search without layout or widget thrashing.
6. Live permissions querying and instantaneous revocation for sensitive modules.
7. Zero continuous QTimer instances in the overlay.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Must configure temporary data dir BEFORE importing any modules that bind data_root()
_TEMP_DATA_DIR = tempfile.TemporaryDirectory()
os.environ["ULTRON_DATA_DIR"] = str(Path(_TEMP_DATA_DIR.name).resolve())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from memory.config_manager import (
    clear_vision_persistent_permissions,
    add_persistent_capture_scope,
    add_persistent_send_destination,
    get_plugin_enabled,
    get_vision_permissions,
    save_plugin_enabled,
)
from plugins._smart_vision_permissions import get_shared_permission_manager
from ui_plugins_center import (
    PluginCardWidget,
    PluginIconWidget,
    PluginManagerOverlay,
    ToggleSwitch,
    _ICON_CACHE,
    get_cached_plugin_icon,
)


class TestPluginCenterUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        try:
            _TEMP_DATA_DIR.cleanup()
        except Exception:
            pass

    def setUp(self):
        # Clear permission manager state and persistent vision permissions
        clear_vision_persistent_permissions()
        get_shared_permission_manager().revoke_all(clear_persistent=True)

    def tearDown(self):
        clear_vision_persistent_permissions()
        get_shared_permission_manager().revoke_all(clear_persistent=True)

    def test_svg_icon_caching(self):
        """Verify SVG icons are rendered once to QPixmap and cached by (spec, size, color)."""
        _ICON_CACHE.clear()

        # 1. Preset eye icon
        pm1 = get_cached_plugin_icon("eye", 40, "#ff2a4b")
        self.assertIsInstance(pm1, QPixmap)
        self.assertEqual(pm1.width(), 40)
        self.assertEqual(pm1.height(), 40)

        # Cache hit: exact same object reference
        pm2 = get_cached_plugin_icon("eye", 40, "#ff2a4b")
        self.assertIs(pm1, pm2)

        # Different size creates a separate cached QPixmap
        pm_large = get_cached_plugin_icon("eye", 64, "#ff2a4b")
        self.assertIsNot(pm1, pm_large)
        self.assertEqual(pm_large.width(), 64)

        # Different color creates a separate cached QPixmap
        pm_white = get_cached_plugin_icon("eye", 40, "#ffffff")
        self.assertIsNot(pm1, pm_white)

        # Spotify preset
        pm_spotify = get_cached_plugin_icon("spotify", 40, "#ff2a4b")
        self.assertIsInstance(pm_spotify, QPixmap)
        self.assertIs(pm_spotify, get_cached_plugin_icon("spotify", 40, "#ff2a4b"))

        # Generic preset
        pm_gen = get_cached_plugin_icon("nonexistent_unknown_plugin", 40, "#ff2a4b")
        self.assertIsInstance(pm_gen, QPixmap)

    def test_precalculated_holographic_paths(self):
        """Verify holographic chamfered borders are precomputed on resizeEvent and reused."""
        sample_plugins = [
            {
                "name": "sample_mod",
                "icon": "generic",
                "category": "UTILITY",
                "tags": ["SYSTEM"],
                "version": "v1.0",
                "description": "Sample utility module",
                "enabled": True,
            }
        ]

        overlay = PluginManagerOverlay(sample_plugins)
        overlay.show()
        overlay.resize(890, 580)

        # Frame path and bracket lines should be precalculated
        self.assertIsNotNone(overlay._cached_frame_path)
        self.assertFalse(overlay._cached_frame_path.isEmpty())
        self.assertEqual(len(overlay._cached_bracket_lines), 8)

        old_path = overlay._cached_frame_path

        # Simulating window resize triggers rebuild
        overlay.resize(920, 600)
        self.assertIsNotNone(overlay._cached_frame_path)
        self.assertIsNot(overlay._cached_frame_path, old_path)

        # Test paintEvent executes cleanly using pre-calculated paths offscreen
        target_pix = QPixmap(920, 600)
        target_pix.fill(Qt.GlobalColor.black)
        p = QPainter(target_pix)
        overlay.render(p)
        p.end()

        # Component widgets precalculation
        card = overlay._card_widgets["sample_mod"]
        self.assertIsNotNone(card._cached_card_path)
        self.assertIsNotNone(card._cached_indicator_rect)

        icon_w = card.icon_widget
        self.assertIsNotNone(icon_w._cached_bg_path)

        sw = card.switch
        self.assertIsNotNone(sw._cached_track_path)

    def test_scalable_dynamic_plugins_no_hardcoding(self):
        """Verify any arbitrary plugin with an icon dynamically renders, without Dev Agent or File Search."""
        dynamic_plugins = [
            {
                "name": "smart_vision",
                "icon": "eye",
                "category": "VISION",
                "tags": ["SENSITIVE"],
                "version": "v1.0",
                "description": "Screen perception and analysis",
                "enabled": False,
            },
            {
                "name": "spotify_control",
                "icon": "spotify",
                "category": "MEDIA",
                "version": "v1.0",
                "description": "Music and playback control",
                "enabled": True,
            },
            {
                "name": "custom_iot_hub",
                "icon": "generic",
                "category": "IOT",
                "tags": ["NETWORK", "HARDWARE"],
                "version": "v2.5",
                "description": "Smart home peripheral automation",
                "enabled": True,
            },
        ]

        overlay = PluginManagerOverlay(dynamic_plugins)

        # Dev Agent and File Search must not be present
        self.assertNotIn("dev_agent", overlay._card_widgets)
        self.assertNotIn("file_search", overlay._card_widgets)
        self.assertNotIn("Dev Agent", [c.title_lbl.text() for c in overlay._card_widgets.values()])
        self.assertNotIn("File Search", [c.title_lbl.text() for c in overlay._card_widgets.values()])

        # All 3 dynamic plugins are present
        self.assertEqual(len(overlay._card_widgets), 3)
        self.assertIn("smart_vision", overlay._card_widgets)
        self.assertIn("spotify_control", overlay._card_widgets)
        self.assertIn("custom_iot_hub", overlay._card_widgets)

        # Check titles & tags
        iot_card = overlay._card_widgets["custom_iot_hub"]
        self.assertEqual(iot_card.title_lbl.text(), "Custom Iot Hub")
        self.assertEqual(iot_card.cat_lbl.text(), "IOT • NETWORK • HARDWARE")
        self.assertEqual(overlay._count_lbl.text(), "03 PLUGINS")

    def test_filtering_and_search_no_widget_recreation(self):
        """Verify search and filters toggle visibility without recreating card widgets or thrashing layouts."""
        plugins = [
            {"name": "p_alpha", "icon": "generic", "category": "CORE", "tags": [], "description": "Alpha service", "enabled": True},
            {"name": "p_beta", "icon": "generic", "category": "MEDIA", "tags": [], "description": "Beta sound player", "enabled": False},
            {"name": "p_gamma", "icon": "generic", "category": "CORE", "tags": [], "description": "Gamma compute engine", "enabled": True},
        ]

        overlay = PluginManagerOverlay(plugins)

        # Store widget memory IDs
        id_alpha = id(overlay._card_widgets["p_alpha"])
        id_beta = id(overlay._card_widgets["p_beta"])
        id_gamma = id(overlay._card_widgets["p_gamma"])

        # 1. Filter ENABLED
        overlay._on_filter_clicked(1)  # ENABLED
        self.assertFalse(overlay._card_widgets["p_alpha"].isHidden())
        self.assertTrue(overlay._card_widgets["p_beta"].isHidden())
        self.assertFalse(overlay._card_widgets["p_gamma"].isHidden())
        self.assertEqual(overlay._count_lbl.text(), "02 PLUGINS")

        # 2. Filter DISABLED
        overlay._on_filter_clicked(2)  # DISABLED
        self.assertTrue(overlay._card_widgets["p_alpha"].isHidden())
        self.assertFalse(overlay._card_widgets["p_beta"].isHidden())
        self.assertTrue(overlay._card_widgets["p_gamma"].isHidden())
        self.assertEqual(overlay._count_lbl.text(), "01 PLUGINS")

        # 3. Search query
        overlay._on_filter_clicked(0)  # ALL
        overlay._on_search_changed("sound player")
        self.assertTrue(overlay._card_widgets["p_alpha"].isHidden())
        self.assertFalse(overlay._card_widgets["p_beta"].isHidden())
        self.assertTrue(overlay._card_widgets["p_gamma"].isHidden())
        self.assertEqual(overlay._count_lbl.text(), "01 PLUGINS")

        # Widget instances remain strictly identical (zero recreation)
        self.assertEqual(id(overlay._card_widgets["p_alpha"]), id_alpha)
        self.assertEqual(id(overlay._card_widgets["p_beta"]), id_beta)
        self.assertEqual(id(overlay._card_widgets["p_gamma"]), id_gamma)

    def test_toggle_switch_persistence(self):
        """Verify toggle switch updates config atomically and syncs UI state."""
        plugins = [
            {"name": "test_toggle_mod", "icon": "generic", "category": "TEST", "description": "Toggle test", "enabled": False}
        ]
        overlay = PluginManagerOverlay(plugins)
        card = overlay._card_widgets["test_toggle_mod"]

        self.assertFalse(card.switch.isChecked())
        self.assertFalse(get_plugin_enabled("test_toggle_mod", default=False))

        # Toggle ON
        overlay._on_card_toggled("test_toggle_mod", True)
        self.assertTrue(card.switch.isChecked())
        self.assertTrue(get_plugin_enabled("test_toggle_mod", default=False))

        # Toggle OFF
        overlay._on_card_toggled("test_toggle_mod", False)
        self.assertFalse(card.switch.isChecked())
        self.assertFalse(get_plugin_enabled("test_toggle_mod", default=False))

    def test_live_permissions_querying_and_instant_revocation(self):
        """Verify permission inspector queries live storage and revocation works immediately."""
        plugins = [
            {
                "name": "smart_vision",
                "icon": "eye",
                "category": "VISION",
                "tags": ["SENSITIVE"],
                "version": "v1.0",
                "description": "Screen analysis",
                "enabled": True,
            }
        ]
        overlay = PluginManagerOverlay(plugins)
        overlay.show()
        det = overlay._details_widget

        # Select smart vision
        overlay._on_card_selected(plugins[0])
        self.assertTrue(det._perm_container.isVisible())
        self.assertFalse(det._generic_container.isVisible())

        # Initially no permissions
        self.assertIn("ASK EVERY TIME", det._pill_cap.text())
        self.assertIn("ASK EVERY TIME", det._pill_send.text())

        # Grant persistent permissions
        add_persistent_capture_scope("screen:screen")
        add_persistent_send_destination("gemini-2.5-flash")
        det.refresh_permissions()

        self.assertIn("ALWAYS ALLOW", det._pill_cap.text())
        self.assertIn("ALWAYS ALLOW", det._pill_send.text())

        # Revoke access immediately
        det._btn_revoke.click()

        # Both should immediately revert to ASK EVERY TIME
        self.assertIn("ASK EVERY TIME", det._pill_cap.text())
        self.assertIn("ASK EVERY TIME", det._pill_send.text())

        # Confirm persistent config was cleared in memory and store
        perms = get_vision_permissions()
        self.assertEqual(len(perms.get("capture_scopes", [])), 0)
        self.assertEqual(len(perms.get("send_destinations", [])), 0)

        # Confirm session memory was also revoked
        pm = get_shared_permission_manager()
        self.assertFalse(pm.has_capture_permission("screen", "screen"))
        self.assertFalse(pm.has_send_permission("gemini-2.5-flash"))

    def test_settings_button_and_signals(self):
        """Verify module details shows settings button when settings are present and emits signal."""
        plugins = [
            {
                "name": "spotify_control",
                "icon": "spotify",
                "category": "MEDIA",
                "description": "Music player",
                "enabled": True,
                "settings": {"namespace": "spotify", "fields": []},
            },
            {
                "name": "simple_plugin",
                "icon": "generic",
                "category": "UTILITY",
                "description": "Simple utility",
                "enabled": True,
            },
        ]
        overlay = PluginManagerOverlay(plugins)
        overlay.show()
        det = overlay._details_widget

        # Select spotify_control (has settings)
        overlay._on_card_selected(plugins[0])
        self.assertTrue(det._btn_settings.isVisible())

        emitted_settings = []
        overlay.open_settings.connect(lambda name: emitted_settings.append(name))
        det._btn_settings.click()
        self.assertEqual(emitted_settings, ["spotify_control"])

        # Select simple_plugin (no settings)
        overlay._on_card_selected(plugins[1])
        self.assertFalse(det._btn_settings.isVisible())

    def test_closed_signal_emission(self):
        """Verify closing or hiding the overlay emits closed signal for navbar sync."""
        plugins = [{"name": "p1", "icon": "generic", "description": "Mod", "enabled": True}]
        overlay = PluginManagerOverlay(plugins)
        overlay.show()

        closed_emitted = [False]
        overlay.closed.connect(lambda: closed_emitted.__setitem__(0, True))

        overlay.hide()
        self.assertTrue(closed_emitted[0])

    def test_zero_continuous_timers(self):
        """Verify the overlay operates entirely event-driven without background polling timers."""
        plugins = [
            {"name": "p1", "icon": "eye", "category": "VISION", "description": "Mod 1", "enabled": True},
            {"name": "p2", "icon": "spotify", "category": "MEDIA", "description": "Mod 2", "enabled": False},
        ]
        overlay = PluginManagerOverlay(plugins)

        # Find all QTimer children
        timers = overlay.findChildren(QTimer)
        active_timers = [t for t in timers if t.isActive()]
        self.assertEqual(len(active_timers), 0, f"Found active continuous timers in overlay: {active_timers}")


if __name__ == "__main__":
    unittest.main()
