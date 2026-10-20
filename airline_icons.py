# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Optional offline logos inferred from an ICAO airline callsign prefix."""
import io
from pathlib import Path
import re
import zipfile
import pygame

def airline_code(callsign):
    value = str(callsign or '').strip().upper()
    # Do not treat registrations, bare codes or arbitrary text as flight numbers.
    return value[:3] if re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}', value) else None

class AirlineIcons:
    def __init__(self, screen):
        self.density = getattr(screen,'density',1)
        self.canvas = hasattr(screen,'density')
        self.width = 36 if screen.get_width()>480 else 26
        self.height = 18
        self.path = Path(__file__).with_name('airline-logos.zip')
        self.cache = {}
        try:
            with zipfile.ZipFile(self.path) as archive:
                self.files = set(archive.namelist())
        except (OSError,zipfile.BadZipFile):
            self.files = set()

    def get(self,callsign):
        code = airline_code(callsign)
        if not code or code+'.png' not in self.files:
            return None
        if code not in self.cache:
            if len(self.cache)>=64:
                self.cache.clear()
            try:
                with zipfile.ZipFile(self.path) as archive:
                    source = pygame.image.load(io.BytesIO(archive.read(code+'.png'))).convert_alpha()
                w,h = round(self.width*self.density),round(self.height*self.density)
                pad = max(1,round(2*self.density))
                factor = min((w-2*pad)/source.get_width(),(h-2*pad)/source.get_height())
                size = tuple(max(1,round(v*factor)) for v in source.get_size())
                logo = pygame.transform.smoothscale(source,size)
                chip = pygame.Surface((w,h),pygame.SRCALPHA)
                pygame.draw.rect(chip,(245,245,245),chip.get_rect(),border_radius=max(1,round(2*self.density)))
                chip.blit(logo,((w-size[0])//2,(h-size[1])//2))
                if self.canvas:
                    from resolution_canvas import Canvas
                    chip = Canvas((self.width,self.height),density=self.density,source=chip)
                self.cache[code] = chip
            except (OSError,ValueError,KeyError,zipfile.BadZipFile,pygame.error):
                self.cache[code] = None
        return self.cache[code]
