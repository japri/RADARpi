"""Offline animation frames and rendering checks; run from application directory."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import json
import time
from unittest.mock import patch
import pygame as pg
from radar_ui import RadarView

pg.display.init();pg.font.init();pg.display.set_mode((1,1))
if Path('resolution_canvas.py').exists():
    from resolution_canvas import Canvas,configure,pixels
    configure(1.5);screen=Canvas((533,320)).convert()
else:
    screen=pg.Surface((480,320));pixels=lambda value:value
cfg=json.loads(Path('config.json' if Path('config.json').exists() else 'config.example.json').read_text())
view=RadarView(screen)
class Weather:
    def snapshot(self,cfg):return '30°C','MOSTLY CLEAR'
view.weather=Weather()
row=dict(hex='8a1669',flight='GIA421',distance=32,bearing=1,track=327,gs=400,alt_baro=37575,t='A320',r='PK-TEST',route_label='CGK > DPS')
def draw(now):
    with patch('split_flap.time.monotonic',return_value=now):
        view.draw(cfg,[row],row,3,'','',100,2.8)
draw(0);draw(4)
row.update(flight='LNI1391',route_label='CGK > SUB')
draw(5)
frames=[]
for dt in (.4,1.1,1.9,3.1):
    draw(5+dt)
    frames.append(pixels(screen).copy())
assert view.flaps.fields['callsign'].target=='LNI1391'
assert view.flaps.fields['route'].target=='CGK > SUB'
assert all(view.flaps.fields['callsign'].cell(i,8.1)[2]==1 for i in range(7))
assert pixels(screen).get_clip()==pixels(screen).get_rect()
assert len(view.flaps.tiles)<=192
assert pg.image.tostring(frames[0],'RGB')!=pg.image.tostring(frames[-1],'RGB')
w,h=frames[0].get_size()
sheet=pg.Surface((w*2,h*2))
for i,frame in enumerate(frames):sheet.blit(frame,((i%2)*w,(i//2)*h))
pg.image.save(sheet,'split-flap-frames.png')
row['route_label']='Route unknown'
draw(9);draw(13)
assert view.flaps.fields['route'].target=='---------'
pg.image.save(pixels(screen),'split-flap-unknown.png')
start=time.perf_counter()
for i in range(30):draw(5+i*.06)
print('PASS: transition, settled text, clipping, bounded cache; whole-view %.1f ms/frame'%((time.perf_counter()-start)*1000/30))
pg.quit()
