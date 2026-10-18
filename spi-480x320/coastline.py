"""Offline Natural Earth coastlines, projected only when the radar centre changes."""
import gzip
import json
import math
from pathlib import Path
import pygame

class Coastline:
    def __init__(self):
        try:
            with gzip.open(Path(__file__).with_name('coastline.json.gz'),'rt',encoding='utf-8') as source:
                self.chunks=json.load(source)
        except (OSError,ValueError):
            self.chunks=[]

    def draw(self, surface, cfg, centre, radius):
        lat,lon,km=cfg['latitude'],cfg['longitude'],cfg['radius_km']
        latspan=km/110+0.1
        lonspan=min(180,latspan/max(0.001,math.cos(math.radians(abs(lat)+latspan))) ) if abs(lat)+latspan<90 else 180
        a=math.radians(lat)
        layer=pygame.Surface(surface.get_size(),pygame.SRCALPHA)
        count=0
        for west,south,east,north,points in self.chunks:
            if south>lat+latspan or north<lat-latspan:
                continue
            if not any(east+shift>=lon-lonspan and west+shift<=lon+lonspan for shift in (-360,0,360)):
                continue
            previous=None
            for x,y in points:
                b=math.radians(y); dl=math.radians(x-lon)
                h=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(dl/2)**2
                distance=6371*2*math.asin(math.sqrt(min(1,max(0,h))))
                bearing=math.atan2(math.sin(dl)*math.cos(b),math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(dl))
                p=(centre[0]+math.sin(bearing)*distance/km*radius,centre[1]-math.cos(bearing)*distance/km*radius)
                if previous and math.hypot(p[0]-previous[0],p[1]-previous[1])<radius*2:
                    pygame.draw.aaline(layer,(39,111,66,255),previous,p)
                    count+=1
                previous=p
        mask=pygame.Surface(surface.get_size(),pygame.SRCALPHA)
        pygame.draw.circle(mask,(255,255,255,255),centre,radius-1)
        layer.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(layer,(0,0))
        return count
