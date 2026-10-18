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
with tempfile.TemporaryDirectory() as tmp, patch('radar.CONFIG',Path(tmp)/'config.json'):
    ui.open();ui.draw()
    ui.tap(next(rect.center for rect,action in ui.buttons if action=='units'))
    assert ui.page=='units'
    revision=feed.revision
    for mode in ('metric','imperial','aviation'):
        ui.draw()
        ui.tap(next(rect.center for rect,action in ui.buttons if action==('units',mode)))
        saved=json.loads((Path(tmp)/'config.json').read_text())
        assert saved['measurement_units']==mode
        assert feed.received==100 and feed.rows==[row] and feed.revision==revision
        assert saved['radius_km']==cfg['radius_km']
        view.draw(feed.cfg,[row],row,3,'','',100,2.8)
        pg.image.save(pixels(screen),f'details-{mode}.png')
        assert view.hit(view.buttons['range'].center)==('range',None)
    ui.draw();pg.image.save(pixels(settings),'details-settings.png')
    previous_temperature=feed.cfg.get('temperature_unit','celsius')
    ui.tap(next(rect.center for rect,action in ui.buttons if action=='temperature'))
    assert feed.cfg['temperature_unit']!=previous_temperature
print('PASS: units save, preserve feed/range; all unit layouts and settings rendered')
pg.quit()
