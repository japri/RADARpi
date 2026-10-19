import unittest
from aircraft_selection import resolve_selection
class SelectionTests(unittest.TestCase):
    def test_lock_survives_reordering_missing_and_return(self):
        a={'hex':'a'};b={'hex':'b'}
        self.assertEqual(resolve_selection([b,a],'b','a'),(a,'a'))
        self.assertEqual(resolve_selection([b],'a','a'),(None,'a'))
        self.assertEqual(resolve_selection([],'a','a'),(None,'a'))
        self.assertEqual(resolve_selection([a,b],'a','a'),(a,'a'))
    def test_unlocked_selection_and_fallback(self):
        a={'hex':'a'};b={'hex':'b'}
        self.assertEqual(resolve_selection([a,b],'b',None),(b,'b'))
        self.assertEqual(resolve_selection([b],'a',None),(b,'b'))
        self.assertEqual(resolve_selection([],'a',None),(None,None))
