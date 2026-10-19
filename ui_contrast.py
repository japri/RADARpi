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


def cloud_contrast(rgba,level):
    """Lift cloud opacity once per image/contrast change, preserving clear pixels."""
    if not level:return rgba
    alpha=bytes(min(200,round(a*(1+level*.8))) for a in range(256))
    out=bytearray(rgba)
    out[3::4]=bytes(out[3::4]).translate(alpha)
    return bytes(out)
