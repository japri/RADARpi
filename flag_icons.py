"""Offline registration-country flags, cached at the display's pixel density."""
import io
import json
from pathlib import Path
import zipfile
import pygame
from aircraft_details import registration_country

class FlagIcons:
    def __init__(self, screen):
        self.density = getattr(screen, 'density', 1)
        self.canvas = hasattr(screen, 'density')
        self.cache = {}
        try:
            # Read the small archive once; no persistent file handle or network.
            self.archive = Path(__file__).with_name('flags.zip').read_bytes()
            with zipfile.ZipFile(io.BytesIO(self.archive)) as z:
                self.codes = json.loads(z.read('countries.json'))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            self.archive, self.codes = b'', {}

    def get(self, hex_id):
        code = self.codes.get(registration_country(hex_id))
        if not code:
            return None
        if code not in self.cache:
            try:
                with zipfile.ZipFile(io.BytesIO(self.archive)) as z:
                    source = pygame.image.load(io.BytesIO(z.read(code+'.png'))).convert_alpha()
                ratio = min(24*self.density/source.get_width(),16*self.density/source.get_height())
                size = tuple(max(1,round(v*ratio)) for v in source.get_size())
                result = pygame.transform.smoothscale(source,size)
                if self.canvas:
                    from resolution_canvas import Canvas
                    result = Canvas(tuple(v/self.density for v in size),density=self.density,source=result)
                self.cache[code] = result
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, pygame.error):
                self.cache[code] = None
        return self.cache[code]
