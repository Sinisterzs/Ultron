import unittest
from unittest.mock import patch
from core import search_sources as sources
from actions import web_search as web


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.context = patch('core.ip_geolocation.get_search_location', return_value={
            'country_code': 'BR', 'city': 'Cidade A', 'region': 'Estado A', 'country_name': 'Brazil', 'source': 'manual'})
        self.location = self.context.start()

    def tearDown(self):
        self.context.stop()

    def test_profiles_and_explicit_region(self):
        self.assertEqual(sources.source_plan('placa de vídeo RTX 3060')['domains'],
                         ('kabum.com.br', 'terabyteshop.com.br', 'amazon.com.br'))
        plan = sources.source_plan('apartamentos')
        self.assertIn('Cidade A', plan['region'])
        self.assertIn('quintoandar.com.br', plan['domains'])
        self.assertIsNone(sources.source_plan('latest world news'))
        self.assertIsNone(sources.source_plan('hardware mundial'))
        self.assertIsNone(sources.source_plan('hardware', country='global'))
        self.assertIsNone(sources.source_plan('noticias'))
        self.assertIsNone(sources.source_plan('historia de astronomia'))
        for query, country in [('apartamento em Portugal', ''), ('hardware', 'PT')]:
            self.location.reset_mock()
            self.assertIsNone(sources.source_plan(query, country)['domains'])
            self.location.assert_not_called()

    def test_explicit_site_no_location_lookup(self):
        plan = sources.source_plan('RTX site:lojaexemplo.com.br')
        self.assertEqual(plan['domains'], ('lojaexemplo.com.br',))
        self.location.assert_not_called()
        self.assertEqual(sources.source_plan('RTX na Amazon nos Estados Unidos')['domains'], ('amazon.com',))
        self.assertFalse(sources.is_preferred_url('https://kabum.com.br.evil.example/p', ('kabum.com.br',)))
        self.assertTrue(sources.is_preferred_url('https://www.kabum.com.br/produto/1', ('kabum.com.br',)))

    def test_concrete_filter_and_no_fallback(self):
        with patch.object(web, '_ddg_search', return_value=[
            {'title': 'GPU', 'snippet': 'price unverified', 'url': 'https://www.kabum.com.br/produto/1'},
            {'title': 'Aggregate', 'url': 'https://bestvaluegpu.com/'}]) as ddg:
            result = web._source_search('RTX 3060')
            self.assertIn('site:terabyteshop.com.br', ddg.call_args.args[0])
            self.assertIn('kabum.com.br/produto/1', result)
            self.assertNotIn('bestvaluegpu', result)
        with patch.object(web, '_ddg_search', return_value=[]) as ddg:
            result = web._source_search('RTX 3060')
            self.assertIn('No other sources substituted', result)
            self.assertEqual(ddg.call_count, 1)

    def test_unknown_country_generic_and_explicit_site_empty(self):
        with patch.object(web, '_ddg_search', return_value=[]) as ddg:
            self.assertIsNone(web._source_search('RTX', expand_sources=True))
            ddg.assert_not_called()
            self.assertIn('No known-source profile', web._source_search('apartamentos', 'PT'))
            self.assertIn('PT', ddg.call_args.args[0])
            self.assertIn('No other site substituted', web._source_search('RTX', site='example.org'))
            self.assertIn('No other site substituted', web._source_search('RTX site:example.org', expand_sources=True))

    def test_arbitrary_prose_not_used_as_source(self):
        with patch('core.offer_verifier.verify_offer_urls') as verify:
            output = web._append_offer_verification('RTX', '- Buy https://invented.example/p')
            verify.assert_not_called()
            self.assertIn('unverified', output)


if __name__ == '__main__':
    unittest.main()
