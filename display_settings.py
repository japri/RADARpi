# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Installation-time panel resolution choice, separate from feed settings."""
import json
import re
from pathlib import Path

PRESETS = ('auto','480x320','800x480','1024x600','1280x800','1920x1080')

def parse_resolution(value):
    if value == 'auto': return None
    match = re.fullmatch(r'(\d+)x(\d+)', str(value).lower())
    if not match: raise ValueError('Use auto or WIDTHxHEIGHT, for example 800x480')
    w,h = map(int,match.groups())
    if min(w,h)<320 or max(w,h)>1920:
        raise ValueError('Supported panel dimensions: 320 through 1920 pixels')
    return w,h

def load_resolution(root):
    path=Path(root)/'display.json'
    return json.loads(path.read_text()).get('resolution','auto') if path.exists() else 'auto'

def main():
    import argparse
    parser=argparse.ArgumentParser(description='Choose panel resolution before starting radar. No driver or boot changes.')
    parser.add_argument('--resolution',help='auto or WIDTHxHEIGHT; omit for interactive selection')
    args=parser.parse_args()
    value=args.resolution
    if value is None:
        print('Select actual panel pixels. Inches alone do not determine resolution.')
        for i,item in enumerate(PRESETS): print(f'{i}: {item}')
        answer=input('Number or custom WIDTHxHEIGHT [0 auto]: ').strip() or '0'
        value=PRESETS[int(answer)] if answer.isdigit() and int(answer)<len(PRESETS) else answer
    try: parse_resolution(value)
    except ValueError as error: parser.error(str(error))
    path=Path(__file__).with_name('display.json')
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({'resolution':value},indent=2)+'\n')
    temp.replace(path)
    print(f'Saved {value}. Takes effect on next radar start.')

if __name__=='__main__': main()
