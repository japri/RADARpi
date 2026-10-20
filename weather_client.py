# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Background Open-Meteo current model weather for the selected pin."""
import json
import math
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from radar import retry_delay


def description(code,day=True):
    if code==0: return 'SUNNY' if day else 'CLEAR'
    if code==1: return 'MOSTLY CLEAR'
    if code==2: return 'PART CLOUDY'
    if code==3: return 'OVERCAST'
    if code in (45,48): return 'FOG'
    if code in (51,53,55): return 'DRIZZLE'
    if code in (56,57,66,67): return 'FREEZING RAIN'
    if code in (61,63,65): return 'RAIN'
    if code in (71,73,75,77): return 'SNOW'
    if code in (80,81,82): return 'SHOWERS'
    if code in (85,86): return 'SNOW SHOWERS'
    if code in (95,96,99): return 'THUNDERSTORM'
    return 'WEATHER --'


def parse(data,key):
    row=data['current']; temp=float(row['temperature_2m']); stamp=float(row['time'])
    if not math.isfinite(temp) or not -100<=temp<=65 or not math.isfinite(stamp): raise ValueError('Invalid weather')
    if data.get('current_units',{}).get('temperature_2m')!='°C': raise ValueError('Wrong temperature unit')
    if not -900 <= time.time()-stamp <=7200: raise ValueError('Old weather')
    code=row.get('weather_code')
    return dict(key=key,temp=temp,stamp=stamp,condition=description(code,row.get('is_day')==1))


class WeatherClient:
    def __init__(self):
        self.lock=threading.Lock();self.stop=threading.Event();self.wake=threading.Event()
        self.desired=None;self.result=None;self.error=False
        threading.Thread(target=self.run,daemon=True).start()

    def snapshot(self,cfg):
        key=(float(cfg['latitude']),float(cfg['longitude']))
        with self.lock:
            if self.desired!=key:
                self.desired=key;self.error=False;self.wake.set()
            row=self.result if self.result and self.result['key']==key else None
            error=self.error
        fahrenheit = cfg.get('temperature_unit') == 'fahrenheit'
        unit = 'F' if fahrenheit else 'C'
        if row and -900<=time.time()-row['stamp']<=7200:
            old=error or time.time()-row['stamp']>2700
            value = row['temp'] * 9 / 5 + 32 if fahrenheit else row['temp']
            return f"{value:.0f}°{unit}", ('OLD ' if old else '')+row['condition']
        return f'--°{unit}','UNAVAILABLE' if error else 'WEATHER...'

    def run(self):
        last_key=None;last_attempt=0;deadline=0;blocked=0
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock: key=self.desired
            due=deadline if key==last_key else max(last_attempt+60,blocked)
            if key is None or time.monotonic()<due:
                self.wake.wait(1);continue
            last_key=key;last_attempt=time.monotonic();delay=900
            try:
                params=dict(latitude=key[0],longitude=key[1],current='temperature_2m,weather_code,is_day',temperature_unit='celsius',timeformat='unixtime',timezone='UTC')
                request=urllib.request.Request('https://api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode(params),headers={'User-Agent':'PersonalFlightRadar/3.0'})
                with urllib.request.urlopen(request,timeout=20) as response:
                    row=parse(json.loads(response.read(100000)),key)
                with self.lock:
                    if key==self.desired: self.result=row;self.error=False
            except Exception as error:
                delay=max(900,retry_delay(error,1));blocked=time.monotonic()+delay
                with self.lock:
                    if key==self.desired:self.error=True
            deadline=time.monotonic()+delay
