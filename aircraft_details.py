"""Display-only conversions and offline ICAO registration-state lookup."""
import csv
import math
import re
from functools import lru_cache
from pathlib import Path

SYSTEMS = ('aviation', 'metric', 'imperial')

def system(cfg):
    value = cfg.get('measurement_units', 'aviation')
    return value if value in SYSTEMS else 'aviation'

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None

def altitude(value, cfg):
    if value == 'ground':
        return 'GROUND', ''
    unit = 'M' if system(cfg) == 'metric' else 'FT'
    n = number(value)
    return ('--' if n is None else f'{n * (.3048 if unit == "M" else 1):,.0f}'), unit

def speed(value, cfg):
    factor, unit = {'aviation': (1, 'KT'), 'metric': (1.852, 'KM/H'),
                    'imperial': (1.150779448, 'MPH')}[system(cfg)]
    n = number(value)
    return ('--' if n is None or n < 0 else f'{n*factor:.0f}') + ' ' + unit

def distance(km, cfg, with_unit=True):
    imperial = system(cfg) == 'imperial'
    value = f'{km / 1.609344 if imperial else km:.0f}'
    return value + (' MI' if imperial else ' KM') if with_unit else value

def direction(aircraft):
    # Ground track is not aircraft nose heading; retain that distinction.
    for key, label, suffix in (('true_heading', 'HDG', 'T'),
                               ('mag_heading', 'HDG', 'M'), ('track', 'TRK', '')):
        value = number(aircraft.get(key))
        if value is not None and 0 <= value <= 360:
            return f'{label} {round(value)%360:03d}°{suffix}'
    return 'HDG --'

@lru_cache(maxsize=1)
def country_ranges():
    with Path(__file__).with_name('aircraft-countries.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = [(int(r['startAddr'],16), int(r['endAddr'],16), r['state']) for r in csv.DictReader(f)]
    return sorted(rows, key=lambda row: row[1]-row[0])

@lru_cache(maxsize=1024)
def registration_country(hex_id):
    if not isinstance(hex_id, str) or not re.fullmatch('[0-9a-fA-F]{6}', hex_id):
        return 'Unknown'
    address = int(hex_id,16)
    if address in (0, 0xFFFFFF):
        return 'Unknown'
    try:
        rows = country_ranges()
    except (OSError, ValueError, KeyError):
        return 'Unknown'
    for start, end, country in rows:
        if start <= address <= end:
            if country.startswith('ICAO'):
                return 'Unknown'
            return {'United States of America':'United States',
                    'United Kingdom of Great Britain and Northern Ireland':'United Kingdom',
                    'Iran (Islamic Republic of)':'Iran',
                    'Democratic People’s Republic of Korea':'North Korea',
                    'Republic of Korea':'South Korea',
                    'Russian Federation':'Russia'}.get(country, country)
    return 'Unknown'
