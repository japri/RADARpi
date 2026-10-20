# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Root-owned, narrowly scoped NetworkManager helper. JSON in/out; no secrets logged."""
import json
import os
import subprocess
import sys
import time
import uuid


def nm(*args):
    return subprocess.run(['/usr/bin/nmcli',*args],env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},text=True,capture_output=True,timeout=25,check=True).stdout.strip()


def split_fields(line):
    fields, current, escaped = [], '', False
    for char in line:
        if escaped:
            current += char
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            fields.append(current)
            current = ''
        else:
            current += char
    return fields+[current]


def status():
    lines = nm('-g','GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS','device','show','wlan0').splitlines()
    return {'connected': bool(lines and lines[0].startswith('100')), 'ssid': lines[1] if len(lines)>1 else '', 'ip':lines[2].split('/')[0] if len(lines)>2 else ''}


def connect(request):
    import dbus
    ssid, password = request.get('ssid',''), request.get('password','')
    security = request.get('security','WPA2')
    if not isinstance(ssid,str) or not 1 <= len(ssid.encode('utf8')) <= 32 or any(ord(c)<32 for c in ssid):
        raise ValueError('Network name must contain 1-32 bytes.')
    if not isinstance(password,str) or any(ord(c)<32 for c in password):
        raise ValueError('Invalid password.')
    if '802.1X' in security or 'EAP' in security or 'WEP' in security:
        raise ValueError('Enterprise/WEP networks need administrator setup.')
    secured = security not in ('','--','OPEN')
    if secured and password and not (8 <= len(password) <= 63 or len(password)==64 and all(c in '0123456789abcdefABCDEF' for c in password)):
        raise ValueError('Wi-Fi password must be 8-63 characters (or 64 hex digits).')
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('org.freedesktop.NetworkManager','/org/freedesktop/NetworkManager'),'org.freedesktop.NetworkManager')
    device = manager.GetDeviceByIpIface('wlan0')
    checkpoint = manager.CheckpointCreate(dbus.Array([device],signature='o'),dbus.UInt32(60),dbus.UInt32(0))
    created = None
    try:
        if secured and not password:
            # NetworkManager may already have a saved secret; never read it back.
            nm('--wait','35','device','wifi','connect',ssid,'ifname','wlan0')
        else:
            settings = {
                'connection': {'id':'Flight Radar - '+ssid,'uuid':str(uuid.uuid4()),'type':'802-11-wireless','interface-name':'wlan0','autoconnect':True},
                '802-11-wireless': {'ssid':dbus.ByteArray(ssid.encode('utf8')),'mode':'infrastructure','hidden':bool(request.get('hidden',False))},
                'ipv4': {'method':'auto'}, 'ipv6': {'method':'auto'}}
            if secured:
                settings['802-11-wireless-security'] = {'key-mgmt':'sae' if 'WPA3' in security and 'WPA2' not in security else 'wpa-psk','psk':password}
            settings = dbus.Dictionary({k:dbus.Dictionary(v,signature='sv') for k,v in settings.items()},signature='sa{sv}')
            created, active = manager.AddAndActivateConnection(settings,device,dbus.ObjectPath('/'))
            properties = dbus.Interface(bus.get_object('org.freedesktop.NetworkManager',active),'org.freedesktop.DBus.Properties')
            deadline = time.monotonic()+40
            while time.monotonic()<deadline:
                state = int(properties.Get('org.freedesktop.NetworkManager.Connection.Active','State'))
                if state == 2:
                    break
                if state == 4:
                    raise RuntimeError('Connection failed')
                time.sleep(.5)
            else:
                raise RuntimeError('Connection timeout')
        current_status = status()
        manager.CheckpointDestroy(checkpoint)
        return {'ok':True,'status':current_status}
    except Exception:
        try:
            manager.CheckpointRollback(checkpoint)
        except Exception:
            pass
        if created:
            try:
                dbus.Interface(bus.get_object('org.freedesktop.NetworkManager',created),'org.freedesktop.NetworkManager.Settings.Connection').Delete()
            except Exception:
                pass
        return {'ok':False,'error':'Could not connect. Check password and signal.','status':status()}


def dispatch(request):
    action = request.get('action')
    if action == 'status':
        return {'ok':True,'status':status()}
    if action == 'scan':
        nm('radio','wifi','on')
        rows = nm('-t','-f','SSID,SIGNAL,SECURITY','device','wifi','list','ifname','wlan0','--rescan','yes')
        networks = {}
        for line in rows.splitlines():
            ssid,signal,security = split_fields(line)
            if ssid and (ssid not in networks or int(signal)>networks[ssid]['signal']):
                networks[ssid] = dict(ssid=ssid,signal=int(signal),security=security)
        return {'ok':True,'networks':sorted(networks.values(),key=lambda n:-n['signal']),'status':status()}
    if action == 'connect':
        return connect(request)
    raise ValueError('Unsupported network operation.')


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.buffer.read(4096))
        result = dispatch(request)
    except ValueError as error:
        result = {'ok':False,'error':str(error)}
    except Exception:
        result = {'ok':False,'error':'Network service unavailable. Please retry.'}
    print(json.dumps(result))
