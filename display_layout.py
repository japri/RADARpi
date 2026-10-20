# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
"""Aspect-preserving output and inverse pointer mapping for HDMI displays."""
from dataclasses import dataclass

@dataclass
class Viewport:
    width: int
    height: int
    rotation: int = 0
    logical_width: int = 480
    logical_height: int = 320

    @property
    def rect(self):
        lw, lh = self.logical_width, self.logical_height
        if self.rotation in (90, 270):
            lw, lh = lh, lw
        scale = min(self.width / lw, self.height / lh)
        w, h = round(lw * scale), round(lh * scale)
        return (self.width - w) // 2, (self.height - h) // 2, w, h

    def to_logical(self, point):
        x, y, w, h = self.rect
        px, py = point
        if not (x <= px < x + w and y <= py < y + h):
            return None
        u, v = (px - x) / w, (py - y) / h
        if self.rotation == 90:
            u, v = 1 - v, u
        elif self.rotation == 180:
            u, v = 1 - u, 1 - v
        elif self.rotation == 270:
            u, v = v, 1 - u
        return (min(self.logical_width - 1, int(u * self.logical_width)),
                min(self.logical_height - 1, int(v * self.logical_height)))

    def render(self, canvas, output):
        import pygame
        from resolution_canvas import pixels
        canvas = pixels(canvas)
        x, y, w, h = self.rect
        frame = pygame.transform.rotate(canvas, self.rotation) if self.rotation else canvas
        output.fill((0, 0, 0))
        # Scale into a contiguous surface: SDL/KMS subsurfaces may have a wider
        # pitch than their visible width, which some ARM scalers mishandle.
        output.blit(frame if frame.get_size() == (w,h) else pygame.transform.smoothscale(frame, (w, h)), (x, y))
