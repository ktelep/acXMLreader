#!/usr/bin/python

import dblayer as db_layer
import unittest

class TestRAIDGroup(unittest.TestCase):
   
    def setUp(self):
        self.raidgroup = db_layer.RAIDGroup()
        self.raidgroup.RAIDGroupID = 1
        self.raidgroup.Type = 0
        self.raidgroup.TotalSize = 20
        self.raidgroup.FreeSize = 10
        self.raidgroup.HighestContigFree = 10
        db_layer.session.add(self.raidgroup)
        db_layer.session.commit()

    def test_raidgroup_insert(self):
        test_raidgroup = db_layer.session.query(db_layer.RAIDGroup).one()
        print test_raidgroup
if __name__ == '__main__':
    unittest.main()
        

