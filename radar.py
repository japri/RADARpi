#!/usr/bin/env python3
"""Small internet flight radar. Python stdlib + system pygame only."""
import argparse
import email.utils
import json
import math
import os
import sys
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from providers import provider_id, position_url, poll_seconds

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'JakartaDeskRadar/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def relative_position(lat, lon, centre_lat, centre_lon):
    """Great circle distance in km and initial bearing clockwise from north."""
    a, b = math.radians(centre_lat), math.radians(lat)
    dl = math.radians(lon - centre_lon)
    da = b - a
    h = math.sin(da / 2)**2 + math.cos(a) * math.cos(b) * math.sin(dl / 2)**2
    distance = 6371.0 * 2 * math.asin(math.sqrt(min(1, max(0, h))))
    bearing = math.atan2(math.sin(dl) * math.cos(b), math.cos(a) * math.sin(b) - math.sin(a) * math.cos(b) * math.cos(dl))
    return distance, bearing


def aircraft_rows(data, cfg):
    if not isinstance(data, dict) or not isinstance(data.get('ac'), list):
        raise ValueError('Invalid aircraft response')
    rows = []
    for item in data['ac']:
        try:
            lat, lon = float(item['lat']), float(item['lon'])
            age = float(item.get('seen_pos', 9999))
            if not all(math.isfinite(v) for v in (lat, lon, age)) or age > 90 or age < 0:
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            distance, bearing = relative_position(lat, lon, cfg['latitude'], cfg['longitude'])
            if distance <= cfg['radius_km']:
                rows.append(dict(item, distance=distance, bearing=bearing, position_age=age))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(rows, key=lambda item: item['distance'])


