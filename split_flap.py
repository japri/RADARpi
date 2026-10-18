"""Mechanical, frame-driven split-flap transitions; no sleeps, threads or network."""
from collections import OrderedDict
from dataclasses import dataclass
import math
import time

DURATION = .22  # Seconds per mechanical flap, visible even on the SPI panel.
STAGGER = .06
FLAPS = 8
CHARACTERS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789->"

@dataclass
class FlipState:
    target: str = ''
    previous: str = ''
    identity: object = None
    started: float = 0

    def update(self, text, identity, now, clear_on_identity=False):
        if text != self.target or identity != self.identity:
            self.previous = '' if clear_on_identity and identity != self.identity else self.target
            self.target, self.identity, self.started = text, identity, now

    def cell(self, index, now):
        old = self.previous[index] if index < len(self.previous) else ' '
        new = self.target[index]
        if old == new:
            return old,new,1
        elapsed = now-self.started-min(index,8)*STAGGER
        steps = FLAPS+index%4
        if elapsed <= 0:
            return old,old,0
        if elapsed >= steps*DURATION:
            return new,new,1
        step = int(elapsed/DURATION)
        phase = (elapsed-step*DURATION)/DURATION
        end = CHARACTERS.find(new)
        if end < 0:
            end = 0
        def character(position):
            if position == 0:
                return old
            if position == steps:
                return new
            return CHARACTERS[(end-steps+position)%len(CHARACTERS)]
        return character(step),character(step+1),phase

class SplitFlap:
    def __init__(self):
        self.fields = {}
        self.tiles = OrderedDict()
        self.labels = {}

    def clear(self, key=None):
        if key is None:
            self.fields.clear()
            self.labels.clear()
        else:
            self.fields.pop(key,None)
            self.labels.pop(key,None)

    def tile(self, font, char, color, width, height):
        import pygame
        key = (font,char,color,width,height)
        if key not in self.tiles:
            tile = pygame.Surface((width,height))
            tile.fill((7,22,12))
            tile.blit(font.render(char,True,color),(0,0))
            self.tiles[key] = tile
            if len(self.tiles)>192:
                self.tiles.popitem(last=False)
        self.tiles.move_to_end(key)
        return self.tiles[key]

    def draw(self, screen, font, text, x, y, color, key, identity, width=None,
             now=None, clear_on_identity=False):
        import pygame
        now = time.monotonic() if now is None else now
        density = getattr(screen,'density',1)
        target = getattr(screen,'pixels',screen)
        native_font = getattr(font,'font',font)
        text = str(text)
        signature = (native_font,text,color,width,density)
        cached = self.labels.get(key)
        if cached is None or cached['signature'] != signature:
            if width is not None and native_font.size(text)[0] > width*density:
                while text and native_font.size(text+'..')[0] > width*density:
                    text=text[:-1]
                text+='..'
            edges = [native_font.size(text[:i])[0] for i in range(len(text)+1)]
            height = native_font.get_height()
            cached = dict(signature=signature,text=text,edges=edges,
                          surface=pygame.Surface((max(1,edges[-1]),height)),frame=None)
            self.labels[key] = cached
        text = cached['text']
        state = self.fields.setdefault(key,FlipState())
        state.update(text,identity,now,clear_on_identity)
        cells = [state.cell(i,now) for i in range(len(text))]
        # Finished boards become one blit. Active boards retain frame-driven timing.
        frame = tuple(cells)
        output = target
        dest = (round(x*density),round(y*density))
        if cached['frame'] == frame:
            output.blit(cached['surface'],dest, (0,0,round(width*density),cached['surface'].get_height()) if width is not None else None)
            return
        target = cached['surface']
        target.fill((7,22,12))
        height = target.get_height()
        half = height//2
        px=py=0
        for index,char in enumerate(text):
            # Prefix metrics retain the exact label width and icon spacing.
            left = cached['edges'][index]
            right = cached['edges'][index+1]
            cell_width = max(1,right-left)
            old,new,phase = cells[index]
            new_tile = self.tile(native_font,new,color,cell_width,height)
            dest = (px+left,py)
            if phase>=1:
                target.blit(new_tile,dest)
            else:
                old_tile = self.tile(native_font,old,color,cell_width,height)
                if phase<=0:
                    target.blit(old_tile,dest)
                else:
                    target.blit(new_tile,dest,(0,0,cell_width,half))
                    target.blit(old_tile,(dest[0],py+half),(0,half,cell_width,height-half))
                    if phase<.5:
                        flap = old_tile.subsurface((0,0,cell_width,half))
                        flap_height = round(half*math.cos(math.pi*phase))
                        flap_y = py+half-flap_height
                    else:
                        flap = new_tile.subsurface((0,half,cell_width,height-half))
                        flap_height = round((height-half)*math.sin(math.pi*(phase-.5)))
                        flap_y = py+half
                    if flap_height>0:
                        folded = pygame.transform.smoothscale(flap,(cell_width,flap_height))
                        shade = round(255*(.55+.45*abs(math.cos(math.pi*phase))))
                        folded.fill((shade,shade,shade),special_flags=pygame.BLEND_RGB_MULT)
                        target.blit(folded,(dest[0],flap_y))
            # Fine hinge and cell boundaries suggest a mechanical board.
            pygame.draw.line(target,(10,32,17),(px+left,py+half),(px+right-1,py+half))
            pygame.draw.line(target,(12,32,18),(px+right-1,py),(px+right-1,py+height-1))
        cached['frame'] = frame
        output.blit(target,(round(x*density),round(y*density)), (0,0,round(width*density),height) if width is not None else None)
