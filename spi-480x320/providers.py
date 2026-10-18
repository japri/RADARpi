"""Verified no-key nearby-aircraft APIs. Manual choice, never rotate around limits."""
import math

PROVIDERS = {
    'adsb_lol': dict(name='ADSB.lol', home='https://www.adsb.lol',
        endpoint='https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}', credit='ODbL / adsbdb'),
    'adsb_fi': dict(name='ADSB.fi', home='https://adsb.fi',
        endpoint='https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{nm}', credit='Routes: adsbdb'),
}


def provider_id(cfg):
    value = cfg.get('data_provider', 'adsb_lol')
    return value if value in PROVIDERS else 'adsb_lol'


def provider(cfg):
    return PROVIDERS[provider_id(cfg)]


def position_url(cfg):
    return provider(cfg)['endpoint'].format(lat=cfg['latitude'], lon=cfg['longitude'],
        nm=min(250, math.ceil(cfg['radius_km']/1.852)))


def poll_seconds(cfg):
    try:
        value = float(cfg.get('refresh_seconds', 8))
        return max(5, min(300, value)) if math.isfinite(value) else 8
    except (TypeError, ValueError):
        return 8
