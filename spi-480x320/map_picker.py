"""On-demand OpenStreetMap tiles for a small native pin picker."""
import math
from pathlib import Path
import queue
import threading
import time
import urllib.error
import urllib.request
import json


def world(lat,lon,zoom):
    lat = max(-85.05112878,min(85.05112878,lat))
    scale = 256*2**zoom
    return (lon+180)/360*scale,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*scale


def coordinate(x,y,zoom):
    scale = 256*2**zoom
    y = max(0,min(scale,y))
    return math.degrees(math.atan(math.sinh(math.pi*(1-2*y/scale)))),(x/scale*360)%360-180


class MapPicker:
    def __init__(self,root):
        self.cache = Path(root)/'map-cache'
        self.cache.mkdir(exist_ok=True)
        self.lat,self.lon,self.zoom = -6.2088,106.8456,11
        self.url = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
        self.visible = set()
        self.pending = set()
        self.failed = {}
        self.images = {}
        self.jobs = queue.Queue()
        self.message = 'Tap map to move pin; +/- to zoom'
        threading.Thread(target=self.worker,daemon=True).start()

    def reset(self,cfg):
        self.lat,self.lon = max(-85.05112878,min(85.05112878,cfg['latitude'])),cfg['longitude']
        self.url = cfg.get('map_tile_url',self.url)
        self.zoom = 11

    def worker(self):
        while True:
            key = self.jobs.get()
            try:
                if key not in self.visible:
                    continue
                z,x,y = key
                path = self.cache/f'{z}-{x}-{y}.png'
                meta_path = path.with_suffix('.json')
                headers = {'User-Agent':'JakartaDeskRadar/2.0 (native personal radar location picker)'}
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text())
                    if meta.get('etag'):
                        headers['If-None-Match'] = meta['etag']
                    if meta.get('modified'):
                        headers['If-Modified-Since'] = meta['modified']
                req = urllib.request.Request(self.url.format(z=z,x=x,y=y),headers=headers)
                try:
                    with urllib.request.urlopen(req,timeout=10) as response:
                        content = response.read(1024*1024)
                        if not content.startswith(b'\x89PNG'):
                            raise ValueError('Unexpected map response')
                        temp = path.with_suffix('.tmp')
                        temp.write_bytes(content)
                        temp.replace(path)
                        meta_path.write_text(json.dumps({'etag':response.headers.get('ETag'),'modified':response.headers.get('Last-Modified')}))
                except urllib.error.HTTPError as error:
                    if error.code != 304 or not path.exists():
                        raise
                    path.touch()
                self.message = 'Tap map to move pin; +/- to zoom'
            except Exception:
                self.failed[key] = time.monotonic()+60
                self.message = 'Map unavailable; coordinates still work'
            finally:
                self.pending.discard(key)

    def draw(self,screen,view):
        import pygame
        rect = pygame.Rect(0,38,480,222)
        cx,cy = world(self.lat,self.lon,self.zoom)
        left,top = cx-240,cy-111
        needed = []
        n = 2**self.zoom
        for tx in range(math.floor(left/256),math.floor((left+479)/256)+1):
            for ty in range(math.floor(top/256),math.floor((top+221)/256)+1):
                if 0<=ty<n:
                    needed.append(((self.zoom,tx%n,ty),int(tx*256-left),int(38+ty*256-top)))
        self.visible = {item[0] for item in needed}
        screen.set_clip(rect)
        screen.fill((15,32,21),rect)
        for key,x,y in needed:
            path = self.cache/('%s-%s-%s.png'%key)
            if path.exists():
                stamp = path.stat().st_mtime
                if key not in self.images or self.images[key][0] != stamp:
                    try:
                        if len(self.images)>32:
                            self.images.clear()
                        self.images[key] = stamp,pygame.image.load(str(path)).convert()
                    except pygame.error:
                        continue
                screen.blit(self.images[key][1],(x,y))
            else:
                pygame.draw.rect(screen,(28,63,38),(x,y,256,256),1)
            # Cache viewed tiles >=7 days; never prefetch regions or zoom levels.
            if (not path.exists() or time.time()-path.stat().st_mtime>7*86400) and key not in self.pending and self.failed.get(key,0)<time.monotonic():
                self.pending.add(key)
                self.jobs.put(key)
        pygame.draw.circle(screen,(0,20,0),(240,149),12,3)
        pygame.draw.circle(screen,(40,255,70),(240,149),8,2)
        pygame.draw.line(screen,(0,10,0),(224,149),(256,149),2)
        pygame.draw.line(screen,(0,10,0),(240,133),(240,165),2)
        pygame.draw.rect(screen,(2,12,5),(1,242,264,18))
        view.label('(c) OpenStreetMap contributors',5,243,12)
        screen.set_clip(None)

    def tap(self,pos):
        cx,cy = world(self.lat,self.lon,self.zoom)
        self.lat,self.lon = coordinate(cx+pos[0]-240,cy+pos[1]-149,self.zoom)
