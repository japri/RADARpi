# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import unittest
from unittest.mock import patch
import urllib.error
from route_client import RouteClient, parse_route

PLANE = dict(callsign='GIA123', lat=-6.2, lng=106.8)
AIRCRAFT = dict(flight=' GIA123 ', lat=-6.2, lon=106.8)
ROUTE = dict(callsign='GIA123', origin={'iata_code':'CGK'}, destination={'iata_code':'DPS'})

def response(route):
    return {'response': {'flightroute': route}}


class RouteTests(unittest.TestCase):
    def test_matches_callsign_and_validates_route(self):
        self.assertEqual(parse_route(response(ROUTE), 'GIA123'), 'CGK > DPS')
        self.assertIsNone(parse_route(response(ROUTE), 'OTHER'))
        self.assertIsNone(parse_route(response(dict(ROUTE, midpoint={'iata_code':'SUB'})), 'GIA123'))
        self.assertIsNone(parse_route(response(dict(ROUTE, destination={})), 'GIA123'))
        self.assertEqual(parse_route(response(dict(ROUTE, origin={'icao_code':'WIII'}, destination={'icao_code':'WADD'})), 'GIA123'), 'WIII > WADD')

    def test_provider_404_is_unknown_not_a_connection_failure(self):
        from route_client import fetch_route
        error = urllib.error.HTTPError('https://example.test',404,'Unknown',{},None)
        with patch('route_client.urllib.request.urlopen',side_effect=error):
            self.assertIsNone(fetch_route(PLANE))

    def test_cache_and_callsign_change(self):
        client = RouteClient()
        with patch('route_client.fetch_route', return_value='CGK > DPS') as fetch:
            client._load(PLANE)
            for _ in range(20):
                self.assertEqual(client.lookup(AIRCRAFT), 'CGK > DPS')
            self.assertNotEqual(client.lookup(dict(AIRCRAFT, flight='GIA999')), 'CGK > DPS')
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(client.lookup(dict(AIRCRAFT, flight='')), 'Route unknown')

    def test_unknown_cached_and_http_retry_after(self):
        client = RouteClient()
        with patch('route_client.fetch_route', return_value=None) as fetch:
            client._load(PLANE)
            self.assertEqual(client.lookup(AIRCRAFT), 'Route unknown')
            self.assertEqual(fetch.call_count, 1)
        error = urllib.error.HTTPError('https://example.test',429,'Limited',{'Retry-After':'3600'},None)
        with patch('route_client.fetch_route', side_effect=error), patch('route_client.time.monotonic',return_value=100):
            client._load(PLANE)
            self.assertEqual(client.next_allowed, 3700)
            self.assertFalse(client.busy)

    def test_lookup_never_fetches_on_render_thread(self):
        client = RouteClient()
        with patch('route_client.threading.Thread') as thread, patch('route_client.fetch_route') as fetch:
            self.assertEqual(client.lookup(AIRCRAFT), 'Looking up route')
            client.lookup(AIRCRAFT)
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
