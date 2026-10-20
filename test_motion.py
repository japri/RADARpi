# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import math,unittest
from motion import Motion
class MotionTests(unittest.TestCase):
 def row(self,east=0,**kw):
  return dict(dict(hex='a',distance=abs(east),bearing=math.pi/2 if east>=0 else -math.pi/2,gs=360,track=90,position_age=0),**kw)
 def test_units_and_no_old_initial_prediction(self):
  self.assertAlmostEqual(Motion().position(self.row(),0,10,10)[0],1.852)
  self.assertEqual(Motion().position(self.row(position_age=40),0,0,0),(0,0))
  self.assertEqual(Motion().position(self.row(gs=None),0,10,10),(0,0))
 def test_behind_report_never_reverses_or_teleports(self):
  m=Motion();m.position(self.row(),0,0,0)
  for i in range(1,101):m.position(self.row(),0,i/10,i/10)
  previous=m.states['a']['position'][0]
  row=self.row(east=0.2)
  for i in range(101,201):
   now=i/10;p=m.position(row,10,now-10,now)[0]
   self.assertGreaterEqual(p,previous-1e-10)
   self.assertLessEqual(p-previous,0.1852*1.6*0.1+1e-10)
   previous=p
 def test_expiry_and_old_snapshot_hold(self):
  m=Motion();row=self.row();p=m.position(row,0,29,29)
  self.assertEqual(m.position(row,0,31,31),p)
  self.assertEqual(m.position(self.row(east=-3,position_age=40),32,0,32),p)
  self.assertEqual(m.position(row,0,50,50),p)
 def test_duplicate_does_not_extend_prediction(self):
  m=Motion();row=self.row();m.position(row,0,0,0)
  for i in range(1,400):
   now=i/10;m.position(row,int(now/10)*10,now%10,now)
  p=m.states['a']['position']
  self.assertEqual(m.position(row,40,0,40),p)
  self.assertEqual(m.states['a']['observed'],0)
 def test_real_turn_and_offline_freeze(self):
  m=Motion();m.position(self.row(east=3),0,0,0)
  row=self.row(east=2.9,track=270)
  m.position(row,1,0,1);before=m.states['a']['position'][0]
  after=m.position(row,1,.1,1.1)[0];self.assertLess(after,before)
  frozen=m.states['a']['position'];self.assertEqual(m.position(row,1,2,3,True),frozen)
 def test_no_input_mutation(self):
  row=self.row(position_age=25);copy=dict(row)
  Motion().position(row,0,0,0);self.assertEqual(row,copy)

 def test_brief_omission_retains_continuity_but_expires(self):
  m=Motion();m.position(self.row(),0,0,0)
  m.retain([],10);self.assertIn('a',m.states)
  m.retain([],100);self.assertNotIn('a',m.states)
