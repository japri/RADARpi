# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import unittest,time,threading
from cloud_client import CloudClient,select_source,latest_time,bounds
class CloudsTests(unittest.TestCase):
 def client(self):
  c=CloudClient.__new__(CloudClient);c.lock=threading.Lock();c.wake=threading.Event();c.desired=None;c.result=None;c.error='';return c
 def test_sources(self):
  for lat,lon,name in [(-6,107,'NASA HIMAWARI'),(40,-74,'NASA GOES-E'),(37,-122,'NASA GOES-W'),(51,0,'EUMETSAT'),(20,55,'EUMETSAT IODC')]:self.assertEqual(select_source(lat,lon)[3],name)
  self.assertIsNone(select_source(88,0))
 def test_timestamp_requires_real_metadata(self):
  xml='<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Layer><Name>test</Name><Dimension name="time" default="2026-10-18T09:30:00Z"/></Layer></WMS_Capabilities>'
  stamp,epoch=latest_time(xml,'test');self.assertEqual(stamp,'2026-10-18T09:30:00Z');self.assertGreater(epoch,0)
  with self.assertRaises(ValueError): latest_time(xml,'missing')
 def test_cache_location_off_expiry(self):
  c=self.client();cfg=dict(latitude=-6,longitude=107,radius_km=50)
  c.result=dict(key=(-6,107,50),timestamp=time.time()-6000,rgba=b'x')
  self.assertTrue(c.snapshot(cfg)[1].startswith('OLD'))
  self.assertIsNone(c.snapshot(dict(cfg,longitude=110))[0])
  self.assertEqual(c.snapshot(dict(cfg,cloud_overlay=False))[1],'CLOUDS OFF')
  c.result['timestamp']=time.time()-11000
  self.assertEqual(c.snapshot(cfg)[1],'CLOUD IMAGE EXPIRED')
 def test_no_coverage_not_clear_skies(self):
  self.assertEqual(self.client().snapshot(dict(latitude=88,longitude=0,radius_km=50))[1],'CLOUD NO COVERAGE')
 def test_dateline_bounds(self):
  self.assertGreater(bounds((0,179.9,200))[2],180)
  self.assertLess(bounds((0,-179.9,200))[0],-180)
