# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Render privacy-safe README examples offline; run from either app directory.
No personal configuration, device identifiers, cached imagery or live feed is read.
"""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
import sys,time,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from unittest.mock import patch
import pygame as pg
import numpy as np
from radar_ui import RadarView
pg.display.init();pg.font.init();pg.display.set_mode((1,1))
native=Path('resolution_canvas.py').exists()
if native:
    from resolution_canvas import Canvas,configure,pixels
    configure(1.5);screen=Canvas((533,320)).convert()
else:
    screen=pg.Surface((480,320));pixels=lambda value:value
# Generic Jakarta city centre, not a device/user location.
cfg=dict(latitude=-6.2088,longitude=106.8456,radius_km=50,stale_seconds=90,
         location_label='DEMO',measurement_units='aviation',display_contrast=3,
         data_provider='adsb_fi',callsign_labels='all',cloud_overlay=True)
y,x=np.mgrid[0:280,0:280]
a=np.exp(-((x-85)**2+(y-75)**2)/4500)*55+np.exp(-((x-205)**2+(y-190)**2)/2200)*40
rgba=np.zeros((280,280,4),dtype=np.uint8);rgba[:,:,:3]=(60,195,100)
rgba[:,:,3]=(a*((x-140)**2+(y-140)**2<140**2)).astype(np.uint8)
class Clouds:
    def snapshot(self,cfg):return dict(key=('demo',),timestamp=0,rgba=rgba.tobytes(),source='DEMO CLOUDS'),'ILLUSTRATIVE DATA'
class Weather:
    def snapshot(self,cfg):return '29°C','PART CLOUDY'
view=RadarView(screen);view.clouds=Clouds();view.weather=Weather()
rows=[dict(hex='8a1669',flight='GIA421',distance=32,bearing=55,track=265,gs=366,
           alt_baro=13975,t='A320',r='PK-DEMO',route_label='UPG > CGK'),
      dict(hex='8a166a',flight='BTK6269',distance=22,bearing=245,track=110,gs=320,
           alt_baro=8500,t='B738',r='PK-SAMPLE'),
      dict(hex='8a166b',flight='CTV945',distance=38,bearing=320,track=150,gs=310,
           alt_baro=12000,t='A320',r='PK-SAMPLE')]
clock=time.struct_time((2026,1,1,12,0,0,3,1,-1))
with patch('radar_ui.time.localtime',return_value=clock):
    for now in (0,4):
        with patch('split_flap.time.monotonic',return_value=now):
            view.draw(cfg,rows,rows[0],1,'','',100,2.8,display_status='DEMO',locked=True)
name='radar-800x480-demo.png' if native else 'radar-480x320-demo.png'
pg.image.save(pixels(screen),name)
print('Created',name,'with sample data only')
pg.quit()
