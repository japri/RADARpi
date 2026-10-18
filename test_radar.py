import math
import unittest
import urllib.error
from unittest.mock import patch
import radar

CFG = {'latitude': -6.2088, 'longitude': 106.8456, 'radius_km': 100, 'refresh_seconds': 5}


class RadarTests(unittest.TestCase):
    def test_distance_and_north_bearing(self):
        km, bearing = radar.relative_position(1, 0, 0, 0)
        self.assertAlmostEqual(km, 111.195, places=2)
        self.assertAlmostEqual(bearing, 0)
        km, bearing = radar.relative_position(0, 1, 0, 0)
        self.assertAlmostEqual(bearing, math.pi / 2)

    def test_filters_invalid_old_and_distant_positions(self):
        good = {'hex': 'abc123', 'lat': -6.21, 'lon': 106.85, 'seen_pos': 1}
        data = {'ac': [good, dict(good, seen_pos=100), dict(good, lat=0), dict(good, lon=float('nan')), {'hex': 'missing'}]}
        self.assertEqual([r['hex'] for r in radar.aircraft_rows(data, CFG)], ['abc123'])

    def test_empty_is_valid_but_bad_response_is_not(self):
        self.assertEqual(radar.aircraft_rows({'ac': []}, CFG), [])
        with self.assertRaises(ValueError):
            radar.aircraft_rows({'error': 'bad request'}, CFG)

    def test_rate_limit_is_respected(self):
        error = urllib.error.HTTPError('https://example.test', 429, 'Limited', {'Retry-After': '3600'}, None)
        self.assertEqual(radar.retry_delay(error, 1), 3600)
        self.assertEqual(radar.retry_delay(ValueError(), 30), 900)

    def test_connection_recovery(self):
        feed = radar.Feed(dict(CFG))
        calls = []
        def request(url):
            calls.append(url)
            if len(calls) == 1:
                raise OSError('offline')
            feed.stop.set()
            return {'ac': []}
        # Advance the monotonic clock beyond the retry deadline without real waits.
        with patch('radar.get_json', side_effect=request), patch.object(feed.wake, 'wait'), patch('radar.time.monotonic', side_effect=range(0, 10000, 100)):
            feed.run()
        self.assertEqual(len(calls), 2)
        self.assertEqual(feed.error, '')
        self.assertIsNotNone(feed.received)

    def test_polling_uses_configured_interval_with_five_second_floor(self):
        for configured, expected in ((5, 5), (10, 10), (1, 5)):
            with self.subTest(refresh_seconds=configured):
                feed = radar.Feed(dict(CFG, refresh_seconds=configured))
                clock, requested = [0], []
                def request(url):
                    requested.append(clock[0])
                    if len(requested) == 3:
                        feed.stop.set()
                    return {'ac': []}
                def wait(seconds):
                    clock[0] += seconds
                with patch('radar.get_json', side_effect=request), patch.object(feed.wake, 'wait', side_effect=wait), patch('radar.time.monotonic', side_effect=lambda: clock[0]):
                    feed.run()
                self.assertEqual(requested, [0, expected, expected * 2])

    def test_diagnostic_pause_preserves_snapshot_and_resumes(self):
        feed = radar.Feed(dict(CFG))
        feed.rows, feed.received = [{'hex':'cached'}], 0
        feed.diagnostic_pause_until = 3
        clock, requested = [0], []
        def wait(seconds):
            if clock[0] < 3:
                self.assertEqual(feed.rows, [{'hex':'cached'}])
                self.assertEqual(requested, [])
            clock[0] += seconds
        def request(url):
            requested.append(clock[0])
            feed.stop.set()
            return {'ac': []}
        with patch('radar.get_json', side_effect=request), patch.object(feed.wake, 'wait', side_effect=wait), patch('radar.time.monotonic', side_effect=lambda:clock[0]):
            feed.run()
        self.assertEqual(requested, [3])


if __name__ == '__main__':
    unittest.main()
