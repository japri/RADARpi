# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Offline layout + persistent units check; run with application folder as cwd."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import json
import tempfile
from copy import copy
from unittest.mock import patch
import pygame as pg
from radar_ui import RadarView
from radar import Feed
from setup_ui import SetupUI
from network_client import NetworkClient

pg.display.init();pg.font.init();pg.display.set_mode((1,1))
native=Path('resolution_canvas.py').exists()
if native:
    from resolution_canvas import Canvas,configure,pixels
    configure(1.5);screen=Canvas((533,320)).convert();settings=Canvas((480,320)).convert()
else:
    screen=pg.Surface((480,320));settings=pg.Surface((480,320))
    pixels=lambda value:value
cfg=json.loads(Path('config.json' if Path('config.json').exists() else 'config.example.json').read_text())
view=RadarView(screen)
class Weather:
    def snapshot(self,cfg):return '30°C','MOSTLY CLEAR'
view.weather=Weather()
row=dict(hex='8a1669',flight='TEST123',distance=32,bearing=1,track=327,gs=400,alt_baro=37575,t='A320',r='PK-TEST',route_label='CGK > DPS')
feed=Feed(cfg);feed.rows=[row];feed.received=100
sv=copy(view);sv.screen=settings
ui=SetupUI(settings,sv,feed,NetworkClient(enabled=False),Path('.'))
for locked in (False,True):
    with patch('split_flap.time.monotonic',return_value=0):view.draw(cfg,[row],row,3,'','',100,2.8,locked=locked)
    with patch('split_flap.time.monotonic',return_value=4):view.draw(cfg,[row],row,3,'','',100,2.8,locked=locked)
    assert view.hit(view.lock_rect.center)==('lock',None)
    assert view.flaps.fields['route'].target=='CGK > DPS'
    pg.image.save(pixels(screen),f'lock-{locked}.png')
view.draw(cfg,[],None,3,'','',100,2.8,locked=True)
assert view.hit(view.lock_rect.center)==('lock',None)
pg.image.save(pixels(screen),'lock-waiting.png')
view.draw(cfg,[],None,3,'','',100,2.8,locked=False)
assert view.lock_rect is None
print('PASS lock icon hit target, full route text, missing target unlock')
pg.quit()
