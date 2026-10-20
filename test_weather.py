# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import unittest,time,threading
from unittest.mock import patch
from weather_client import parse,description,WeatherClient
class WeatherTests(unittest.TestCase):
 def test_codes(self):
  self.assertEqual(description(0,False),'CLEAR');self.assertEqual(description(95),'THUNDERSTORM');self.assertEqual(description(None),'WEATHER --')
 def test_validation(self):
  data={'current':{'temperature_2m':28,'time':time.time(),'weather_code':3},'current_units':{'temperature_2m':'°C'}}
  self.assertEqual(parse(data,(0,0))['temp'],28)
  data['current']['temperature_2m']=float('nan')
  with self.assertRaises(ValueError):parse(data,(0,0))
 def test_expiry_and_pin(self):
  c=WeatherClient.__new__(WeatherClient);c.lock=threading.Lock();c.wake=threading.Event();c.desired=None;c.error=False
  c.result=dict(key=(0,0),temp=-20,stamp=time.time(),condition='SNOW')
  self.assertEqual(c.snapshot(dict(latitude=0,longitude=0)),('-20°C','SNOW'))
  self.assertEqual(c.snapshot(dict(latitude=1,longitude=0))[0],'--°C')
  c.result['stamp']=time.time()-8000
  self.assertEqual(c.snapshot(dict(latitude=0,longitude=0))[0],'--°C')
