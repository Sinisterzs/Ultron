"""Conservative HTTP/HTML verification for a small number of product offers."""
from __future__ import annotations

import html
import gzip
import io
import http.client
import ipaddress
import json
import math
from decimal import Decimal, InvalidOperation
import re
import socket
import ssl
import urllib.parse
from html.parser import HTMLParser

_MAX_URLS = 4
_MAX_BYTES = 750_000
_MAX_DECODED_BYTES = 3_000_000
_TIMEOUT = 5
_USER_AGENT = "ULTRON offer verifier/1"


def _decode_body(body, encoding='', content_type=''):
    if len(body) > _MAX_BYTES:
        raise ValueError('compressed body exceeds limit')
    if encoding.lower() == 'gzip' or body[:2] == b'\x1f\x8b':
        body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(_MAX_DECODED_BYTES + 1)
    elif encoding and encoding.lower() != 'identity':
        raise ValueError('unsupported content encoding')
    if len(body) > _MAX_DECODED_BYTES:
        raise ValueError('decoded body exceeds limit')
    charset = re.search(r'charset=[\"\x27]?([\w-]+)', content_type, re.I)
    if not charset:
        charset = re.search(r'charset=[\"\x27]?([\w-]+)', body[:4096].decode('ascii', 'ignore'), re.I)
    return body.decode(charset.group(1) if charset else 'utf-8', errors='strict').encode('utf-8')


