# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 japri
import unittest
from aircraft_details import altitude, speed, distance, direction, registration_country, country_ranges

class DetailTests(unittest.TestCase):
    def test_conversion_and_defaults(self):
        self.assertEqual(altitude(10000,{}),('10,000','FT'))
        self.assertEqual(altitude(10000,{'measurement_units':'metric'}),('3,048','M'))
        self.assertEqual(speed(100,{'measurement_units':'metric'}),'185 KM/H')
        self.assertEqual(speed(100,{'measurement_units':'imperial'}),'115 MPH')
        self.assertEqual(distance(1.609344,{'measurement_units':'imperial'}),'1 MI')
        self.assertEqual(distance(100,{}),'100 KM')
        self.assertEqual(altitude('ground',{}),('GROUND',''))
        self.assertEqual(altitude(float('nan'),{}),('--','FT'))
        self.assertEqual(speed(None,{}),'-- KT')
        self.assertEqual(speed(-1,{}),'-- KT')

    def test_direction_does_not_mislabel_track(self):
        self.assertEqual(direction({'true_heading':327,'track':310}),'HDG 327°T')
        self.assertEqual(direction({'mag_heading':45,'track':50}),'HDG 045°M')
        self.assertEqual(direction({'track':359.9}),'TRK 000°')
        self.assertEqual(direction({'true_heading':float('nan'),'track':0}),'TRK 000°')
        self.assertEqual(direction({'track':-1}),'HDG --')
        self.assertEqual(direction({}),'HDG --')

    def test_registration_country_is_offline_and_address_based(self):
        for address,country in (('8a0000','Indonesia'),('4d2000','Malta'),
                                ('4d27ff','Malta'),('a00001','United States'),('400001','United Kingdom')):
            self.assertEqual(registration_country(address),country)
        for address in (None,'~8a0001','ffffff','000000','invalid','f00001','4d2800'):
            self.assertEqual(registration_country(address),'Unknown')
        rows=country_ranges()
        self.assertGreater(len(rows),180)
        for start,end,country in rows:
            self.assertLessEqual(start,end)
            self.assertTrue(0<start<=end<0xFFFFFF)

if __name__=='__main__': unittest.main()
