"""Regional preferences and settings card with synthetic configuration only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import ast
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtGui import QFontDatabase, QFont
from core import config_store, location_preferences as prefs, ip_geolocation as geo
from core.location_settings import LocationSettings
from actions.web_search import _regional_search_hint


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'config.json'
        self.context = patch.object(config_store, 'config_path', return_value=self.path)
        self.context.start()

    def tearDown(self):
        self.context.stop()
        self.temp.cleanup()

    def test_persist_precedence_currency_and_reset(self):
        config_store.save_config({'other': {'untouched': True}})
        prefs.confirm_location('Cidade exemplo', 'BR', 'Estado exemplo')
        self.assertEqual(prefs.get_override()['currency'], 'BRL')
        with patch.object(geo, 'get_approximate_location', return_value={'city': 'IP city'}) as ip:
            self.assertEqual(geo.get_search_location()['source'], 'manual')
            ip.assert_not_called()
            hint = _regional_search_hint('preço em Portugal', 'price')
            self.assertIn('confirmed preferred', hint)
            self.assertIn('honor any explicit region', hint)
            prefs.reset_location()
            self.assertEqual(geo.get_search_location()['source'], 'ip')
            ip.assert_called_once()
        self.assertTrue(config_store.load_config()['other']['untouched'])

    def test_validation_and_currency_derived_on_read(self):
        for city, country, region in [('', 'BR', ''), ('Town', 'ZZ', ''), ('x\n', 'BR', ''), ('x'*121, 'BR', '')]:
            with self.assertRaises(ValueError):
                prefs.confirm_location(city, country, region)
        self.assertFalse(self.path.exists())
        prefs.confirm_location('Lisboa', 'PT')
        self.assertEqual(prefs.get_override()['currency'], 'EUR')
        config_store.update_config({'search_location': {'city': 'New York', 'country_code': 'US', 'currency': 'BRL'}})
        self.assertEqual(prefs.get_override()['currency'], 'USD')

    def test_credential_preservation_uses_config_store(self):
        # Synthetic credential, mock only OS encryption; never reads personal configuration.
        with patch.object(config_store, '_dpapi', side_effect=lambda raw, **kw: raw[::-1]):
            config_store.save_config({'gemini_api_key': 'synthetic-fixture-secret', 'theme': 'red'})
            prefs.confirm_location('Example', 'BR')
            restored = config_store.load_config()
            self.assertEqual(restored['gemini_api_key'], 'synthetic-fixture-secret')
            self.assertEqual(restored['theme'], 'red')
            self.assertNotIn('synthetic-fixture-secret', self.path.read_text())


class LocationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/segoeui.ttf'
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
            cls.app.setFont(QFont('Segoe UI', 10))

    def wait(self, widget):
        for _ in range(100):
            self.app.processEvents()
            if widget.confirm.isEnabled():
                return
            QTest.qWait(10)
        self.fail('settings worker did not finish')

    def test_worker_confirm_reset_validation_and_preview(self):
        main_thread = threading.get_ident()
        calls = []
        ip = {'city': 'Cidade aproximada', 'region': 'Santa Catarina', 'country_code': 'BR',
              'country_name': 'Brazil', 'currency': 'BRL', 'source': 'ip'}
        def read():
            calls.append(threading.get_ident())
            return ip
        with patch('core.location_settings.get_search_location', side_effect=read), patch.object(
                prefs, 'confirm_location', return_value=prefs.validate_location('Cidade corrigida', 'BR', 'SC')) as save, patch.object(
                prefs, 'reset_location') as reset:
            card = LocationSettings()
            card.resize(620, 360)
            self.assertEqual(calls, [])
            card.show()
            self.wait(card)
            self.assertIn('aproximado', card.status.text())
            self.assertNotEqual(calls[0], main_thread)
            card.city.clear()
            card.confirm.click()
            save.assert_not_called()
            card.city.setText('Cidade corrigida')
            card.region.setText('SC')
            card.confirm.click()
            self.wait(card)
            save.assert_called_once_with('Cidade corrigida', 'BR', 'SC')
            self.assertIn('Manual confirmada', card.status.text())
            self.assertEqual(card.currency.text(), 'BRL')
            preview = os.environ.get('ULTRON_LOCATION_PREVIEW')
            if preview:
                self.assertTrue(card.grab().save(preview))
            card.automatic.click()
            self.wait(card)
            reset.assert_called_once()
            self.assertIn('aproximado', card.status.text())
            card.close()
            card.deleteLater()
            self.app.processEvents()

    def test_syntax(self):
        for name in ('ui.py', 'core/location_settings.py', 'core/location_preferences.py', 'core/ip_geolocation.py'):
            ast.parse(Path(name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
