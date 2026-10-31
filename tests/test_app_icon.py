"""Icon asset and lookup regressions without launching the application."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PyQt6.QtWidgets import QApplication
from core import app_icon


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]

    def test_windows_asset_is_real_multisize_ico(self):
        path = self.root / "config/jarvis.ico"
        self.assertEqual(path.read_bytes()[:4], b"\x00\x00\x01\x00")
        with Image.open(path) as image:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)} <= image.ico.sizes())
        with Image.open(self.root / "config/jarvis.png") as image:
            self.assertEqual(image.format, "PNG")

    def test_source_and_bootstrap_payload_set_the_application_icon(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in ("config/jarvis.ico", "payload/app/config/jarvis.ico"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((self.root / "config/jarvis.ico").read_bytes())
                with patch.object(app_icon, "resource_root", return_value=root):
                    self.assertTrue(app_icon.apply_app_icon(self.app))
                    self.assertFalse(self.app.windowIcon().isNull())
                path.unlink()


if __name__ == "__main__":
    unittest.main()
