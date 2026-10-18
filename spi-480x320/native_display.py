"""Synchronous RGB565 DRM output for the SPI LCD, with bounded damage regions.

Uses the existing kernel driver/libdrm; does not change device-tree or boot files.
DIRTYFB blocks until the kernel has finished uploading each region.
"""
import atexit
import ctypes as C
import ctypes.util
import fcntl
import mmap
import os
from pathlib import Path
import signal
import struct
import numpy as np

U32, U16, I32 = C.c_uint32, C.c_uint16, C.c_int
P32 = C.POINTER(U32)

class Resources(C.Structure):
    _fields_ = [('count_fbs',I32),('fbs',P32),('count_crtcs',I32),('crtcs',P32),
                ('count_connectors',I32),('connectors',P32),('count_encoders',I32),('encoders',P32),
                ('min_width',U32),('max_width',U32),('min_height',U32),('max_height',U32)]

class Mode(C.Structure):
    _fields_ = [('clock',U32)]+[(name,U16) for name in ('hdisplay','hsync_start','hsync_end','htotal','hskew','vdisplay','vsync_start','vsync_end','vtotal','vscan')]+[('vrefresh',U32),('flags',U32),('type',U32),('name',C.c_char*32)]

class Connector(C.Structure):
    _fields_ = [(name,U32) for name in ('connector_id','encoder_id','connector_type','connector_type_id')]+[('connection',I32),('mmWidth',U32),('mmHeight',U32),('subpixel',I32),('count_modes',I32),('modes',C.POINTER(Mode)),('count_props',I32),('props',P32),('prop_values',C.POINTER(C.c_uint64)),('count_encoders',I32),('encoders',P32)]

class Crtc(C.Structure):
    _fields_ = [(name,U32) for name in ('crtc_id','buffer_id','x','y','width','height')]+[('mode_valid',I32),('mode',Mode),('gamma_size',I32)]

class Clip(C.Structure):
    _fields_ = [(name,U16) for name in ('x1','y1','x2','y2')]

def rgb565(rgb):
    """Convert pygame's width-major RGB array to row-major native pixels."""
    values = rgb.astype(np.uint16)
    return (((values[:,:,0] >> 3) << 11) | ((values[:,:,1] >> 2) << 5) | (values[:,:,2] >> 3)).T.copy()

def damage_regions(previous, current):
    if previous is None:
        return [(0,0,480,320)]
    changed = previous != current
    regions = []
    # Physical image is rotated 180 degrees: info panel is on the left.
    # Separate its strips from the scope so animation never dirties its header.
    bounds = [(160,0,480,320)]+[(0,y,160,min(y+32,320)) for y in range(0,320,32)]
    for x1,y1,x2,y2 in bounds:
        ys,xs = np.nonzero(changed[y1:y2,x1:x2])
        if len(xs):
            regions.append((x1+int(xs.min()),y1+int(ys.min()),x1+int(xs.max())+1,y1+int(ys.max())+1))
    return regions