def _html_offer(text, url, products):
    """Read only recognized primary-offer fields; no page-wide price guessing."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, 'html.parser')
    host = urllib.parse.urlparse(url).hostname
    if host == 'www.amazon.com.br':
        return _amazon_offer(soup, url)
    if host == 'www.kabum.com.br':
        return _kabum_offer(soup, url, products)
    return None


def _amazon_offer(soup, url):
    product = None
    if '/dp/' in url:
        title = soup.select_one('#productTitle')
        sellers = {n.get_text(' ', strip=True) for n in soup.select('#sellerProfileTriggerId')}
        prices = soup.select('#corePrice_feature_div .a-offscreen, #corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen')
        values = {p.get_text(' ', strip=True) for p in prices if p.get_text(strip=True)}
        if title and len(sellers) == 1 and len(values) == 1:
            amount = next(iter(values))
            product = {'name': title.get_text(' ', strip=True), 'url': url,
                       'offers': {'price': _brl_amount(amount), 'priceCurrency': 'BRL',
                                  'seller': {'name': next(iter(sellers))}}}
    evidence = _offer(product, {}) if product else None
    if not evidence:
        return None
    evidence['payment_condition'] = 'not confirmed'
    # Payment text belongs to the principal offer; installment widget must
    # identify this ASIN. Do not consume recommendation or generic help text.
    asin = url.split('/dp/', 1)[-1].split('/')[0].split('?')[0]
    principal = soup.select_one('#apex_desktop')
    calculator = principal.select_one('#installmentCalculatorCentral_feature_div') if principal else None
    if calculator and calculator.get('data-csa-c-asin') == asin:
        principal_text = principal.get_text(' ', strip=True)
        method = re.search(r'\b\d+%\s*off\s+à vista\s+no Pix ou NuPay', principal_text, re.I)
        if method:
            evidence['payment_condition'] = method.group(0)
            evidence['cash_price'] = evidence['price']
            evidence['cash_methods'] = ['Pix', 'NuPay']
        _installments(evidence, calculator.get_text(' ', strip=True).split('Ver opções de pagamento')[0])
    evidence['evidence_source'] = 'Amazon primary offer HTML'
    return evidence


def _installments(evidence, text):
    match = re.search(r'(\d+)\s*x\s*(?:de\s*)?R\$\s*([\d.]+,\d{2})\s*(sem juros|com juros)', text, re.I)
    if match:
        evidence['installments'] = {'count': int(match.group(1)),
                                    'amount': _brl_amount(match.group(2)),
                                    'interest': match.group(3).lower()}
        installment = evidence['installments']
        installment['calculated_total'] = format(Decimal(installment['amount']) * installment['count'], '.2f')
        installment['calculation_note'] = 'sum of displayed installments; rounding and checkout may differ'
        total = re.search(r'total parcelado\s*R\$\s*([\d.]+,\d{2})', text, re.I)
        if total:
            evidence['installments']['declared_total'] = _brl_amount(total.group(1))


def _kabum_offer(soup, url, products):
    product = None
    if '/produto/' in url and len(products) == 1:
        labels = soup.find_all(string=re.compile(r'^Vendido e entregue por:$'))
        names = {node.parent.parent.get_text(' ', strip=True).split(':', 1)[-1].strip()
                 for node in labels}
        if len(names) == 1 and isinstance(products[0].get('offers'), dict):
            product = dict(products[0])
            product['offers'] = dict(product['offers'])
            product['offers']['seller'] = {'name': next(iter(names))}
    if not product:
        return None
    evidence = _offer(product, {})
    if not evidence:
        return None
    evidence['payment_condition'] = 'not confirmed'
    # Payment labels must share a small price container with this exact amount.
    for node in soup.select('p, .priceToPay'):
        snippet = node.get_text(' ', strip=True)
        amounts = re.findall(r'R\$\s*([\d.]+,\d{2})', snippet)
        if len(snippet) < 250 and len(amounts) == 1 and _brl_amount(amounts[0]) == str(evidence['price']):
            if re.search(r'PIX|NuPay|vista|juros', snippet, re.I):
                evidence['payment_condition'] = snippet
                evidence['cash_price'] = evidence['price']
                evidence['cash_methods'] = ['Pix'] if re.search('PIX', snippet, re.I) else []
                # Only inspect the adjacent payment block of this price.
                container_text = node.parent.parent.get_text(' ', strip=True)
                _installments(evidence, container_text.replace('s/ juros', 'sem juros'))
                break
    _kabum_embedded_price(soup, url, evidence)
    evidence['evidence_source'] = 'primary offer HTML with product data'
    return evidence


def _kabum_embedded_price(soup, url, evidence):
    node = soup.select_one('#__NEXT_DATA__')
    if not node or 'installments' not in evidence:
        return
    try:
        data = json.loads(node.get_text(), parse_float=Decimal)
        product_id = url.split('/produto/', 1)[1].split('/')[0]
        records = [item for item in _walk(data) if str(item.get('id')) == product_id
                   and item.get('sellerName') == evidence['seller'] and isinstance(item.get('prices'), dict)]
        if len(records) != 1:
            return
        record = records[0]
        terms = record.get('installment', {})
        installment = evidence['installments']
        if (terms.get('installment') != installment['count'] or
                Decimal(str(terms.get('amount'))) != Decimal(installment['amount']) or
                Decimal(str(record['prices'].get('priceWithDiscount'))) != Decimal(evidence['price'])):
            return
        regular = Decimal(str(record['prices']['price']))
        if not regular.is_finite() or regular <= 0:
            return
        installment['embedded_regular_price'] = format(regular, '.2f')
        installment['regular_price_source'] = '__NEXT_DATA__: matching product id, seller, cash price and installments; prices.price'
        installment['difference_from_regular_price'] = format(Decimal(installment['calculated_total']) - regular, '.2f')
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return


def _brl_amount(text):
    value = re.search(r'([\d.]+,\d{2})', text)
    return value.group(1).replace('.', '').replace(',', '.') if value else ''


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.jsonld: list[str] = []
        self.meta: dict[str, str] = {}
        self._script_type = ""
        self._script_data: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "script" and "ld+json" in attrs.get("type", "").lower():
            self._script_type = "ld+json"
            self._script_data = []
        if tag.lower() == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key and attrs.get("content"):
                self.meta[key.lower()] = attrs["content"].strip()

    def handle_data(self, data):
        if self._script_type:
            self._script_data.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._script_type:
            self.jsonld.append("".join(self._script_data))
            self._script_type = ""
            self._script_data = []


def _public_http_url(url: str):
    try:
        parsed = urllib.parse.urlparse(str(url).strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in (80, 443):
            return False
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            addresses = [ipaddress.ip_address(item[4][0])
                         for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        public = next((address for address in addresses if not (
            address.is_private or address.is_loopback or address.is_link_local or
            address.is_reserved or address.is_multicast or address.is_unspecified)), None)
        return (parsed, public) if public else False
    except Exception:
        return False


def _walk(value):
    if isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)


def _products(documents):
    products = []
    for document in documents:
        for item in _walk(document):
            kind = item.get("@type", "")
            types = kind if isinstance(kind, list) else [kind]
            if any(str(value).lower() == "product" for value in types):
                products.append(item)
    return products


def _offer(product: dict, meta: dict[str, str]):
    offers = product.get("offers")
    if isinstance(offers, list):
        if len(offers) != 1:
            return None
        offers = offers[0]
    if not isinstance(offers, dict):
        offers = {}
    price = offers.get("price")
    currency = offers.get("priceCurrency")
    if price is None:
        price = meta.get("product:price:amount")
    if not currency:
        currency = meta.get("product:price:currency")
    # Do not interpret aggregate lowPrice/highPrice as the product's offer.
    try:
        numeric_price = float(str(price).replace(",", ".").strip())
    except ValueError:
        return None
    if not math.isfinite(numeric_price) or numeric_price <= 0 or not currency:
        return None
    seller = ((offers.get("seller") or {}).get("name", "")
              if isinstance(offers.get("seller"), dict) else offers.get("seller", ""))
    if not str(seller).strip():
        return None
    return {
        "product": str(product.get("name") or meta.get("og:title") or "").strip(),
        "seller": str(seller).strip(),
        "price": str(price).strip(),
        "currency": str(currency or "").strip(),
        "availability": str(offers.get("availability") or "").strip(),
    }


def _relevant(query: str, product: str) -> bool:
    wanted = {token for token in re.findall(r"[\wÀ-ÿ]{2,}", query.lower())
              if token not in {"preço", "price", "quanto", "custa", "hoje", "current"}}
    found = set(re.findall(r"[\wÀ-ÿ]{2,}", product.lower()))
    numeric = {token for token in wanted if any(char.isdigit() for char in token)}
    if numeric and not numeric <= found:
        return False
    return bool(wanted) and len(wanted & found) / len(wanted) >= 0.75


def _fetch(url: str):
    """Fetch directly to one validated IP, avoiding proxies and DNS rebinding."""
    current = url
    for _ in range(4):
        checked = _public_http_url(current)
        if not checked:
            raise ValueError("URL or redirect is not a public HTTP(S) address")
        parsed, address = checked
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        sock = socket.create_connection(
            (str(address), parsed.port or (443 if parsed.scheme == "https" else 80)),
            _TIMEOUT,
        )
        try:
            if parsed.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
            sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {parsed.netloc}\r\n"
                          f"User-Agent: {_USER_AGENT}\r\nAccept: text/html,application/xhtml+xml\r\n"
                          "Connection: close\r\n\r\n").encode("ascii", "ignore"))
            response = http.client.HTTPResponse(sock)
            response.begin()
            if response.status in {301, 302, 303, 307, 308}:
                target = response.getheader("Location")
                if not target:
                    raise ValueError("redirect without location")
                current = urllib.parse.urljoin(current, target)
                continue
            if response.status != 200:
                raise ValueError('HTTP response is not successful')
            body = response.read(_MAX_BYTES + 1)
            content_type = response.getheader('Content-Type', '')
            body = _decode_body(body, response.getheader('Content-Encoding', ''), content_type)
            media_type = content_type.split(';', 1)[0].lower()
            if not media_type and body.lstrip()[:32].lower().startswith((b'<!doctype html', b'<html')):
                media_type = 'text/html'
            return current, media_type, body
        finally:
            sock.close()
    raise ValueError("too many redirects")


def _verify_one(query: str, url: str) -> dict:
    if not _public_http_url(url):
        return {"status": "blocked", "url": url, "reason": "URL is not a public HTTP(S) address"}
    try:
        final_url, content_type, body = _fetch(url)
        if len(body) > _MAX_DECODED_BYTES:
            return {"status": "unverified", "url": final_url, "reason": "page exceeded size limit"}
        if content_type not in {"text/html", "application/xhtml+xml"}:
            return {"status": "unverified", "url": final_url, "reason": "not an HTML product page"}
        parser = _PageParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        documents = []
        for raw in parser.jsonld:
            try:
                documents.append(json.loads(html.unescape(raw)))
            except (TypeError, ValueError):
                continue
        products = _products(documents)
        html_evidence = _html_offer(body.decode('utf-8'), final_url, products)
        if html_evidence and _relevant(query, html_evidence['product']):
            return {'status': 'verified', 'url': final_url, **html_evidence}
        if len(products) != 1:
            return {"status": "unverified", "url": final_url,
                    "reason": "page contains zero or multiple product records"}
        product = products[0]
        product_url = product.get("url")
        if product_url:
            product_url = urllib.parse.urljoin(final_url, str(product_url))
            if not _public_http_url(product_url):
                return {"status": "unverified", "url": final_url,
                        "reason": "product record points to an unsafe URL"}
            product_parsed = urllib.parse.urlparse(product_url)
            final_parsed = urllib.parse.urlparse(final_url)
            if (product_parsed.hostname != final_parsed.hostname or
                    product_parsed.path.rstrip("/") != final_parsed.path.rstrip("/")):
                return {"status": "unverified", "url": final_url,
                        "reason": "product record is not bound to the fetched page"}
        evidence = _offer(product, parser.meta)
        if not evidence or not _relevant(query, evidence["product"]):
            return {"status": "unverified", "url": final_url,
                    "reason": "page did not provide a matching specific product offer"}
        return {"status": "verified", "url": final_url,
                'payment_condition': 'not confirmed', **evidence}
    except Exception as exc:
        return {"status": "unverified", "url": url,
                "reason": f"page could not be safely read: {type(exc).__name__}"}


def verify_offer_urls(query: str, urls: list[str]) -> list[dict]:
    """Verify at most four already-returned URLs; never invents or searches URLs."""
    results = []
    seen = set()
    for url in urls:
        clean = str(url).strip()
        if clean and clean not in seen:
            seen.add(clean)
            results.append(_verify_one(query, clean))
        if len(results) >= _MAX_URLS:
            break
    return results
