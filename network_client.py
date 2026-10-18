import json
import os
import subprocess
import threading
import time


class NetworkClient:
    def __init__(self,enabled=True):
        self.status = {'connected':None,'ssid':'','ip':''}
        self.networks = []
        self.busy = False
        self.message = ''
        self.last_check = 0
        self.enabled = enabled

    def request(self,action,**values):
        if self.busy or not self.enabled:
            return
        self.busy = True
        if action != 'status':
            self.message = 'Scanning...' if action == 'scan' else 'Connecting...'
        def work():
            try:
                if action == 'status':
                    # Status is public. Avoid sudo opening a session on the LCD's
                    # controlling terminal during every background status poll.
                    proc = subprocess.run(['/usr/bin/nmcli','-g','GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS','device','show','wlan0'],stdin=subprocess.DEVNULL,text=True,capture_output=True,timeout=10,check=True,env=dict(os.environ,LC_ALL='C'),start_new_session=True)
                    lines = proc.stdout.strip().splitlines()
                    data = {'ok':True,'status':{'connected':bool(lines and lines[0].startswith('100')),'ssid':lines[1] if len(lines)>1 else '', 'ip':lines[2].split('/')[0] if len(lines)>2 else ''}}
                else:
                    proc = subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','-I','/usr/local/lib/flight-radar/network-helper.py'],input=json.dumps(dict(action=action,**values)),text=True,capture_output=True,timeout=65,start_new_session=True)
                    data = json.loads(proc.stdout)
                if 'status' in data:
                    self.status = data['status']
                if 'networks' in data:
                    self.networks = data['networks']
                if action != 'status' or not data.get('ok'):
                    self.message = ('Connected' if action == 'connect' else 'Choose a network') if data.get('ok') else data.get('error','Network error')
            except Exception:
                self.message = 'Network setup unavailable. Please retry.'
            finally:
                values.clear()  # Do not retain a password after the operation.
                self.last_check = time.monotonic()
                self.busy = False
        threading.Thread(target=work,daemon=True).start()

    def tick(self):
        if self.enabled and not self.busy and time.monotonic()-self.last_check>6:
            self.request('status')
