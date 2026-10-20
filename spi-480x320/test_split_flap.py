# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import unittest
from split_flap import FlipState, DURATION, STAGGER, FLAPS

class FlapTests(unittest.TestCase):
    def test_updates_do_not_restart_animation(self):
        state=FlipState()
        state.update('GIA421','plane-a',10)
        state.update('GIA421','plane-a',10.2)
        self.assertEqual(state.started,10)
        self.assertGreater(state.cell(0,10.2)[2],0)
        self.assertLess(state.cell(5,10.2)[2],state.cell(0,10.2)[2])
        self.assertEqual(state.cell(5,14)[2],1)

    def test_rapid_selection_targets_latest_without_queue(self):
        state=FlipState()
        state.update('GIA421','a',0)
        state.update('LNI1391','b',.1)
        state.update('CTV888','c',.2)
        self.assertEqual(state.target,'CTV888')
        self.assertEqual(state.cell(5,4),('8','8',1))

    def test_route_never_reuses_previous_aircraft_route(self):
        state=FlipState()
        state.update('CGK > DPS','a',0,True)
        state.update('SUB > CGK','b',1,True)
        self.assertEqual(state.previous,'')
        self.assertEqual(state.cell(0,1),(' ',' ',0))

    def test_unchanged_cells_settle_and_total_duration_is_bounded(self):
        state=FlipState()
        state.update('ABC','a',0)
        state.update('ABD','a',1)
        self.assertEqual(state.cell(0,1),('A','A',1))
        self.assertLess((FLAPS+3)*DURATION+8*STAGGER,3)
        self.assertEqual(state.cell(2,5),('D','D',1))

    def test_cycles_through_multiple_characters_before_landing(self):
        state=FlipState()
        state.update('G','a',0)
        letters=[state.cell(0,(i+.5)*DURATION)[1] for i in range(FLAPS)]
        self.assertGreater(len(set(letters)),5)
        self.assertEqual(letters[-1],'G')
        for i in range(FLAPS-1):
            self.assertEqual(state.cell(0,(i+.99)*DURATION)[1],
                             state.cell(0,(i+1.01)*DURATION)[0])
        self.assertEqual(state.cell(0,4),('G','G',1))

if __name__=='__main__':unittest.main()
