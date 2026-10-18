"""Cached, background infrared imagery from public NASA/EUMETSAT WMS services."""
import base64
import datetime as dt
import io
import json
import math
from pathlib import Path
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

NASA='https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi'
EUMET='https://view.eumetsat.int/geoserver/wms'
NS='{http://www.opengis.net/wms}'
SOURCES=[(140.7,NASA,'Himawari_AHI_Band13_Clean_Infrared','NASA HIMAWARI'),(-137,NASA,'GOES-West_ABI_Band13_Clean_Infrared','NASA GOES-W'),(-75,NASA,'GOES-East_ABI_Band13_Clean_Infrared','NASA GOES-E'),(0,EUMET,'msg_fes:ir108','EUMETSAT'),(45.5,EUMET,'msg_iodc:ir108','EUMETSAT IODC')]

def select_source(lat,lon):
    source=max(SOURCES,key=lambda s:math.cos(math.radians(lat))*math.cos(math.radians(lon-s[0])))
    angle=math.degrees(math.acos(max(-1,min(1,math.cos(math.radians(lat))*math.cos(math.radians(lon-source[0]))))))
    return source if angle<70 else None

def location_key(cfg):
    return (float(cfg['latitude']),float(cfg['longitude']),float(cfg['radius_km']))

def fetch(url, limit=24000000):
    req=urllib.request.Request(url,headers={'User-Agent':'PersonalFlightRadar/3.0','Accept':'*/*'})
    with urllib.request.urlopen(req,timeout=25) as response:
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError('Response too large')
    return data

def query(endpoint,**params):
    return endpoint+'?'+urllib.parse.urlencode(params)

def latest_time(xml,layer):
    root=ET.fromstring(xml)
    for node in root.iter(NS+'Layer'):
        if node.findtext(NS+'Name')==layer:
            for d in node.findall(NS+'Dimension'):
                if d.get('name')=='time':
                    stamp=d.get('default','')
                    parsed=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
                    if parsed.tzinfo is None: raise ValueError('Missing image timezone')
                    return stamp,parsed.timestamp()
    raise ValueError('Satellite time unavailable')

def bounds(key):
    lat,lon,km=key
    dy=km/110+0.03
    dx=dy/max(0.05,math.cos(math.radians(abs(lat)+dy)))
    return lon-dx,lat-dy,lon+dx,lat+dy

def render_image(parts,bbox,key):
    # Inverse azimuthal-equidistant projection aligns with radar distance/bearing.
    import numpy as np
    import pygame
    arrays=[]
    for blob in parts:
        im=pygame.image.load(io.BytesIO(blob))
        if im.get_height()!=420 or im.get_width()>420: raise ValueError('Unexpected image size')
        arrays.append(np.frombuffer(pygame.image.tobytes(im,'RGBA'),dtype=np.uint8).reshape(im.get_height(),im.get_width(),4))
    source=np.concatenate(arrays,axis=1)
    if not np.any(source[:,:,3]) or not np.any(source[:,:,:3]): raise ValueError('No imagery coverage')
    yy,xx=np.mgrid[0:280,0:280]
    east=(xx+0.5-140)/140*key[2]; north=(140-yy-0.5)/140*key[2]
    rho=np.hypot(east,north); c=rho/6371; bearing=np.arctan2(east,north)
    lat0=math.radians(key[0]); lon0=math.radians(key[1])
    lat=np.arcsin(np.cos(c)*math.sin(lat0)+np.sin(c)*math.cos(lat0)*np.cos(bearing))
    lon=lon0+np.arctan2(np.sin(bearing)*np.sin(c)*math.cos(lat0),np.cos(c)-math.sin(lat0)*np.sin(lat))
    lat=np.degrees(lat); lon=key[1]+(np.degrees(lon)-key[1]+180)%360-180
    w,s,e,n=bbox
    ix=np.clip(((lon-w)/(e-w)*source.shape[1]).astype(int),0,source.shape[1]-1)
    iy=np.clip(((n-lat)/(n-s)*source.shape[0]).astype(int),0,source.shape[0]-1)
    pixels=source[iy,ix]
    # A qualitative green rendition of IR brightness, not a cloud/rain measurement.
    strength=np.clip((pixels[:,:,:3].max(axis=2).astype(float)-65)*0.45,0,70)
    out=np.zeros((280,280,4),dtype=np.uint8)
    out[:,:,:3]=(60,195,100)
    out[:,:,3]=(strength*(pixels[:,:,3]/255)*(rho<key[2])).astype(np.uint8)
    return out.tobytes()