class NativeDisplay:
    def __init__(self, probe_only=False):
        self.fd = self.tty = None
        self.mapping = self.pixels = self.old = None
        self.framebuffer = U32()
        self.handle = 0
        self.started = False
        self.previous = None
        self.frames = self.regions = self.upload_pixels = 0
        self.lib = C.CDLL(ctypes.util.find_library('drm') or 'libdrm.so.2',use_errno=True)
        signatures = {
            'drmModeGetResources':([I32],C.POINTER(Resources)),
            'drmModeFreeResources':([C.POINTER(Resources)],None),
            'drmModeGetConnector':([I32,U32],C.POINTER(Connector)),
            'drmModeFreeConnector':([C.POINTER(Connector)],None),
            'drmModeGetCrtc':([I32,U32],C.POINTER(Crtc)),
            'drmModeFreeCrtc':([C.POINTER(Crtc)],None),
            'drmSetMaster':([I32],I32),'drmDropMaster':([I32],I32),
            'drmModeAddFB':([I32,U32,U32,C.c_uint8,C.c_uint8,U32,U32,P32],I32),
            'drmModeRmFB':([I32,U32],I32),
            'drmModeSetCrtc':([I32,U32,U32,U32,U32,P32,I32,C.POINTER(Mode)],I32),
            'drmModeDirtyFB':([I32,U32,C.POINTER(Clip),U32],I32)}
        for name,(args,result) in signatures.items():
            function = getattr(self.lib,name)
            function.argtypes, function.restype = args,result
        cards = [p for p in Path('/sys/class/drm').glob('card[0-9]*') if (p/'device/driver').resolve().name=='ili9486']
        if len(cards)!=1:
            raise RuntimeError('Expected one ILI9486 DRM display')
        try:
            self.fd = os.open('/dev/dri/'+cards[0].name,os.O_RDWR|os.O_CLOEXEC)
            resources = self.lib.drmModeGetResources(self.fd)
            if not resources:
                raise OSError('Cannot read DRM resources')
            try:
                if resources.contents.count_crtcs!=1 or resources.contents.count_connectors!=1:
                    raise RuntimeError('Unexpected SPI display topology')
                self.crtc_id = resources.contents.crtcs[0]
                self.connector_id = resources.contents.connectors[0]
            finally:
                self.lib.drmModeFreeResources(resources)
            connector = self.lib.drmModeGetConnector(self.fd,self.connector_id)
            if not connector:
                raise OSError('Cannot read LCD connector')
            try:
                if connector.contents.connection!=1 or connector.contents.count_modes<1:
                    raise RuntimeError('LCD has no connected mode')
                self.mode = Mode.from_buffer_copy(bytes(connector.contents.modes[0]))
            finally:
                self.lib.drmModeFreeConnector(connector)
            if (self.mode.hdisplay,self.mode.vdisplay)!=(480,320):
                raise RuntimeError('Expected 480x320 LCD')
            if probe_only:
                return
            self.check(self.lib.drmSetMaster(self.fd),'DRM master')
            old = self.lib.drmModeGetCrtc(self.fd,self.crtc_id)
            if old:
                self.old = Crtc.from_buffer_copy(bytes(old.contents))
                self.lib.drmModeFreeCrtc(old)
            create = bytearray(struct.pack('=IIIIIIQ',320,480,16,0,0,0,0))
            fcntl.ioctl(self.fd,0xc02064b2,create,True) # DRM_IOCTL_MODE_CREATE_DUMB
            _,_,_,_,self.handle,pitch,size = struct.unpack('=IIIIIIQ',create)
            mapping = bytearray(struct.pack('=IIQ',self.handle,0,0))
            fcntl.ioctl(self.fd,0xc01064b3,mapping,True) # DRM_IOCTL_MODE_MAP_DUMB
            offset = struct.unpack('=IIQ',mapping)[2]
            self.mapping = mmap.mmap(self.fd,size,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=offset)
            self.pixels = np.ndarray((320,pitch//2),dtype='<u2',buffer=self.mapping)
            self.check(self.lib.drmModeAddFB(self.fd,480,320,16,16,pitch,self.handle,C.byref(self.framebuffer)),'RGB565 framebuffer')
            self.tty = os.open('/dev/tty7',os.O_RDWR|os.O_CLOEXEC)
            fcntl.ioctl(self.tty,0x4b3a,1) # KDSETMODE, KD_GRAPHICS
            atexit.register(self.close)
            signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(SystemExit(0)))
        except Exception:
            self.close()
            raise

    def check(self, result, operation):
        if result:
            code = C.get_errno()
            raise OSError(code,operation+': '+os.strerror(code))

    def present(self, surface):
        import pygame
        frame = rgb565(pygame.surfarray.array3d(surface))
        regions = damage_regions(self.previous,frame)
        if not regions:
            return
        self.pixels[:,:480] = frame
        if not self.started:
            connector = U32(self.connector_id)
            self.check(self.lib.drmModeSetCrtc(self.fd,self.crtc_id,self.framebuffer,0,0,C.byref(connector),1,C.byref(self.mode)),'Set LCD framebuffer')
            self.started = True
        else:
            for rectangle in regions:
                self.check(self.lib.drmModeDirtyFB(self.fd,self.framebuffer,C.byref(Clip(*rectangle)),1),'Upload LCD region')
        self.previous = frame
        self.frames += 1
        self.regions += len(regions)
        self.upload_pixels += sum((x2-x1)*(y2-y1) for x1,y1,x2,y2 in regions)

    def close(self):
        if self.fd is None:
            return
        if self.started and self.old and self.old.mode_valid:
            connector = U32(self.connector_id)
            self.lib.drmModeSetCrtc(self.fd,self.old.crtc_id,self.old.buffer_id,self.old.x,self.old.y,C.byref(connector),1,C.byref(self.old.mode))
        if self.framebuffer.value:
            self.lib.drmModeRmFB(self.fd,self.framebuffer)
        self.pixels = None
        if self.mapping:
            self.mapping.close()
        if self.handle:
            fcntl.ioctl(self.fd,0xc00464b4,struct.pack('=I',self.handle))
        self.lib.drmDropMaster(self.fd)
        os.close(self.fd)
        self.fd = None
        if self.tty is not None:
            fcntl.ioctl(self.tty,0x4b3a,0) # KD_TEXT
            os.close(self.tty)
            self.tty = None

if __name__ == '__main__':
    display = NativeDisplay(probe_only=True)
    print('Read-only probe:',display.mode.hdisplay,display.mode.vdisplay,'connector',display.connector_id,'CRTC',display.crtc_id)
    display.close()
