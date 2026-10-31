import ast
import io
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from core import offer_verifier as offers, ip_geolocation as geo
from actions import web_search
from actions import browser_control

URL = 'https://shop.example/product/3060?x=1'


def page(products):
    return ('<script type="application/ld+json">' + json.dumps(products) + '</script>').encode()


def product(**changes):
    item = {'@type': 'Product', 'name': 'RTX 3060', 'url': URL,
            'offers': {'@type': 'Offer', 'price': '1500', 'priceCurrency': 'BRL',
                       'seller': {'name': 'Loja'}}}
    item.update(changes)
    return item


class OfferTests(unittest.TestCase):
    def test_compression_charset_and_bomb_limit(self):
        raw = 'preço'.encode('iso-8859-1')
        self.assertEqual(offers._decode_body(gzip.compress(raw), 'gzip',
                         'text/html; charset=iso-8859-1'), 'preço'.encode())
        with self.assertRaises(ValueError):
            offers._decode_body(gzip.compress(b'x' * (offers._MAX_DECODED_BYTES + 1)), 'gzip')

    def test_primary_offer_payment_and_recommendations(self):
        self.assertTrue(offers._relevant('RX 7600 PCYES', 'PCYES GPU AMD Radeon Rx 7600'))
        markup = '''<span id="productTitle">RX 7600 PCYES</span>
        <a id="sellerProfileTriggerId">Seller A</a>
        <div id="corePriceDisplay_desktop_feature_div"><span class="priceToPay">
        <span class="a-offscreen">R$ 2.279,05</span> no Pix</span></div>
        <p>Recomendação R$ 99,00 no Pix</p>'''
        evidence = offers._html_offer(markup, 'https://www.amazon.com.br/dp/ABC', [])
        self.assertEqual(evidence['price'], '2279.05')
        self.assertEqual(evidence['payment_condition'], 'not confirmed')
        self.assertEqual(evidence['seller'], 'Seller A')
        self.assertIsNone(offers._html_offer(markup.replace('sellerProfileTriggerId', 'shipper'),
                          'https://www.amazon.com.br/dp/ABC', []))

    def test_amazon_payment_siblings_and_wrong_asin(self):
        from bs4 import BeautifulSoup
        markup = '''<span id="productTitle">RX 7600 PCYES</span>
        <a id="sellerProfileTriggerId">Seller A</a>
        <div id="apex_desktop"><div id="corePrice_feature_div">
        <span class="a-offscreen">R$2.279,05</span></div>
        <div>5% off à vista no Pix ou NuPay</div>
        <div id="installmentCalculatorCentral_feature_div" data-csa-c-asin="ABC">
        até 12x de R$199,99 sem juros (total parcelado R$2.399,00)
        Ver opções de pagamento</div></div>
        <div>Recomendação: 2x de R$10,00 sem juros</div>'''
        evidence = offers._amazon_offer(BeautifulSoup(markup, 'html.parser'),
                                        'https://www.amazon.com.br/dp/ABC')
        self.assertEqual(evidence['cash_methods'], ['Pix', 'NuPay'])
        self.assertEqual(evidence['installments']['declared_total'], '2399.00')
        self.assertEqual(evidence['installments']['amount'], '199.99')
        other = offers._amazon_offer(BeautifulSoup(markup.replace('asin="ABC"', 'asin="OTHER"'), 'html.parser'),
                                    'https://www.amazon.com.br/dp/ABC')
        self.assertEqual(other['payment_condition'], 'not confirmed')
        self.assertNotIn('installments', other)

    def verify(self, products, query='RTX 3060'):
        with patch.object(offers, '_public_http_url', return_value=True), patch.object(
                offers, '_fetch', return_value=(URL, 'text/html', page(products))):
            return offers._verify_one(query, URL)

    def test_offer_and_wrong_model(self):
        self.assertEqual(self.verify(product())['status'], 'verified')
        self.assertEqual(self.verify(product(name='RTX 4060'))['status'], 'unverified')

    def test_ambiguous_and_missing_fields(self):
        self.assertEqual(self.verify([product(), product()])['status'], 'unverified')
        for offer in ({'price': '100', 'priceCurrency': 'BRL'},
                      {'price': '100', 'seller': {'name': 'Loja'}},
                      [{'price': '1'}, {'price': '2'}]):
            self.assertEqual(self.verify(product(offers=offer))['status'], 'unverified')

    def test_nonfinite_price(self):
        p = product(); p['offers']['price'] = 'nan'
        self.assertEqual(self.verify(p)['status'], 'unverified')

    def test_installments_do_not_invent_total(self):
        evidence = {}
        offers._installments(evidence, '10 x R$ 225,88 sem juros ou em até 36x no NuPay')
        self.assertEqual(evidence['installments']['count'], 10)
        self.assertEqual(evidence['installments']['amount'], '225.88')
        self.assertNotIn('declared_total', evidence['installments'])
        self.assertEqual(evidence['installments']['calculated_total'], '2258.80')

    def test_embedded_price_is_not_declared_total(self):
        from bs4 import BeautifulSoup
        evidence = {'seller': 'Loja', 'price': '1919.99'}
        offers._installments(evidence, '10x R$225,88 sem juros')
        record = {'id': 123, 'sellerName': 'Loja',
                  'prices': {'price': 2258.81, 'priceWithDiscount': 1919.99},
                  'installment': {'installment': 10, 'amount': 225.88}}
        soup = BeautifulSoup('<script id="__NEXT_DATA__">' + json.dumps(record) + '</script>', 'html.parser')
        offers._kabum_embedded_price(soup, 'https://www.kabum.com.br/produto/123/name', evidence)
        self.assertEqual(evidence['installments']['difference_from_regular_price'], '-0.01')
        self.assertNotIn('declared_total', evidence['installments'])
        other = {'seller': 'Other', 'price': '1919.99'}
        offers._installments(other, '10x R$225,88 sem juros')
        offers._kabum_embedded_price(soup, 'https://www.kabum.com.br/produto/123/name', other)
        self.assertNotIn('embedded_regular_price', other['installments'])

    def test_private_addresses_and_source_url(self):
        for url in ('http://127.0.0.1/', 'http://169.254.169.254/', 'http://192.168.1.1/'):
            self.assertFalse(offers._public_http_url(url))
        with patch.object(offers, '_verify_one', return_value={'status': 'unverified'}) as verify:
            offers.verify_offer_urls('x', [URL + ')'])
            verify.assert_called_once_with('x', URL + ')')

    def test_redirect_to_internal_is_blocked_before_connect(self):
        response = unittest.mock.Mock(status=302)
        response.getheader.return_value = 'http://127.0.0.1/private'
        with patch.object(offers.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch.object(
                offers.socket, 'create_connection') as connect, patch.object(
                offers.ssl, 'create_default_context') as tls, patch.object(
                offers.http.client, 'HTTPResponse', return_value=response):
            tls.return_value.wrap_socket.return_value = connect.return_value
            with self.assertRaises(ValueError):
                offers._fetch('https://shop.example/item')
            self.assertEqual(connect.call_count, 1)


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.old = geo._cached
        geo._cached = (0, None)

    def tearDown(self):
        geo._cached = self.old

    def test_cache_and_privacy(self):
        raw = json.dumps({'city': 'Recife', 'country_name': 'Brazil', 'ip': 'secret'}).encode()
        with patch.object(geo.time, 'monotonic', return_value=50000), patch.object(
                geo.urllib.request, 'urlopen', return_value=io.BytesIO(raw)) as fetch:
            self.assertEqual(geo.get_approximate_location()['city'], 'Recife')
            self.assertNotIn('ip', geo.get_approximate_location())
            self.assertEqual(fetch.call_count, 1)

    def test_failure(self):
        with patch.object(geo.time, 'monotonic', return_value=50000), patch.object(
                geo.urllib.request, 'urlopen', side_effect=OSError):
            self.assertIsNone(geo.get_approximate_location())


class RoutingTests(unittest.TestCase):
    def test_default_browser_even_with_active_session(self):
        with patch.object(browser_control._registry, 'has', return_value=True), patch.object(
                browser_control._registry, 'get') as session, patch.object(
                browser_control, '_open_native', return_value='unverified') as native:
            browser_control.browser_control({'action': 'go_to', 'url': URL})
            native.assert_called_once_with(URL, None)
            session.assert_not_called()

    def test_price_uses_returned_source(self):
        source = 'https://shop.example/item?x=1'
        with patch.object(web_search, '_source_search', return_value=None), patch.object(web_search, '_regional_search_hint', return_value=''), patch.object(
                web_search, '_gemini_search', return_value='result\n\nSources:\n- shop: ' + source), patch.object(
                offers, 'verify_offer_urls', return_value=[]) as verify:
            web_search._price('RTX 3060')
            verify.assert_called_once_with('RTX 3060', [source])

    def test_main_syntax_without_import(self):
        for name in ('main.py', 'actions/browser_control.py', 'actions/web_search.py',
                     'core/offer_verifier.py', 'core/ip_geolocation.py'):
            ast.parse(Path(name).read_text(encoding='utf-8'), filename=name)


if __name__ == '__main__':
    unittest.main()
