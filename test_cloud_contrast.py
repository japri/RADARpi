import unittest
from ui_contrast import cloud_contrast

class CloudContrastTests(unittest.TestCase):
    def test_clear_pixels_rgb_and_original_are_preserved(self):
        data=bytes((60,195,100,0,60,195,100,70))
        self.assertIs(cloud_contrast(data,0),data)
        result=cloud_contrast(data,3)
        self.assertEqual(result,bytes((60,195,100,0,60,195,100,200)))
        self.assertEqual(data[-1],70)

    def test_levels_progressively_strengthen_actual_cloud_alpha(self):
        data=bytes(value for a in range(71) for value in (60,195,100,a))
        previous=data[3::4]
        for level in (1,2,3):
            result=cloud_contrast(data,level)
            self.assertEqual(len(result),len(data))
            self.assertTrue(all(a<=b<=200 for a,b in zip(previous,result[3::4])))
            previous=result[3::4]
