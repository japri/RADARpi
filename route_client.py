"""Cached route metadata; network requests never block the display or position feed."""
import email.utils
import json
import re
import threading
import time
import urllib.error
import urllib.request


def parse_route(data, callsign):
    if not isinstance(data, dict) or not isinstance(data.get('response'), dict):
        raise ValueError('Invalid route response')
    route = data['response'].get('flightroute')
    if not isinstance(route, dict):
        return None
    aliases = [str(route.get(key) or '').strip().upper() for key in ('callsign','callsign_icao','callsign_iata')]
    if callsign not in aliases or route.get('midpoint'):
        return None
    codes = []
    for airport in (route.get('origin'), route.get('destination')):
        if not isinstance(airport, dict):
            return None
        code = airport.get('iata_code') or airport.get('icao_code') or ''
        if not isinstance(code, str) or not re.fullmatch(r'[A-Z]{3,4}', code):
            return None
        codes.append(code)
    return ' > '.join(codes) if codes[0] != codes[1] else None


def fetch_route(plane):
    request = urllib.request.Request('https://api.adsbdb.com/v0/callsign/' + plane['callsign'],
        headers={'User-Agent': 'JakartaDeskRadar/1.0', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return parse_route(json.load(response), plane['callsign'])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


class RouteClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}
        self.busy = False
        self.next_allowed = 0
        self.failures = 0

    def lookup(self, aircraft):
        """Return a label immediately; launch at most one background request."""
        callsign = str(aircraft.get('flight') or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{2,8}', callsign):
            return 'Route unknown'
        now = time.monotonic()
        with self.lock:
            cached = self.cache.get(callsign)
            if cached and cached[0] > now:
                return cached[1] or 'Route unknown'
            if not self.busy and now >= self.next_allowed:
                try:
                    plane = dict(callsign=callsign, lat=float(aircraft['lat']), lng=float(aircraft['lon']))
                except (KeyError, TypeError, ValueError):
                    return 'Route unknown'
                self.busy = True
                threading.Thread(target=self._load, args=(plane,), daemon=True).start()
            return 'Route unavailable' if now < self.next_allowed and not self.busy else 'Looking up route'

    def _load(self, plane):
        route, ttl, delay = None, 900, 5
        try:
            route = fetch_route(plane)
            ttl = 21600 if route else 900
            self.failures = 0
        except Exception as error:
            route = 'Route unavailable'
            self.failures += 1
            delay = min(900, 30 * 2 ** min(self.failures, 5))
            if isinstance(error, urllib.error.HTTPError):
                retry = error.headers.get('Retry-After')
                if retry:
                    try:
                        delay = max(delay, float(retry))
                    except ValueError:
                        try:
                            delay = max(delay, email.utils.parsedate_to_datetime(retry).timestamp() - time.time())
                        except (TypeError, ValueError, OverflowError):
                            pass
            ttl = delay
        finally:
            with self.lock:
                now = time.monotonic()
                if len(self.cache) >= 256:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[plane['callsign']] = (now + ttl, route)
                self.next_allowed = now + delay
                self.busy = False
