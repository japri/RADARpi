# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Touch-only settings: Wi-Fi, keyboard, coordinates, map, calibration."""
import math
from resolution_canvas import pygame
from map_picker import MapPicker
from ui_contrast import LEVELS, contrast_level
from providers import PROVIDERS, provider_id, poll_seconds


def valid_coordinates(lat,lon):
    lat,lon = float(lat),float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
        raise ValueError('Latitude: -90 to 90. Longitude: -180 to 180.')
    return lat,lon


class SetupUI:
    def __init__(self,screen,view,feed,network,root):
        self.screen,self.view,self.feed,self.network = screen,view,feed,network
        self.active = False
        self.page = 'menu'
        self.buttons = []
        self.message = ''
        self.offset = 0
        self.keyboard = None
        self.map = None
        self.root = root
        self.lat = self.lon = ''
        self.can_calibrate = False
        self.data_provider = 'adsb_lol'
        self.interval = 8
        self.callsign_labels = 'selected'

    def open(self,page='menu'):
        self.active = True
        self.page = page
        self.message = ''
        if page == 'wifi':
            self.network.request('scan')
        elif page == 'location':
            with self.feed.lock:
                self.lat,self.lon = str(self.feed.cfg['latitude']),str(self.feed.cfg['longitude'])
        elif page == 'data':
            with self.feed.lock:
                self.data_provider = provider_id(self.feed.cfg)
                self.interval = poll_seconds(self.feed.cfg)
                self.callsign_labels = self.feed.cfg.get('callsign_labels','selected')
                if self.callsign_labels not in ('off','selected','all'):
                    self.callsign_labels = 'selected'

    def key_input(self,title,value,callback,secret=False,numeric=False):
        self.keyboard = dict(title=title,value=value,callback=callback,secret=secret,numeric=numeric,shift=False,symbols=False,replace=bool(value))

    def button(self,title,rect,action):
        rect = pygame.Rect(rect)
        self.view.button(rect,title)
        self.buttons.append((rect,action))

    def draw(self):
        self.buttons = []
        self.view.set_contrast(self.feed.cfg)
        self.screen.fill(self.view.color((3,15,7)))
        if self.keyboard:
            self.draw_keyboard()
            return
        label = self.view.label
        title = {'menu':'RADAR SETTINGS','wifi':'WI-FI SETUP','location':'RADAR LOCATION','map':'CHOOSE A MAP PIN','data':'AIRCRAFT DATA','units':'DISPLAY / UNITS','contrast':'DISPLAY CONTRAST'}[self.page]
        label(title,12,7,21)
        if self.page == 'menu':
            state = self.network.status
            label(('Connected: '+state['ssid']) if state['connected'] else 'Wi-Fi disconnected',12,43,12,width=455)
            label('IP '+(state['ip'] or '--'),12,64,12)
            self.button('Wi-Fi networks',(10,94,225,48),'wifi')
            self.button('Radar location',(245,94,225,48),'location')
            self.button('Data / refresh',(10,151,225,48),'data')
            self.button('Location label',(245,151,225,48),'label')
            self.button('Calibrate touch',(10,208,225,48),'calibrate')
            self.button('Display / units',(245,208,225,48),'units')
            self.button('Clouds: '+('ON' if self.feed.cfg.get('cloud_overlay',True) else 'OFF'),(10,268,225,38),'clouds')
            self.button('Back to radar',(245,268,225,38),'close')
        elif self.page == 'units':
            selected = self.feed.cfg.get('measurement_units','aviation')
            label('Altitude / speed / distance',12,39,12)
            for i,(value,title) in enumerate((('aviation','Aviation: ft / kt / km'),('metric','Metric: m / km/h / km'),('imperial','Imperial: ft / mph / mi'))):
                self.button(('* ' if selected == value else '')+title,(8,61+i*44,464,38),('units',value))
            unit = 'Fahrenheit' if self.feed.cfg.get('temperature_unit') == 'fahrenheit' else 'Celsius'
            self.button('Temperature: '+unit,(8,196,464,38),'temperature')
            self.button('Contrast: '+LEVELS[contrast_level(self.feed.cfg)],(8,240,464,34),'contrast')
            self.button('Back',(8,280,464,32),'menu')
        elif self.page == 'contrast':
            label('Radar colors only; saves on this Pi.',12,40,12)
            selected=contrast_level(self.feed.cfg)
            for i,name in enumerate(LEVELS):
                self.button(('* ' if selected==i else '')+name,(8+(i%2)*236,66+(i//2)*46,228,40),('contrast',i))
            label('LIVE   GIA421   CGK > DPS',18,171,19)
            label('Altitude 37,575 FT     Speed 400 KT',18,204,12,(83,151,98))
            label('Higher contrast: darker panels, brighter text.',12,239,11,width=455)
            self.button('Back',(8,280,464,32),'units')
        elif self.page == 'data':
            source = PROVIDERS[self.data_provider]
            label('Position provider (tap to switch)',12,39,12)
            self.button(source['name'],(8,62,464,43),'provider')
            label(source['home'],12,111,11,width=455)
            label('Personal use / no API key',12,130,10)
            self.button('-', (8,154,70,43), 'slower_number')
            self.button(f'Every {self.interval:g} seconds', (86,154,308,43), 'interval')
            self.button('+', (402,154,70,43), 'higher_number')
            label(self.message or '5-300 sec. Tap interval to enter a number.',12,207,11,width=455)
            label('Plus response time. Server retry limits still apply.',12,228,10,width=455)
            self.button('Callsign labels: '+self.callsign_labels.upper(),(8,244,464,28),'callsigns')
            self.button('Cancel',(8,278,225,34),'menu')
            self.button('Save',(245,278,227,34),'savedata')
        elif self.page == 'wifi':
            label(self.network.message or 'Choose a network',12,36,11,width=456)
            networks = self.network.networks
            for i,item in enumerate(networks[self.offset:self.offset+4]):
                security = 'OPEN' if item['security'] in ('','--') else item['security']
                self.button(f'{item["ssid"][:25]}  {item["signal"]}% {security}',(8,58+i*42,464,37),('network',item))
            if not networks and not self.network.busy:
                label('No networks found. Try Scan or Hidden.',12,90,12)
            self.button('< Prev',(8,232,110,33),'prev')
            self.button('Next >',(124,232,110,33),'more')
            label('Connecting...' if self.network.busy else f'{len(networks)} networks',250,242,11)
            self.button('Back',(8,278,144,34),'menu')
            self.button('Scan',(168,278,144,34),'scan')
            self.button('Hidden SSID',(328,278,144,34),'hidden')
        elif self.page == 'location':
            label('Signed decimal degrees; works offline',12,40,12)
            self.button('LAT  '+self.lat,(8,70,464,48),'latitude')
            self.button('LON  '+self.lon,(8,131,464,48),'longitude')
            label(self.message,12,185,11,width=455)
            self.button('Save coordinates',(8,214,464,42),'savecoords')
            self.button('Back',(8,278,144,34),'menu')
            self.button('Choose on map',(168,278,144,34),'map')
            self.button('Auto IP',(328,278,144,34),'ip')
        elif self.page == 'map':
            self.map.draw(self.screen,self.view)
            label(self.map.message,12,27,9,width=455)
            label(f'{self.map.lat:.5f}, {self.map.lon:.5f}   Z{self.map.zoom}',12,262,11)
            self.button('Back',(6,281,100,33),'location')
            self.button('-',(114,281,58,33),'zoomout')
            self.button('+',(180,281,58,33),'zoomin')
            self.button('Use this pin',(246,281,228,33),'savepin')

    def draw_keyboard(self):
        k = self.keyboard
        self.view.label(k['title'],10,8,17,width=460)
        pygame.draw.rect(self.screen,(17,49,25),(8,40,464,44),border_radius=5)
        shown = '*'*len(k['value']) if k['secret'] else k['value']
        self.view.label(shown[-37:] or 'Type here',16,51,17,width=445)
        self.view.label('First key replaces the selected value' if k['replace'] else 'Tap keys, then Done. Passwords are hidden.' if k['secret'] else 'Tap keys, then Done.',10,90,11)
        if k['numeric']:
            rows = ['123','456','789','-0.']
            for row,chars in enumerate(rows):
                for col,char in enumerate(chars):
                    self.button(char,(86+col*104,112+row*38,100,34),('char',char))
            self.button('Cancel',(8,278,110,34),'cancelkey')
            self.button('Clear',(125,278,110,34),'clearkey')
            self.button('< DEL',(242,278,110,34),'deletekey')
            self.button('Done',(359,278,113,34),'donekey')
        else:
            rows = ['!@#$%^&*()','-_=+[]{}<>','.,:;?/\\|~','\'"`'] if k['symbols'] else ['1234567890','qwertyuiop','asdfghjkl','zxcvbnm']
            for row,chars in enumerate(rows):
                if k['shift']:
                    chars = chars.upper()
                start = (480-len(chars)*47)//2
                for col,char in enumerate(chars):
                    self.button(char,(start+col*47,112+row*38,43,34),('char',char))
            for title,rect,action in [('Back',(5,278,69,34),'cancelkey'),('SHIFT' if not k['shift'] else 'shift',(79,278,73,34),'shiftkey'),('ABC' if k['symbols'] else '#+=',(157,278,62,34),'symbolkey'),('Space',(224,278,79,34),('char',' ')),('< DEL',(308,278,78,34),'deletekey'),('Done',(391,278,84,34),'donekey')]:
                self.button(title,rect,action)

    def tap(self,pos):
        action = next((action for rect,action in self.buttons if rect.collidepoint(pos)),None)
        if self.keyboard:
            k = self.keyboard
            if isinstance(action,tuple) and action[0]=='char':
                if k['replace']:
                    k['value'] = ''
                k['replace'] = False
                if len(k['value'])<64:
                    k['value'] += action[1]
            elif action == 'deletekey':
                k['value'] = '' if k['replace'] else k['value'][:-1]
                k['replace'] = False
            elif action == 'clearkey':
                k['value'] = ''
                k['replace'] = False
            elif action == 'shiftkey':
                k['shift'] = not k['shift']
            elif action == 'symbolkey':
                k['symbols'] = not k['symbols']
            elif action in ('donekey','cancelkey'):
                self.keyboard = None
                if action == 'donekey':
                    k['callback'](k['value'])
                k['value'] = ''
            return
        if action == 'close':
            self.active = False
        elif action in ('menu','wifi','location','data'):
            self.open(action)
        elif action == 'contrast':
            self.open('contrast')
        elif isinstance(action,tuple) and action[0] == 'contrast':
            self.feed.change(display_contrast=action[1])
        elif action == 'units':
            self.open('units')
        elif isinstance(action,tuple) and action[0] == 'units':
            self.feed.change(measurement_units=action[1])
        elif action == 'temperature':
            unit = 'celsius' if self.feed.cfg.get('temperature_unit') == 'fahrenheit' else 'fahrenheit'
            self.feed.change(temperature_unit=unit)
        elif action == 'clouds':
            self.feed.change(cloud_overlay=not self.feed.cfg.get('cloud_overlay',True))
        elif action == 'label':
            with self.feed.lock:
                value = self.feed.cfg.get('location_label') or self.feed.cfg.get('location_name','')
            self.key_input('Location label (up to 20 characters)',value,self.save_label)
        elif action == 'provider':
            keys = list(PROVIDERS)
            self.data_provider = keys[(keys.index(self.data_provider)+1)%len(keys)]
        elif action == 'interval':
            self.key_input('Refresh seconds (5-300)',f'{self.interval:g}',self.set_interval,numeric=True)
        elif action == 'slower_number':
            self.interval = max(5,self.interval-1)
        elif action == 'higher_number':
            self.interval = min(300,self.interval+1)
        elif action == 'callsigns':
            modes = ('off','selected','all')
            self.callsign_labels = modes[(modes.index(self.callsign_labels)+1)%3]
        elif action == 'savedata':
            self.feed.change(data_provider=self.data_provider,refresh_seconds=self.interval,callsign_labels=self.callsign_labels)
            self.active = False
        elif action == 'calibrate':
            if self.can_calibrate:
                self.active = False
                return 'calibrate'
        elif action == 'scan' and not self.network.busy:
            self.offset = 0
            self.network.request('scan')
        elif action == 'prev':
            self.offset = max(0,self.offset-4)
        elif action == 'more':
            if self.offset+4<len(self.network.networks):
                self.offset += 4
        elif action == 'hidden' and not self.network.busy:
            self.key_input('Hidden Wi-Fi name','',lambda value:self.choose_network(dict(ssid=value,security='WPA2',hidden=True)))
        elif isinstance(action,tuple) and action[0]=='network' and not self.network.busy:
            self.choose_network(action[1])
        elif action == 'latitude':
            self.key_input('Latitude (-90 to 90)',self.lat,lambda value:setattr(self,'lat',value),numeric=True)
        elif action == 'longitude':
            self.key_input('Longitude (-180 to 180)',self.lon,lambda value:setattr(self,'lon',value),numeric=True)
        elif action == 'savecoords':
            try:
                lat,lon = valid_coordinates(self.lat,self.lon)
                self.feed.change(latitude=lat,longitude=lon,location_name='Custom location',location_label='',location_mode='manual')
                self.active = False
            except ValueError:
                self.message = 'Enter valid latitude (-90..90) and longitude (-180..180).'
        elif action == 'ip':
            self.feed.change(location_mode='ip',location_label='')
            self.active = False
        elif action == 'map':
            if self.map is None:
                self.map = MapPicker(self.root)
            with self.feed.lock:
                self.map.reset(dict(self.feed.cfg))
            self.page = 'map'
        elif action == 'zoomin':
            self.map.zoom = min(18,self.map.zoom+1)
        elif action == 'zoomout':
            self.map.zoom = max(2,self.map.zoom-1)
        elif action == 'savepin':
            self.feed.change(latitude=self.map.lat,longitude=self.map.lon,location_name='Map pin',location_label='',location_mode='manual')
            self.active = False
        elif self.page == 'map' and 38<=pos[1]<240:
            self.map.tap(pos)

    def choose_network(self,item):
        if not item['ssid']:
            return
        if '802.1X' in item['security'] or 'EAP' in item['security'] or 'WEP' in item['security']:
            self.network.message = 'Enterprise/WEP Wi-Fi needs administrator setup.'
        elif item['security'] in ('','--'):
            self.network.request('connect',ssid=item['ssid'],security='OPEN')
        else:
            self.key_input('Password: '+item['ssid'],'',lambda password:self.network.request('connect',ssid=item['ssid'],security=item['security'],password=password,hidden=item.get('hidden',False)),secret=True)

    def set_interval(self,value):
        try:
            number = float(value)
            if not math.isfinite(number) or not 5 <= number <= 300 or number != int(number):
                raise ValueError()
            self.interval = int(number)
            self.message = ''
        except ValueError:
            self.message = 'Enter a whole number from 5 to 300.'

    def save_label(self,value):
        label = ''.join(c for c in value.strip() if c.isprintable())[:20]
        self.feed.change(location_label=label)