class CloudClient:
    def __init__(self,root):
        self.path=Path(root)/'cloud-cache.json'
        self.lock=threading.Lock(); self.wake=threading.Event(); self.stop=threading.Event()
        self.desired=None; self.result=None; self.error=''; self.next_allowed=0
        self.metadata={}
        self.last_key=None; self.last_attempt=0; self.blocked_until=0
        try:
            cached=json.loads(self.path.read_text())
            cached['key']=tuple(cached['key']); cached['rgba']=base64.b64decode(cached['rgba'])
            if len(cached['rgba'])==280*280*4 and 0<=time.time()-cached['timestamp']<10800: self.result=cached
        except (OSError,ValueError,KeyError,TypeError): pass
        threading.Thread(target=self.run,daemon=True).start()

    def snapshot(self,cfg):
        key=location_key(cfg) if cfg.get('cloud_overlay',True) else None
        with self.lock:
            if key!=self.desired:
                self.desired=key; self.error=''; self.wake.set()
            result=self.result if self.result and self.result['key']==key else None
            error=self.error
        if key is None: return None,'CLOUDS OFF'
        if not select_source(key[0],key[1]): return None,'CLOUD NO COVERAGE'
        if result:
            age=time.time()-result['timestamp']
            if age<0 or age>10800: return None,'CLOUD IMAGE EXPIRED'
            stamp=time.strftime('%H:%MZ',time.gmtime(result['timestamp']))
            return result,('OLD ' if age>5400 else 'IR ')+stamp+f' {int(age/60)}m'+(' *' if error else '')
        return None,'CLOUD UNAVAILABLE' if error else 'CLOUD LOADING'

    def load(self,key):
        source=select_source(key[0],key[1])
        if source is None: raise ValueError('Outside supported satellite coverage')
        _,endpoint,layer,name=source
        cached=self.metadata.get(endpoint)
        if not cached or time.monotonic()-cached[0]>=600:
            xml=fetch(query(endpoint,SERVICE='WMS',VERSION='1.3.0',REQUEST='GetCapabilities'))
            cached=(time.monotonic(),xml);self.metadata[endpoint]=cached
        stamp,timestamp=latest_time(cached[1],layer)
        if not -300<=time.time()-timestamp<10800: raise ValueError('Satellite image too old')
        bbox=bounds(key); w,s,e,n=bbox
        ranges=[(w,e,420)]
        # WMS longitude boundaries: split before fetching, then join west to east.
        if e>180:
            first=max(1,min(419,round(420*(180-w)/(e-w))))
            ranges=[(w,180,first),(-180,e-360,420-first)]
        elif w< -180:
            first=max(1,min(419,round(420*(-180-w)/(e-w))))
            ranges=[(w+360,180,first),(-180,e,420-first)]
        blobs=[]
        for west,east,width in ranges:
            data=fetch(query(endpoint,SERVICE='WMS',VERSION='1.1.1',REQUEST='GetMap',LAYERS=layer,STYLES='',SRS='EPSG:4326',BBOX=f'{west},{s},{east},{n}',WIDTH=width,HEIGHT=420,FORMAT='image/png',TRANSPARENT='TRUE',TIME=stamp),2000000)
            if not data.startswith(b'\x89PNG'): raise ValueError('Invalid satellite image')
            blobs.append(data)
        return dict(key=key,rgba=render_image(blobs,bbox,key),timestamp=timestamp,source=name)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock: key=self.desired
            deadline=self.next_allowed if key==self.last_key else max(self.last_attempt+60,self.blocked_until)
            if key is None or time.monotonic()<deadline:
                self.wake.wait(1); continue
            self.last_key=key; self.last_attempt=time.monotonic()
            delay=600
            try:
                result=self.load(key)
                with self.lock:
                    if key==self.desired:
                        self.result=result; self.error=''
                        try:
                            payload=dict(result,rgba=base64.b64encode(result['rgba']).decode())
                            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(payload));temp.replace(self.path)
                        except OSError: pass
            except Exception as error:
                if isinstance(error,urllib.error.HTTPError) and error.headers:
                    try: delay=max(delay,float(error.headers.get('Retry-After','0')))
                    except ValueError: pass
                self.blocked_until=time.monotonic()+delay
                with self.lock:
                    if key==self.desired: self.error=str(error)
            self.next_allowed=time.monotonic()+delay
            self.wake.wait(1)
