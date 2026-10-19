"""Green phosphor scope for a 480x320 SPI display. No extra dependencies."""
import math
from pathlib import Path
import time
from resolution_canvas import pygame
from providers import provider
from motion import Motion
from coastline import Coastline
from flag_icons import FlagIcons
from airline_icons import AirlineIcons
from split_flap import SplitFlap
from ui_contrast import contrast_level, contrast_color, cloud_contrast
from aircraft_details import altitude, speed, distance, direction, registration_country

SIZE = (480, 320)
CENTRE = (158, 160)
RADIUS = 140
INK = (183, 255, 180)
GREEN = (80, 244, 117)
MUTED = (83, 151, 98)
DIM = (35, 85, 49)


def polar(angle, radius, centre=CENTRE):
    return (int(centre[0] + math.sin(angle) * radius), int(centre[1] - math.cos(angle) * radius))


class RadarView:
    def __init__(self, screen):
        self.screen = screen
        self.contrast = 0
        self.flags = FlagIcons(screen)
        self.airlines = AirlineIcons(screen)
        self.flaps = SplitFlap()
        self.extra_width = max(0, screen.get_width()-480)
        self.fonts = {}
        for size in (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 25):
            path = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
            self.fonts[size] = pygame.font.Font(path if Path(path).exists() else None, size)
        self.buttons = {'range': pygame.Rect(324, 246, 148, 29), 'location': pygame.Rect(324, 279, 66, 33), 'next': pygame.Rect(397, 279, 75, 33)}
        self.buttons['range'].width += self.extra_width
        self.buttons['location'].width += self.extra_width//2
        self.buttons['next'].x += self.extra_width//2
        self.buttons['next'].width += self.extra_width-self.extra_width//2
        self.hits = []
        self.text_cache = {}
        self.coastline = Coastline()
        self.map_key = None
        self.clouds = None
        self.weather = None
        self.cloud_image = None
        self.cloud_token = None
        self.base = self.build_base()
        # Keep the soft sweep at design density: 144 native frames would
        # consume hundreds of MB on larger panels. Text/geometry stay native.
        from resolution_canvas import configure
        density = getattr(screen, 'density', 1)
        configure(1)
        self.sweep = self.build_sweep()
        configure(density)
        # Crop transparent sweep margins and cache display-ready frames.
        # A 64 MiB cap keeps large-panel installations within Pi memory limits.
        from resolution_canvas import sweep_frames
        self.sweep_frames = sweep_frames(self.sweep, density)
        self.halos = {}
        self.trails = {}
        self.motion = Motion()
        self.last_received = None
        self.last_centre = None

    def set_contrast(self,cfg):
        level=contrast_level(cfg)
        if level != self.contrast:
            self.contrast=level
            self.map_key=None
            self.text_cache.clear()

    def color(self,value):
        return contrast_color(self.contrast,value)

    def label(self, text, x, y, size=12, color=INK, width=None, surface=None):
        target = surface or self.screen
        value = str(text)
        if width is not None and self.fonts[size].size(value)[0] > width:
            while value and self.fonts[size].size(value + '..')[0] > width:
                value = value[:-1]
            value += '..'
        rendered = self.text_surface(value, size, color)
        target.blit(rendered, (x, y))
        return rendered.get_width()

    def text_surface(self, value, size, color):
        color = self.color(color)
        # Reuse unchanged labels instead of rasterizing them every animation frame.
        key = (value, size, color)
        if key not in self.text_cache:
            if len(self.text_cache) >= 256:
                self.text_cache.clear()
            self.text_cache[key] = self.fonts[size].render(value, True, color)
        return self.text_cache[key]

    def build_base(self, cfg=None):
        base = pygame.Surface(self.screen.get_size()).convert()
        base.fill(self.color((3,15,7)))
        for y in range(320):
            c = int(4 + 5 * (1 - y / 320))
            pygame.draw.line(base, self.color((c // 2, c + 4, c // 2)), (0, y), (self.screen.get_width(), y))
        # Machined ring, inner shadow, and curved phosphor glass.
        pygame.draw.circle(base, self.color((0, 3, 0)), (160, 163), 158)
        for radius in range(156, 142, -1):
            shade = int(22 + 39 * math.sin((156 - radius) / 14 * math.pi))
            pygame.draw.circle(base, (shade // 3, shade, shade // 2), CENTRE, radius)
        pygame.draw.circle(base, self.color((1, 8, 3)), CENTRE, 143)
        for radius in range(142, 0, -1):
            f = 1 - radius / 143
            pygame.draw.circle(base, self.color((2 + int(f * 2), 17 + int(f * 13), 7 + int(f * 4))), CENTRE, radius)
        pygame.gfxdraw.aacircle(base, *CENTRE, 156, (60, 115, 63))
        pygame.gfxdraw.aacircle(base, *CENTRE, 143, (10, 50, 22))
        if self.cloud_image is not None:
            base.blit(self.cloud_image,(CENTRE[0]-RADIUS,CENTRE[1]-RADIUS))
        # Glass reflection clipped inside the scope.
        glass = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for i in range(28):
            pygame.draw.arc(glass, (134, 255, 155, max(0, 14 - i // 2)), (23+i, 23+i, 270-2*i, 270-2*i), .42, 2.9, 1)
        base.blit(glass, (0, 0))
        for fraction in (.25, .5, .75, 1):
            pygame.gfxdraw.aacircle(base, *CENTRE, int(RADIUS * fraction), (25, 70, 39))
        for degrees in range(0, 360, 30):
            angle = math.radians(degrees)
            pygame.draw.line(base, self.color((14, 49, 27)), CENTRE, polar(angle, RADIUS))
        for degrees in range(0, 360, 5):
            angle = math.radians(degrees)
            major = degrees % 30 == 0
            pygame.draw.aaline(base, self.color((93, 149, 92)) if major else (40, 90, 48), polar(angle, 148 if major else 151), polar(angle, 154))
        for name, angle in (('N', 0), ('E', 90), ('S', 180), ('W', 270)):
            x, y = polar(math.radians(angle), 130)
            self.label(name, x - 4, y - 7, 12, (101, 179, 111), surface=base)
        for x, y in ((6, 6), (306, 6), (6, 308), (306, 308)):
            pygame.draw.circle(base, self.color((0, 5, 1)), (x+1, y+1), 4)
            pygame.draw.circle(base, self.color((41, 67, 39)), (x, y), 3)
            pygame.draw.line(base, self.color((9, 22, 10)), (x-2, y), (x+2, y))
        # Thin scan lines give the glass subtle texture.
        for y in range(24, 299, 3):
            dy = y - CENTRE[1]
            dx = int(math.sqrt(max(0, RADIUS**2 - dy**2)))
            if dx:
                pygame.draw.line(base, self.color((3, 16, 6)), (CENTRE[0]-dx, y), (CENTRE[0]+dx, y))
        # Keep the shoreline continuous above clouds and decorative scan lines.
        if cfg is not None:
            self.coastline.draw(base,cfg,CENTRE,RADIUS,color=self.color((39,111,66)),outline=bool(self.cloud_image is not None and self.contrast))
        return base

    def build_sweep(self):
        size = RADIUS * 2 + 4
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (size // 2, size // 2)
        # The leading ray is north. Rotating the cached wedge is cheap at this size.
        for degrees in range(-52, 0):
            strength = ((degrees + 52) / 52) ** 2
            a, b = math.radians(degrees), math.radians(degrees + 1.5)
            pygame.draw.polygon(surface, (51, 242, 85, int(56 * strength)), [centre, polar(a, RADIUS-1, centre), polar(b, RADIUS-1, centre)])
        pygame.draw.line(surface, (85, 255, 115, 110), centre, polar(0, RADIUS-1, centre), 3)
        pygame.draw.aaline(surface, (163, 255, 181, 200), centre, polar(0, RADIUS-1, centre))
        return surface

    def halo(self, radius, strength):
        key = radius, strength
        if key not in self.halos:
            surface = pygame.Surface((radius*2+2, radius*2+2), pygame.SRCALPHA)
            for r in range(radius, 0, -1):
                alpha = int(strength * (1-r/(radius+1))**2)
                pygame.draw.circle(surface, (66, 255, 91, alpha), (radius+1, radius+1), r)
            self.halos[key] = surface
        return self.halos[key]

    def plane(self, x, y, heading, selected):
        halo = self.halo(18 if selected else 11, 170 if selected else 100)
        self.screen.blit(halo, halo.get_rect(center=(x, y)))
        angle = math.radians(heading)
        silhouette = ((0,-7),(1,-2),(7,2),(7,4),(1,2),(1,6),(3,8),(3,9),(0,7),(-3,9),(-3,8),(-1,6),(-1,2),(-7,4),(-7,2),(-1,-2))
        points = [(x + px*math.cos(angle) - py*math.sin(angle), y + px*math.sin(angle) + py*math.cos(angle)) for px,py in silhouette]
        pygame.draw.polygon(self.screen, self.color((0, 7, 1)), [(px+1, py+2) for px,py in points])
        color = INK if selected else (65, 210, 97)
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.aalines(self.screen, color, True, points)
        if selected:
            for dx,dy in ((-1,-1),(1,-1),(-1,1),(1,1)):
                corner = (int(x+dx*12), int(y+dy*12))
                pygame.draw.line(self.screen, GREEN, corner, (corner[0]-dx*5,corner[1]))
                pygame.draw.line(self.screen, GREEN, corner, (corner[0],corner[1]-dy*5))

    def button(self, rect, title, subtitle=None):
        pygame.draw.rect(self.screen, self.color((0, 4, 1)), rect.move(0,2), border_radius=6)
        pygame.draw.rect(self.screen, self.color((16, 49, 25)), rect, border_radius=6)
        pygame.draw.rect(self.screen, self.color((43, 99, 52)), rect, 1, border_radius=6)
        pygame.draw.line(self.screen, self.color((63, 119, 63)), (rect.left+7,rect.top+1),(rect.right-7,rect.top+1))
        label = self.text_surface(title, 12, INK)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def draw(self, cfg, rows, current, age, error, note, received, elapsed, display_status=None):
        self.set_contrast(cfg)
        cloud,cloud_note = self.clouds.snapshot(cfg) if self.clouds else (None,'CLOUDS OFF')
        token = (cloud['key'],cloud['timestamp'],self.contrast) if cloud else None
        if token != self.cloud_token:
            self.cloud_image = pygame.image.frombytes(cloud_contrast(cloud['rgba'],self.contrast),(280,280),'RGBA') if cloud else None
            self.cloud_token = token
        map_key = (cfg['latitude'],cfg['longitude'],cfg['radius_km'],token)
        if self.map_key != map_key:
            self.base = self.build_base(cfg)
            self.map_key = map_key
        self.screen.blit(self.base, (0,0))
        sweep_angle = (elapsed * 30) % 360
        sweep, offset = self.sweep_frames[round(sweep_angle/2.5) % len(self.sweep_frames)]
        self.screen.blit(sweep, (CENTRE[0]+offset[0],CENTRE[1]+offset[1]))
        for fraction in (.25,.5,.75):
            self.label(distance(cfg['radius_km']*fraction,cfg,with_unit=False), CENTRE[0]+4, CENTRE[1]-int(RADIUS*fraction)+2, 9, DIM)
        pygame.draw.circle(self.screen, self.color((58, 157, 76)), CENTRE, 5, 1)
        pygame.draw.circle(self.screen, INK, CENTRE, 2)

        # Trails retain reported positions; prediction affects icons only.
        centre_key = (cfg['latitude'], cfg['longitude'], cfg['radius_km'], cfg.get('data_provider'))
        if centre_key != self.last_centre:
            self.trails.clear()
            self.motion = Motion()
            self.last_centre = centre_key
        if received != self.last_received:
            active = {a.get('hex') for a in rows}
            self.trails = {k:v for k,v in self.trails.items() if k in active}
            for a in rows:
                pos = polar(a['bearing'], a['distance']/cfg['radius_km']*RADIUS)
                trail = self.trails.setdefault(a.get('hex'), [])
                if not trail or trail[-1] != pos:
                    trail.append(pos)
                    del trail[:-6]
            self.last_received = received
        self.motion.retain(rows)
        motion_now = time.monotonic()
        self.hits = []
        selected_pos = None
        for a in reversed(rows):
            ident = a.get('hex')
            trail = self.trails.get(ident, [])
            for i in range(1, len(trail)):
                pygame.draw.aaline(self.screen, (16, 40+i*14, 25+i*5), trail[i-1], trail[i])
            east,north = self.motion.position(a, received, age, motion_now, frozen=bool(error) or display_status == 'REPLAY')
            if math.hypot(east,north) > cfg['radius_km']:
                continue
            x,y = CENTRE[0]+east/cfg['radius_km']*RADIUS, CENTRE[1]-north/cfg['radius_km']*RADIUS
            selected = current is not None and ident == current.get('hex')
            try:
                heading = float(a.get('track') or 0)
                if not math.isfinite(heading):
                    heading = 0
            except (TypeError, ValueError):
                heading = 0
            self.plane(x, y, heading, selected)
            mode = cfg.get('callsign_labels', 'selected')
            if mode == 'all' or (mode == 'selected' and selected):
                callsign = str(a.get('flight') or a.get('hex') or '?').strip()
                self.label(callsign, max(20,min(231,int(x)+13)), max(22,min(278,int(y)-20)), 10, INK if selected else MUTED, 76)
            self.hits.append((pygame.Rect(x-15,y-15,30,30),ident))
            if selected:
                selected_pos = x,y

        if self.weather:
            temperature,conditions = self.weather.snapshot(cfg)
            self.label(temperature,max(225,300-self.fonts[17].size(temperature)[0]),14,17,INK,75)
            weather_text = self.text_surface(conditions,9,MUTED)
            self.screen.blit(weather_text,(max(201,300-weather_text.get_width()),2))
        extra = self.extra_width
        local_now = time.localtime()
        self.label((cfg.get('location_label') or cfg.get('location_name') or 'PIN LOCATION').upper(),14,4,11,INK,84)
        self.label(time.strftime('%H:%M:%S', local_now),324,0,25,INK,122+extra)
        self.label(time.strftime('%Z', local_now),448+extra,16,9,MUTED,24)
        self.label(time.strftime('%a %d %b %Y', local_now).upper(),325,30,11,MUTED,147+extra)
        status = display_status or ('CONNECTING' if age is None and not error else ('OFFLINE' if error else ('STALE' if age > cfg['stale_seconds'] else 'LIVE')))
        pygame.draw.circle(self.screen, GREEN if status == 'LIVE' else MUTED, (329,54), 3)
        self.label(status, 339,46,11,GREEN)
        self.label(f'{len(rows):02} TRACKS', 405+extra,47,10,MUTED)
        self.label(f'UPDATED {max(0,int(age))}s AGO' if age is not None else 'WAITING FOR DATA',325,65,10,MUTED,147+extra)

        self.label(cloud['source'] if cloud else cloud_note,325,77,9,DIM,147+extra)

        # Flight balloon sits clear of the maximised scope; its leader names the target.
        balloon = pygame.Rect(324, 87, 148+extra, 141)
        if selected_pos:
            x,y = selected_pos
            pygame.draw.lines(self.screen, self.color((0,8,2)), False, [(x+13,y+2),(309,y+2),(320,126),(326,126)],3)
            pygame.draw.aalines(self.screen, self.color((58,137,76)), False, [(x+13,y),(309,y),(320,124),(325,124)])
            pygame.draw.circle(self.screen, GREEN, (x+13,y), 2)
        pygame.draw.rect(self.screen, self.color((0,3,0)), balloon.move(2,4), border_radius=8)
        pygame.draw.polygon(self.screen, self.color((42,94,49)), [(324,115),(316,123),(324,132)])
        pygame.draw.rect(self.screen, self.color((17,51,26)), balloon, border_radius=8)
        pygame.draw.rect(self.screen, self.color((55,112,64)), balloon, 1, border_radius=8)
        pygame.draw.line(self.screen, self.color((90,147,92)), (332,88),(462+extra,88))
        pygame.draw.line(self.screen, self.color((8,25,12)), (331,225),(465+extra,225))
        if current:
            callsign = (current.get('flight') or current.get('hex') or '?').strip()
            logo = self.airlines.get(current.get('flight'))
            compact = self.screen.get_width()<=480 and logo is not None
            flag = self.flags.get(current.get('hex'),(18,12) if compact else (24,16))
            icons = [icon for icon in (flag,logo) if icon is not None]
            gap = 4 if compact else 6
            available = 127+extra - sum(icon.get_width()+gap for icon in icons)
            font_size = 19
            if compact:
                while font_size>15 and self.fonts[font_size].size(callsign)[0]>available:
                    font_size -= 1
            title = callsign
            if self.fonts[font_size].size(title)[0] > available:
                while title and self.fonts[font_size].size(title+'..')[0] > available:
                    title = title[:-1]
                title += '..'
            self.flaps.draw(self.screen,self.fonts[font_size],title,334,94+(19-font_size)/2,self.color(INK),'callsign',current.get('hex'),width=available)
            icon_x = 334+self.fonts[font_size].size(title)[0]
            for icon in icons:
                icon_x += gap
                self.screen.blit(icon,(icon_x,97+(18-icon.get_height())/2))
                icon_x += icon.get_width()
            self.label(f'{current.get("t", "?")} {current.get("r", "")}',334,119,10,MUTED,127+extra)
            route = current.get('route_label') or ''
            route = route if ' > ' in route else '---------'
            self.flaps.draw(self.screen,self.fonts[17],route,334,135,self.color(GREEN),'route',current.get('hex'),width=127+extra,clear_on_identity=True)
            self.label('REG: '+registration_country(current.get('hex')),334,155,9,MUTED,127+extra)
            altitude_text, altitude_unit = altitude(current.get('alt_baro'),cfg)
            self.label(altitude_text,334,168,19,INK,106+extra)
            if altitude_unit:
                altitude_width = min(self.fonts[19].size(altitude_text)[0],106+extra)
                self.label(altitude_unit,334+altitude_width+6,175,10,MUTED)
            self.label(speed(current.get('gs'),cfg),334,193,10,GREEN,76+extra)
            self.label(distance(current['distance'],cfg),414+extra,193,10,GREEN,58)
            self.label(direction(current),334,212,10,MUTED,127+extra)
        else:
            self.flaps.clear()
            self.label('ACQUIRING' if age is None else 'NO TARGETS',334,106,14,INK)
            self.label('Waiting for' if age is None else 'No recent',334,142,12,MUTED)
            self.label('live positions' if age is None else 'positions here',334,159,12,MUTED)
        detail = error or (note if note.startswith('IP failed') else '') or (cloud_note if self.clouds and cfg.get('cloud_overlay',True) else 'MOTION EST. / 30s MAX')
        if status == 'REPLAY':
            detail = 'DATA PAUSED / TEST'
        if self.clouds and cfg.get('cloud_overlay',True):
            detail = cloud_note
        self.label(detail,325,232,9,MUTED,147+extra)
        self.button(self.buttons['range'],'RANGE  '+distance(cfg['radius_km'],cfg))
        self.button(self.buttons['location'],'SETUP')
        self.button(self.buttons['next'],'NEXT >')
        # Tiny attribution occupies an unused outer corner, outside the radar glass.
        self.label(provider(cfg)['name'],6,291,9,MUTED)
        self.label(provider(cfg)['credit'],6,303,9,DIM)
        if self.weather:
            self.label('Open-Meteo',248,303,9,DIM,60)
        return status

    def hit(self, pos):
        for name,rect in self.buttons.items():
            if rect.collidepoint(pos):
                return name, None
        matches = [(math.hypot(rect.centerx-pos[0],rect.centery-pos[1]),ident) for rect,ident in self.hits if rect.collidepoint(pos)]
        if matches:
            return 'select', min(matches)[1]
        return None, None
