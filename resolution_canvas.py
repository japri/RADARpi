# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Logical UI coordinates backed by native-resolution pixels.

This facade is used only by drawing modules; SDL/events keep real pygame.
Vector primitives and fonts rasterize at panel density. Bitmap sources retain
their own density and are resampled only when blitted to a different density.
"""
from types import SimpleNamespace
import pygame as pg
import pygame.gfxdraw

_scale = 1.0

def configure(scale):
    global _scale
    _scale = float(scale)

def pixels(surface):
    return surface.pixels if isinstance(surface, Canvas) else surface

class Canvas:
    def __init__(self, size, flags=0, *, density=None, source=None):
        self.density = _scale if density is None else density
        self.size = tuple(size)
        self.pixels = source if source is not None else pg.Surface(
            tuple(max(1, round(v*self.density)) for v in size), flags)
    def get_size(self): return self.size
    def get_width(self): return self.size[0]
    def get_height(self): return self.size[1]
    def get_rect(self, **kwargs): return self._rect(kwargs)
    def _rect(self, kwargs):
        rect = pg.Rect(0, 0, *self.size)
        for key, value in kwargs.items(): setattr(rect, key, value)
        return rect
    def convert(self):
        self.pixels = self.pixels.convert()
        return self
    def convert_alpha(self):
        self.pixels = self.pixels.convert_alpha()
        return self
    def fill(self, color, rect=None):
        return self.pixels.fill(color, scaled_rect(rect,self.density) if rect is not None else None)
    def set_clip(self, rect=None):
        self.pixels.set_clip(scaled_rect(rect,self.density) if rect is not None else None)
    def blit(self, source, dest, special_flags=0):
        density = source.density if isinstance(source, Canvas) else 1.0
        bitmap = pixels(source)
        if abs(density-self.density)>1e-6:
            bitmap = pg.transform.smoothscale(bitmap, tuple(max(1,round(v*self.density/density)) for v in bitmap.get_size()))
        return self.pixels.blit(bitmap, point(dest[:2],self.density), special_flags=special_flags)

def point(value,s): return tuple(round(v*s) for v in value)
def scaled_rect(value,s):
    r=pg.Rect(value)
    return pg.Rect(round(r.x*s),round(r.y*s),round(r.right*s)-round(r.x*s),round(r.bottom*s)-round(r.y*s))
def stroke(width,s): return max(1,round(width*s)) if width else 0

class Draw:
    def __getattr__(self,name):
        def draw(surface,color,*args,**kwargs):
            s=surface.density if isinstance(surface,Canvas) else 1
            a=list(args)
            if name in ('line','aaline'):
                a[:2]=[point(v,s) for v in a[:2]]
                if name=='line' and len(a)>2: a[2]=stroke(a[2],s)
                elif name=='line' and 'width' not in kwargs: a.append(stroke(1,s))
            elif name in ('lines','aalines'):
                a[1]=[point(v,s) for v in a[1]]
                if name=='lines' and len(a)>2: a[2]=stroke(a[2],s)
                elif name=='lines' and 'width' not in kwargs: a.append(stroke(1,s))
            elif name=='polygon':
                a[0]=[point(v,s) for v in a[0]]
                if len(a)>1: a[1]=stroke(a[1],s)
            elif name=='circle':
                a[0]=point(a[0],s); a[1]=round(a[1]*s)
                if len(a)>2: a[2]=stroke(a[2],s)
            elif name in ('rect','arc'):
                a[0]=scaled_rect(a[0],s)
                wi=1 if name=='rect' else 3
                if len(a)>wi: a[wi]=stroke(a[wi],s)
            else: raise NotImplementedError(name)
            for key in ('width','border_radius'):
                if key in kwargs: kwargs[key]=stroke(kwargs[key],s)
            return getattr(pg.draw,name)(pixels(surface),color,*a,**kwargs)
        return draw

class Font:
    def __init__(self,path,size):
        self.density=_scale
        self.font=pg.font.Font(path,max(1,round(size*_scale)))
    def size(self,text): return tuple(v/self.density for v in self.font.size(text))
    def render(self,*args):
        bitmap=self.font.render(*args)
        return Canvas(tuple(v/self.density for v in bitmap.get_size()),density=self.density,source=bitmap)

def aacircle(surface,x,y,r,color):
    s=surface.density if isinstance(surface,Canvas) else 1
    return pg.gfxdraw.aacircle(pixels(surface),round(x*s),round(y*s),round(r*s),color)

def bitmap(source): return Canvas(source.get_size(),density=1,source=source)
def rotozoom(surface,angle,scale):
    result=pg.transform.rotozoom(pixels(surface),angle,scale)
    density=surface.density if isinstance(surface,Canvas) else 1
    return Canvas(tuple(v/density for v in result.get_size()),density=density,source=result)

class Facade:
    Surface=Canvas
    draw=Draw()
    gfxdraw=SimpleNamespace(aacircle=aacircle)
    font=SimpleNamespace(Font=Font)
    transform=SimpleNamespace(rotozoom=rotozoom)
    image=SimpleNamespace(frombytes=lambda *a:bitmap(pg.image.frombytes(*a)),load=lambda *a:bitmap(pg.image.load(*a)))
    def __getattr__(self,name): return getattr(pg,name)

pygame=Facade()

def sweep_frames(surface,density):
    """Crop invisible sweep pixels before caching; cap all frames at 64 MiB."""
    frames=[]
    for i in range(144):
        frame=pg.transform.rotozoom(pixels(surface),-i*2.5,1)
        bounds=frame.get_bounding_rect()
        offset=(bounds.x-frame.get_width()//2,bounds.y-frame.get_height()//2)
        frames.append((frame.subsurface(bounds).copy(),offset))
    area=sum(frame.get_width()*frame.get_height() for frame,offset in frames)
    scale=min(density,(64*1024*1024/(area*4))**.5)
    result=[]
    for frame,offset in frames:
        size=frame.get_size()
        native=pg.transform.smoothscale(frame,tuple(max(1,round(v*scale)) for v in size)) if scale!=1 else frame
        result.append((Canvas(size,density=scale,source=native),offset))
    return result

def layout(width,height,rotation=0):
    """Return landscape design width and native density after mounting rotation."""
    if rotation in (90,270): width,height=height,width
    logical_width=max(480,round(width*320/height))
    return logical_width,min(width/logical_width,height/320)
