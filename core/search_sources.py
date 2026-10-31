"""Small, explicit country/topic preferences; not a trust or safety rating."""
import re
import unicodedata
from urllib.parse import urlsplit

PROFILES = {
    ('BR', 'hardware'): ('kabum.com.br', 'terabyteshop.com.br', 'amazon.com.br'),
    ('BR', 'housing'): ('quintoandar.com.br', 'zapimoveis.com.br', 'vivareal.com.br'),
}


def _plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower())
                   if not unicodedata.combining(c))


def source_plan(query, country='', site=''):
    """Explicit site/country wins; only classified requests consult location."""
    text = _plain(query)
    # Resolve named countries before choosing any named-store alias.
    from core.location_preferences import countries
    aliases_country = {'brasil': 'BR', 'estados unidos': 'US', 'eua': 'US', 'espanha': 'ES',
                       'alemanha': 'DE', 'reino unido': 'GB', 'franca': 'FR', 'japao': 'JP'}
    choices = {**{_plain(name): code for code, (name, _) in countries().items()}, **aliases_country}
    explicit_country = country.strip().upper() or next((code for name, code in choices.items()
        if re.search(r'\b' + re.escape(name) + r'\b', text)), '')
    category = ('housing' if re.search(r'\b(apartamento|apartamentos|imoveis|imovel|apartment|aluguel|alugar|real estate)\b', text)
                else 'hardware' if re.search(r'\b(hardware|placa de video|gpu|rtx|geforce|radeon|ryzen|ssd|processador|motherboard)\b', text)
                else '')
    explicit_site = site.strip().lower()
    if not explicit_site:
        found = re.search(r'(?:site:|https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/\s]|$)', query.lower())
        if found:
            explicit_site = found.group(1)
        else:
            aliases = {'kabum': 'kabum.com.br', 'terabyte': 'terabyteshop.com.br',
                       'amazon': 'amazon.com.br', 'quintoandar': 'quintoandar.com.br',
                       'vivareal': 'vivareal.com.br', 'zap imoveis': 'zapimoveis.com.br'}
            if explicit_country == 'US':
                aliases['amazon'] = 'amazon.com'
            elif explicit_country and explicit_country != 'BR':
                aliases.pop('amazon')
            explicit_site = next((domain for name, domain in aliases.items()
                                  if re.search(r'\b' + re.escape(name) + r'\b', text)), '')
    if explicit_site:
        host = urlsplit(explicit_site if '://' in explicit_site else 'https://' + explicit_site).hostname or ''
        if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', host):
            raise ValueError('Provide a site domain, not a query or address.')
        return {'category': category, 'country': country, 'domains': (host,),
                'region': '', 'explicit_site': True}
    if not category:
        return None
    if country.lower() == 'global' or re.search(r'\b(global|worldwide|mundo todo|mundial|internacional)\b', text):
        return None
    # Country names in the request outrank any saved/IP location. This does
    # not attempt to guess countries from ambiguous cities or language.
    if explicit_country:
        # No local profile means a labeled generic regional search.
        return _plan(category, explicit_country, '', False)
    from core.ip_geolocation import get_search_location
    location = get_search_location() or {}
    code = location.get('country_code', '')
    place = ', '.join(location[k] for k in ('city', 'region', 'country_name') if location.get(k))
    if re.search(r'\b(em|in|near|perto de)\s+\S', text):
        place = ''  # Do not append the saved city to a request naming a place.
    return _plan(category, code, place, False)


def _plan(category, country, region, explicit_site):
    domains = PROFILES.get((country, category))
    return {'category': category, 'country': country, 'domains': domains,
            'region': (region or country) if category == 'housing' else country,
            'explicit_site': explicit_site}


def is_preferred_url(url, domains):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    return parsed.scheme in ('http', 'https') and any(
        host == domain or host.endswith('.' + domain) for domain in domains)
