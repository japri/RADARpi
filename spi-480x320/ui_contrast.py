"""Cached UI palette adjustments; no full-screen processing in the frame loop."""
from functools import lru_cache
LEVELS = ('Normal','Medium','High','Maximum')
def contrast_level(cfg):
    value=cfg.get('display_contrast',0)
    return value if type(value) is int and 0<=value<len(LEVELS) else 0
@lru_cache(maxsize=512)
def contrast_color(level,color):
    if not level:return color
    # Darken panel fills while lifting text and outlines; preserve alpha.
    factor=1+level*.22 if max(color[:3])>=65 else 1-level*.25
    return tuple(min(255,round(c*factor)) for c in color[:3])+tuple(color[3:])
