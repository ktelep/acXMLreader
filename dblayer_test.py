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

    def tearDown(self):
        raidgroups = db_layer.session.query(db_layer.RAIDGroup).all()
        for group in raidgroups:
            db_layer.session.delete(group)
        db_layer.session.commit()

    def test_raidgroup_insert(self):
        test_raidgroup = db_layer.session.query(db_layer.RAIDGroup).one()
        self.assertEquals(test_raidgroup.RAIDGroupID,1)

    def test_raidgroup_modify(self):
        test_raidgroup = db_layer.session.query(db_layer.RAIDGroup).one()
        test_raidgroup.TotalSize=30
        db_layer.session.commit()
        test_raidgroup2 = db_layer.session.query(db_layer.RAIDGroup).filter(db_layer.RAIDGroup.RaidID==1).one()
        self.assertEquals(test_raidgroup.TotalSize,test_raidgroup2.TotalSize)

if __name__ == '__main__':
    unittest.main()
        

