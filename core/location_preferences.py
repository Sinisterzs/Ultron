"""Confirmed regional preferences, stored through the protected config store."""
from functools import lru_cache
from core.config_store import load_config, update_config

_KEY = 'search_location'


@lru_cache(maxsize=1)
def countries():
    """Country and ISO currency data from Qt's bundled CLDR locale database."""
    from PyQt6.QtCore import QLocale
    result = {}
    for locale in QLocale.matchingLocales(QLocale.Language.AnyLanguage,
                                          QLocale.Script.AnyScript,
                                          QLocale.Country.AnyCountry):
        code = QLocale.territoryToCode(locale.territory())
        currency = locale.currencySymbol(QLocale.CurrencySymbolFormat.CurrencyIsoCode)
        if len(code) == 2 and len(currency) == 3 and code not in result:
            result[code] = (QLocale.territoryToString(locale.territory()), currency)
    return result


def validate_location(city, country_code, region=''):
    def clean(value, required=False):
        if not isinstance(value, str) or len(value) > 120 or any(ord(c) < 32 for c in value):
            raise ValueError('Use nomes de cidade e estado válidos, com até 120 caracteres.')
        value = value.strip()
        if required and not value:
            raise ValueError('Informe a cidade e selecione o país.')
        return value
    if not isinstance(country_code, str) or country_code not in countries():
        raise ValueError('Selecione um país da lista.')
    name, currency = countries()[country_code]
    return {'city': clean(city, True), 'region': clean(region),
            'country_code': country_code, 'country_name': name, 'currency': currency}


def get_override():
    value = load_config().get(_KEY)
    if not isinstance(value, dict):
        return None
    try:
        return validate_location(value.get('city', ''), value.get('country_code'), value.get('region', ''))
    except ValueError:
        return None


def confirm_location(city, country_code, region=''):
    value = validate_location(city, country_code, region)
    update_config({_KEY: value})
    return value


def reset_location():
    update_config({_KEY: None})
