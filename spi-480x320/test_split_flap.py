import unittest
from split_flap import FlipState, DURATION, STAGGER

class FlapTests(unittest.TestCase):
    def test_updates_do_not_restart_animation(self):
        state=FlipState()
        state.update('GIA421','plane-a',10)
        state.update('GIA421','plane-a',10.2)
        self.assertEqual(state.started,10)
        self.assertGreater(state.cell(0,10.2)[2],0)
        self.assertLess(state.cell(5,10.2)[2],state.cell(0,10.2)[2])
        self.assertEqual(state.cell(5,11)[2],1)

    def test_rapid_selection_targets_latest_without_queue(self):
        state=FlipState()
        state.update('GIA421','a',0)
        state.update('LNI1391','b',.1)
        state.update('CTV888','c',.2)
        self.assertEqual(state.target,'CTV888')
        self.assertEqual(state.cell(5,1),('9','8',1))

    def test_route_never_reuses_previous_aircraft_route(self):
        state=FlipState()
        state.update('CGK > DPS','a',0,True)
        state.update('SUB > CGK','b',1,True)
        self.assertEqual(state.previous,'')
        self.assertEqual(state.cell(0,1),(' ','S',0))

    def test_unchanged_cells_settle_and_total_duration_is_bounded(self):
        state=FlipState()
        state.update('ABC','a',0)
        state.update('ABD','a',1)
        self.assertEqual(state.cell(0,1),('A','A',1))
        self.assertLess(DURATION+8*STAGGER,.6)
        self.assertEqual(state.cell(2,2),('C','D',1))

if __name__=='__main__':unittest.main()
