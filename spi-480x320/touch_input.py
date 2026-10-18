"""Read the ADS7846 legacy evdev stream and calibrate directly to UI pixels."""
import json
import os
from pathlib import Path
import statistics
import struct

EVENT = struct.Struct('@llHHi')


def solve_affine(raw, target):
    def solve(values):
        a = [[float(x),float(y),1.0,float(v)] for (x,y),v in zip(raw,values)]
        for i in range(3):
            pivot = max(range(i,3),key=lambda j:abs(a[j][i]))
            a[i],a[pivot] = a[pivot],a[i]
            if abs(a[i][i]) < 1e-8:
                raise ValueError('Taps were too close together. Try again.')
            divisor = a[i][i]
            a[i] = [v/divisor for v in a[i]]
            for j in range(3):
                if j != i:
                    factor = a[j][i]
                    a[j] = [v-factor*w for v,w in zip(a[j],a[i])]
        return [row[3] for row in a]
    return solve([p[0] for p in target])+solve([p[1] for p in target])


def mapped(point, matrix):
    x,y = point
    a,b,c,d,e,f = matrix
    return round(a*x+b*y+c),round(d*x+e*y+f)


class RawTouch:
    def __init__(self,path):
        self.path = Path(path)
        self.matrix = None
        if self.path.exists():
            try:
                self.matrix = json.loads(self.path.read_text())['matrix']
                if len(self.matrix) != 6:
                    self.matrix = None
            except (OSError,ValueError,KeyError,TypeError):
                pass
        self.fd = None
        for node in Path('/sys/class/input').glob('event*'):
            if (node/'device/name').read_text().strip() == 'ADS7846 Touchscreen':
                self.fd = os.open('/dev/input/'+node.name,os.O_RDONLY|os.O_NONBLOCK)
                break
        if self.fd is None:
            raise RuntimeError('ADS7846 touchscreen not found')
        self.x = self.y = None
        self.down = False
        self.released = False
        self.samples = []
        self.pending = b''

    def poll(self):
        taps = []
        while True:
            try:
                data = os.read(self.fd,EVENT.size*64)
            except BlockingIOError:
                break
            if not data:
                break
            self.pending += data
            while len(self.pending) >= EVENT.size:
                _,_,typ,code,value = EVENT.unpack(self.pending[:EVENT.size])
                self.pending = self.pending[EVENT.size:]
                if typ == 3 and code == 0:
                    self.x = value
                elif typ == 3 and code == 1:
                    self.y = value
                elif typ == 1 and code == 330:
                    if value:
                        self.down = True
                        self.samples = []
                    else:
                        self.down = False
                        self.released = True
                elif typ == 0 and code == 3:  # SYN_DROPPED: ignore partial gesture.
                    self.samples = []
                    self.down = self.released = False
                    self.x = self.y = None
                elif typ == 0 and code == 0:
                    if self.down and self.x is not None and self.y is not None:
                        self.samples.append((self.x,self.y))
                        self.samples = self.samples[-9:]
                    if self.released:
                        if self.samples:
                            taps.append(tuple(statistics.median(p[i] for p in self.samples) for i in (0,1)))
                        self.samples = []
                        self.released = False
        return taps

    def save(self,matrix):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'matrix':matrix},indent=2)+'\n')
        temp.replace(self.path)
        self.matrix = matrix


class Calibration:
    targets = [(40,45),(440,45),(240,275),(240,160)]
    def __init__(self,touch):
        self.touch = touch
        self.points = []
        self.matrix = None
        self.done = False
        self.message = 'Tap each target with the stylus, then lift.'

    def tap(self,raw):
        self.points.append(raw)
        if len(self.points) == 3:
            try:
                self.matrix = solve_affine(self.points,self.targets[:3])
            except ValueError as error:
                self.points = []
                self.message = str(error)
        elif len(self.points) == 4:
            x,y = mapped(raw,self.matrix)
            if abs(x-240) <= 25 and abs(y-160) <= 25:
                self.touch.save(self.matrix)
                self.done = True
            else:
                self.points = []
                self.message = 'Accuracy check failed. Tap the targets again.'

    def draw(self,screen,view):
        import pygame
        screen.fill((3,15,7))
        view.label('TOUCH SETUP',145,88,21)
        view.label(self.message,16,119,12,width=449)
        view.label(f'Target {len(self.points)+1} of 4',166,205,14)
        x,y = self.targets[min(3,len(self.points))]
        pygame.draw.circle(screen,(93,255,121),(x,y),16,2)
        pygame.draw.line(screen,(200,255,200),(x-23,y),(x+23,y),2)
        pygame.draw.line(screen,(200,255,200),(x,y-23),(x,y+23),2)
