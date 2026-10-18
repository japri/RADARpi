import math
import tempfile
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import patch
import radar
from providers import position_url, poll_seconds, provider_id

CFG = dict(latitude=-6.2,longitude=106.8,radius_km=50,refresh_seconds=8)


class ProviderTests(unittest.TestCase):
    def test_urls_and_poll_bounds(self):
        self.assertEqual(position_url(CFG),'https://api.adsb.lol/v2/point/-6.2/106.8/27')
        self.assertEqual(position_url(dict(CFG,data_provider='adsb_fi')),'https://opendata.adsb.fi/api/v3/lat/-6.2/lon/106.8/dist/27')
        self.assertEqual(provider_id(dict(CFG,data_provider='invalid')),'adsb_lol')
        for value,expected in [(1,5),(8,8),(300,300),(999,300),(float('nan'),8),('bad',8)]:
            self.assertEqual(poll_seconds(dict(CFG,refresh_seconds=value)),expected)

    def test_label_and_interval_edits_preserve_aircraft(self):
        feed = radar.Feed(dict(CFG))
        feed.rows,feed.received = [{'hex':'abc'}],100
        with patch.object(feed,'save'):
            feed.change(location_label='Jakarta',refresh_seconds=30)
            self.assertEqual(feed.rows,[{'hex':'abc'}])
            self.assertEqual(feed.revision,0)
            feed.change(data_provider='adsb_fi')
            self.assertEqual(feed.rows,[])
            self.assertIsNone(feed.received)
            self.assertEqual(feed.revision,1)

    def test_switch_discards_old_response_and_keeps_per_provider_backoff(self):
        feed = radar.Feed(dict(CFG))
        clock,requests = [0],[]
        def request(url):
            requests.append((url,clock[0]))
            if len(requests)==1:
                feed.change(data_provider='adsb_fi')
                raise urllib.error.HTTPError(url,429,'Limited',{'Retry-After':'120'},None)
            if len(requests)==2:
                self.assertEqual(feed.error,'')
                feed.change(data_provider='adsb_lol')
                return {'ac':[dict(hex='old-fi',lat=-6.2,lon=106.8,seen_pos=0)]}
            self.assertEqual(feed.rows,[])
            feed.stop.set()
            return {'ac':[]}
        with patch.object(feed,'save'), patch('radar.get_json',side_effect=request), patch('radar.time.monotonic',side_effect=lambda:clock[0]), patch.object(feed.wake,'wait',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            feed.run()
        self.assertIn('adsb.lol',requests[0][0])
        self.assertIn('adsb.fi',requests[1][0])
        self.assertEqual([t for _,t in requests],[0,0,120])

    def test_interval_edit_recomputes_success_deadline(self):
        feed = radar.Feed(dict(CFG))
        clock,requested,changed = [0],[],[False]
        def request(url):
            requested.append(clock[0])
            if len(requested)==2:
                feed.stop.set()
            return {'ac':[]}
        def wait(seconds):
            if not changed[0]:
                clock[0] += 2
                changed[0] = True
                feed.change(refresh_seconds=30)
            else:
                clock[0] += seconds
        with patch.object(feed,'save'),patch('radar.get_json',side_effect=request),patch('radar.time.monotonic',side_effect=lambda:clock[0]),patch.object(feed.wake,'wait',side_effect=wait):
            feed.run()
        self.assertEqual(requested,[0,30])


if __name__ == '__main__':
    unittest.main()
