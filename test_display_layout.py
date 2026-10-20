# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import unittest
import importlib.util
from display_layout import Viewport

class DisplayTests(unittest.TestCase):
    def test_wide_panel_fills_screen_without_stretching_scope(self):
        v = Viewport(800, 480, 180, logical_width=533)
        self.assertEqual(v.rect, (0,0,800,480))
        self.assertLess(abs(280*800/533-280*480/320), 1)
        self.assertEqual(v.to_logical((0,0)), (532,319))
        self.assertEqual(v.to_logical((799,479)), (0,0))

    def test_letterbox_and_controls(self):
        v = Viewport(800, 480)
        self.assertEqual(v.rect, (40, 0, 720, 480))
        self.assertIsNone(v.to_logical((39, 200)))
        self.assertIsNone(v.to_logical((760, 200)))
        self.assertEqual(v.to_logical((40, 0)), (0, 0))
        self.assertEqual(v.to_logical((759, 479)), (479, 319))
        self.assertEqual(v.to_logical((400, 240)), (240, 160))

    def test_rotation_corners(self):
        for rotation, corner in [(0, (0, 0)), (90, (479, 0)), (180, (479, 319)), (270, (0, 319))]:
            v = Viewport(800, 480, rotation)
            x, y, w, h = v.rect
            self.assertEqual(v.to_logical((x, y)), corner)
            self.assertEqual(v.to_logical((x+w/2, y+h/2)), (240, 160))
            self.assertIsNone(v.to_logical((x+w, y+h)))

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'pygame required for pixel checks')
    def test_render_uses_full_stride_and_black_margins(self):
        import pygame
        canvas = pygame.Surface((480, 320), depth=32)
        canvas.fill((10, 40, 20))
        pygame.draw.rect(canvas, (200, 100, 50), (240, 160, 240, 160))
        output = pygame.Surface((800, 480), depth=32)
        Viewport(800, 480).render(canvas, output)
        for point in ((0, 0), (39, 240), (760, 240), (799, 479)):
            self.assertEqual(tuple(output.get_at(point))[:3], (0, 0, 0))
        for point in ((40, 0), (100, 100), (100, 479)):
            self.assertEqual(tuple(output.get_at(point))[:3], (10, 40, 20))
        self.assertEqual(tuple(output.get_at((700, 400)))[:3], (200, 100, 50))

if __name__ == '__main__':
    unittest.main()
