# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Compare isolated flap rendering with a saved baseline on actual Pi hardware."""
import os,sys,time,statistics,importlib.util
from pathlib import Path
os.environ['SDL_VIDEODRIVER']='dummy'
sys.path.insert(0,str(Path.cwd()))
import pygame as pg
pg.display.init();pg.font.init();pg.display.set_mode((1,1))
from split_flap import SplitFlap
spec=importlib.util.spec_from_file_location('baseline_flap',sys.argv[1])
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
for density in (1,1.5):
 font=pg.font.Font('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',round(19*density))
 screen=pg.Surface((800,480))
 for name,cls in [('before',old.SplitFlap),('after',SplitFlap)]:
  for mode in ('active','settled'):
   board=cls();samples=[]
   board.draw(screen,font,'LNI1391',0,0,(170,255,180),'call','a',now=0)
   for i in range(180):
    t=(i%45)/20 if mode=='active' else 10
    start=time.perf_counter()
    board.draw(screen,font,'LNI1391',0,0,(170,255,180),'call','a',now=t)
    board.draw(screen,font,'CGK > DPS',0,40,(170,255,180),'route','a',now=t)
    samples.append((time.perf_counter()-start)*1000)
   print(density,name,mode,'mean_ms',round(statistics.mean(samples),3),'p95_ms',round(sorted(samples)[170],3),flush=True)
# Reusing a finished board must avoid font measurement, render and scaling.
class CountFont:
 def __init__(self,real):self.real=real;self.calls=0
 def size(self,text):self.calls+=1;return self.real.size(text)
 def get_height(self):return self.real.get_height()
 def render(self,*args):self.calls+=1;return self.real.render(*args)
f=CountFont(font);board=SplitFlap()
board.draw(screen,f,'TEST123',0,0,(1,255,1),'test','a',now=0)
board.draw(screen,f,'TEST123',0,0,(1,255,1),'test','a',now=10)
count=f.calls
screen.set_clip((2,2,200,100));clip=screen.get_clip()
board.draw(screen,f,'TEST123',0,0,(1,255,1),'test','a',now=11)
assert f.calls==count and screen.get_clip()==clip
board.clear();assert not board.labels
print('PASS cached label reuse and clipping')