def retry_delay(error, failures):
    delay = min(900, 30 * 2 ** min(failures, 5))
    if isinstance(error, urllib.error.HTTPError):
        retry = error.headers.get('Retry-After')
        if retry:
            try:
                delay = max(delay, float(retry))
            except ValueError:
                try:
                    delay = max(delay, email.utils.parsedate_to_datetime(retry).timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
    return delay


class Feed:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.rows = []
        self.received = None
        self.error = ''
        self.location_note = 'Manual centre'
        self.revision = 0
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.reconnect = threading.Event()
        self.diagnostic_pause_until = 0

    def save(self):
        temp = CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(self.cfg, indent=2) + '\n')
        temp.replace(CONFIG)

    def change(self, **values):
        with self.lock:
            reset = any(key in ('latitude','longitude','radius_km','data_provider','location_mode') and self.cfg.get(key) != value for key,value in values.items())
            self.cfg.update(values)
            if reset:
                self.revision += 1
                self.rows = []
                self.received = None
                self.error = ''
            self.save()
        self.wake.set()

    def run(self):
        ip_checked = False
        provider_states = {}
        while not self.stop.is_set():
            self.wake.clear()
            pause_remaining = self.diagnostic_pause_until - time.monotonic()
            if pause_remaining > 0:
                self.wake.wait(min(1, pause_remaining))
                continue
            with self.lock:
                cfg, revision = dict(self.cfg), self.revision
            state = provider_states.setdefault(provider_id(cfg),dict(failures=0,next_allowed=0,connection_failed=False,last_completed=None))
            if not state['failures'] and state['last_completed'] is not None:
                state['next_allowed'] = state['last_completed'] + poll_seconds(cfg)
            if self.reconnect.is_set():
                self.reconnect.clear()
                if state['connection_failed']:
                    state['next_allowed'] = 0
            if cfg.get('location_mode') == 'ip' and not ip_checked:
                try:
                    geo = get_json('https://ipwho.is/')
                    lat, lon = float(geo['latitude']), float(geo['longitude'])
                    if not geo.get('success') or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError('Invalid location')
                    with self.lock:
                        if revision == self.revision:
                            self.cfg.update(latitude=lat, longitude=lon, location_name=geo.get('city') or 'IP location')
                            cfg = dict(self.cfg)
                            self.location_note = 'Approximate IP location'
                            self.save()
                except Exception:
                    with self.lock:
                        self.location_note = 'IP failed; saved centre'
                ip_checked = True
            elif cfg.get('location_mode') != 'ip':
                ip_checked = False
                with self.lock:
                    self.location_note = 'Manual centre'
            remaining = state['next_allowed'] - time.monotonic()
            if remaining > 0:
                self.wake.wait(remaining)
                continue
            try:
                data = get_json(position_url(cfg))
                rows = aircraft_rows(data, cfg)
                with self.lock:
                    if revision == self.revision:
                        self.rows, self.received, self.error = rows, time.monotonic(), ''
                state['failures'] = 0
                state['connection_failed'] = False
                delay = poll_seconds(cfg)
            except Exception as error:
                state['failures'] += 1
                state['connection_failed'] = isinstance(error,(urllib.error.URLError,OSError)) and not isinstance(error,urllib.error.HTTPError)
                with self.lock:
                    if revision == self.revision:
                        self.error = f'HTTP {error.code}' if isinstance(error, urllib.error.HTTPError) else 'Connection lost'
                delay = retry_delay(error, state['failures'])
            state['last_completed'] = time.monotonic()
            state['next_allowed'] = state['last_completed'] + delay
            if revision == self.revision:
                self.wake.wait(delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--screenshot', help='Render one frame to PNG using live data')
    parser.add_argument('--windowed', action='store_true')
    parser.add_argument('--frame-time', type=float, default=2.8, help='Sweep time for screenshot')
    parser.add_argument('--fps', type=int, default=12, help='Animation frame rate')
    parser.add_argument('--benchmark-seconds', type=float, default=0, help='Measure then exit')
    parser.add_argument('--rotate-display', type=int, choices=(0,90,180,270), default=0)
    parser.add_argument('--raw-touch', action='store_true', help='Use explicitly configured ADS7846 resistive touch')
    parser.add_argument('--native-drm', action='store_true', help='Use synchronous RGB565 LCD updates')
    parser.add_argument('--resolution', default=None, help='auto or WIDTHxHEIGHT; panel pixel resolution, not inches')
    args = parser.parse_args()
    from display_settings import load_resolution, parse_resolution
    try:
        chosen_resolution = parse_resolution(args.resolution or load_resolution(ROOT))
    except ValueError as error:
        parser.error(str(error))
    if args.native_drm and chosen_resolution not in (None,(480,320)):
        parser.error('This ILI9486 SPI driver supports 480x320 only')
    if args.screenshot or args.native_drm:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
    if args.native_drm and args.rotate_display != 180:
        parser.error('Native LCD output currently requires --rotate-display 180')
    if args.native_drm:
        def native_failure(kind, value, tb):
            import traceback
            (ROOT/'native-display-error.log').write_text(''.join(traceback.format_exception(kind,value,tb)))
            (ROOT/'native-display.enabled').unlink(missing_ok=True)
        sys.excepthook = native_failure
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    os.environ['SDL_TOUCH_MOUSE_EVENTS'] = '0'
    import pygame
    from radar_ui import RadarView
    cfg = json.loads(CONFIG.read_text())
    feed = Feed(cfg)
    from route_client import RouteClient
    routes = RouteClient()
    threading.Thread(target=feed.run, daemon=True).start()
    pygame.display.init()
    pygame.font.init()
    from display_layout import Viewport
    fullscreen = not (args.windowed or args.screenshot or args.native_drm)
    output = pygame.display.set_mode(chosen_resolution or ((0, 0) if fullscreen else (480, 320)), pygame.FULLSCREEN if fullscreen else 0)
    # Use the panel's full width; height determines the circular radar scale.
    from resolution_canvas import Canvas, configure, layout, pixels, pygame as drawing
    logical_width, density = layout(*output.get_size(), rotation=0 if args.native_drm else args.rotate_display)
    configure(density)
    screen = Canvas((logical_width, 320)).convert()
    viewport = Viewport(*output.get_size(), rotation=args.rotate_display, logical_width=logical_width)
    settings_offset = (logical_width-480)//2
    settings_screen = Canvas((480,320)).convert()
    def show_settings_canvas():
        screen.fill((3,15,7))
        screen.blit(settings_screen,(settings_offset,0))
    native_display = None
    if args.native_drm:
        from native_display import NativeDisplay
        native_display = NativeDisplay()
    def present():
        if native_display:
            native_display.present(pygame.transform.rotate(pixels(screen), args.rotate_display))
        else:
            viewport.render(screen, output)
            pygame.display.flip()
    pygame.display.set_caption('Green Airspace Radar')
    pygame.mouse.set_visible(False)
    screen.fill((3,15,7))
    splash_font = drawing.font.Font(None,34)
    screen.blit(splash_font.render('FLIGHT RADAR',True,(100,255,140)),(140,125))
    screen.blit(drawing.font.Font(None,22).render('Starting...',True,(75,155,100)),(200,168))
    present()
    view = RadarView(screen)
    if not args.screenshot and not args.benchmark_seconds:
        from cloud_client import CloudClient
        view.clouds = CloudClient(ROOT)
        from weather_client import WeatherClient
        view.weather = WeatherClient()
    from network_client import NetworkClient
    from setup_ui import SetupUI
    network = NetworkClient(enabled=not args.screenshot and not args.benchmark_seconds)
    from copy import copy
    settings_view = copy(view)
    settings_view.screen = settings_screen
    setup = SetupUI(settings_screen,settings_view,feed,network,ROOT)
    auto_wifi_opened = False
    previous_connected = None
    touch = calibration = None
    if args.native_drm or args.raw_touch:
        from touch_input import RawTouch, Calibration, mapped
        try:
            touch = RawTouch(ROOT/'touch.json')
            if touch.matrix is None:
                calibration = Calibration(touch)
        except (OSError, RuntimeError) as error:
            print('Touch unavailable:', error, flush=True)
    setup.can_calibrate = touch is not None
    selected, running, rows = None, True, []
    clock = pygame.time.Clock()
    started = time.monotonic()
    last_cycle = started
    frame_times, render_times, present_times = [], [], []
    last_present = None
    from collections import deque
    recent_presentations = deque(maxlen=80)
    diagnostic_snapshot_time = None
    while running:
        now = time.monotonic()
        pause_request = ROOT/'.diagnostic-pause-feed'
        if pause_request.exists():
            try:
                seconds = float(pause_request.read_text())
                seconds = max(0, min(180, seconds)) if math.isfinite(seconds) else 0
                feed.diagnostic_pause_until = now + seconds
                diagnostic_snapshot_time = now if seconds else None
                feed.wake.set()
            except (OSError, ValueError):
                pass
            pause_request.unlink(missing_ok=True)
        diagnostic_paused = now < feed.diagnostic_pause_until
        network.tick()
        connected = network.status['connected']
        if connected and previous_connected is False:
            feed.reconnect.set()
            feed.wake.set()
        previous_connected = connected
        if not auto_wifi_opened and now-started>15 and network.status['connected'] is False:
            setup.open('wifi')
            auto_wifi_opened = True
        events = pygame.event.get()
        if touch:
            for raw in touch.poll():
                if calibration and not calibration.done:
                    calibration.tap(raw)
                else:
                    events.append(pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=mapped(raw,touch.matrix),button=1,calibrated=True))
        if calibration and not calibration.done:
            calibration.draw(settings_screen,settings_view)
            show_settings_canvas()
            present()
            clock.tick(12)
            continue
        for event in events:
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s:
                    setup.open()
                elif event.key == pygame.K_n and rows:
                    ids = [a.get('hex') for a in rows]
                    selected = ids[(ids.index(selected)+1) % len(ids)] if selected in ids else ids[0]
                    last_cycle = now + 20
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                if touch and not getattr(event,'calibrated',False):
                    continue
                physical = (event.x * viewport.width, event.y * viewport.height) if event.type == pygame.FINGERDOWN else event.pos
                pos = (event.pos[0]+settings_offset,event.pos[1]) if getattr(event,'calibrated',False) else viewport.to_logical(physical)
                if pos is None:
                    continue
                if setup.active:
                    if setup.tap((pos[0]-settings_offset,pos[1])) == 'calibrate' and touch:
                        calibration = Calibration(touch)
                    continue
                action, ident = view.hit(pos)
                if action == 'range':
                    setup.open('range')
                elif action == 'location':
                    setup.open()
                elif action == 'next' and rows:
                    ids = [a.get('hex') for a in rows]
                    selected = ids[(ids.index(selected) + 1) % len(ids)] if selected in ids else ids[0]
                    last_cycle = now + 20
                elif action == 'select':
                    selected = ident
                    last_cycle = now + 20
        with feed.lock:
            cfg, all_rows, received, error, note = dict(feed.cfg), list(feed.rows), feed.received, feed.error, feed.location_note
        age = now - received if received is not None else None
        filter_age = max(0, diagnostic_snapshot_time-received) if diagnostic_paused and received is not None else (age or 0)
        rows = [a for a in all_rows if a['position_age'] + filter_age <= cfg['stale_seconds']]
        if now - last_cycle >= 12 and rows:
            ids = [a.get('hex') for a in rows]
            selected = ids[(ids.index(selected) + 1) % len(ids)] if selected in ids else ids[0]
            last_cycle = now
        current = next((a for a in rows if a.get('hex') == selected), rows[0] if rows else None)
        selected = current.get('hex') if current else None
        if current:
            current = dict(current, route_label=routes.lookup(current))
        elapsed = args.frame_time if args.screenshot else now-started
        render_start = time.monotonic()
        if setup.active:
            setup.draw()
            show_settings_canvas()
            status = 'SETUP'
        else:
            status = view.draw(cfg, rows, current, age, error, note, received, elapsed, display_status='REPLAY' if diagnostic_paused else None)
        diagnostic_request = ROOT/'.diagnostic-request'
        if diagnostic_request.exists():
            pygame.image.save(pixels(screen),str(ROOT/'diagnostic-ui.png'))
            viewport.render(screen, output)
            pygame.image.save(output,str(ROOT/'diagnostic-display.png'))
            (ROOT/'diagnostic-status.json').write_text(json.dumps({'backend':pygame.display.get_driver(),'display_size':output.get_size(),'render_size':pixels(screen).get_size(),'render_density':density,'observed_fps':round((len(recent_presentations)-1)/(recent_presentations[-1]-recent_presentations[0]),1) if len(recent_presentations)>1 else None,'viewport':viewport.rect,'rotation':args.rotate_display,'setup_page':setup.page if setup.active else None,'wifi_connected':network.status['connected'],'touch_calibrated':bool(touch and touch.matrix),'status':status,'aircraft':len(rows),'feed_paused':diagnostic_paused,'cloud_status':view.clouds.snapshot(cfg)[1] if view.clouds else 'OFF','weather':view.weather.snapshot(cfg) if view.weather else None,'selected_callsign':current.get('flight','').strip() if current else None,'selected_route':current.get('route_label') if current else None}))
            diagnostic_request.unlink(missing_ok=True)
        present_start = time.monotonic()
        present()
        presented = time.monotonic()
        recent_presentations.append(presented)
        if args.benchmark_seconds:
            if last_present is not None:
                frame_times.append(presented-last_present)
            render_times.append(present_start-render_start)
            present_times.append(presented-present_start)
            last_present = presented
            if presented-started >= args.benchmark_seconds:
                running = False
        if args.screenshot and (received is not None or now-started > 20):
            pygame.image.save(output, args.screenshot)
            print(json.dumps({'aircraft': len(rows), 'status': status, 'error': error}))
            running = False
        clock.tick(max(1, min(30, args.fps)))
    if view.weather:
        view.weather.stop.set()
        view.weather.wake.set()
    if view.clouds:
        view.clouds.stop.set()
        view.clouds.wake.set()
    feed.stop.set()
    feed.wake.set()
    if native_display:
        native_display.close()
    pygame.quit()
    if frame_times:
        ordered = sorted(frame_times)
        print(json.dumps({'application_fps': round(len(frame_times)/sum(frame_times),2),
                          'frame_p95_ms': round(ordered[int((len(ordered)-1)*.95)]*1000,1),
                          'render_avg_ms': round(sum(render_times)/len(render_times)*1000,1),
                          'present_avg_ms': round(sum(present_times)/len(present_times)*1000,1)}))


if __name__ == '__main__':
    main()
