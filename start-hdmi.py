"""Launch only on the confirmed HDMI/KMS display; no boot or overlay edits."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
connectors = [p for p in Path('/sys/class/drm').glob('card*-HDMI-A-*')
              if (p/'status').read_text().strip() == 'connected']
if len(connectors) != 1:
    raise RuntimeError('Expected one connected HDMI display')
card = connectors[0].name.split('-')[0][4:]
os.environ.update(SDL_VIDEODRIVER='KMSDRM', SDL_KMSDRM_DEVICE_INDEX=card,
                  SDL_TOUCH_MOUSE_EVENTS='0', PYGAME_HIDE_SUPPORT_PROMPT='1')
os.execv(sys.executable, [sys.executable, str(root/'radar.py'), *sys.argv[1:]])
