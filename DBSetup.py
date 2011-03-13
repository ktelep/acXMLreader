#!/usr/bin/python

from sqlalchemy import *
from sqlalchemy.orm import mapper, sessionmaker, relation, backref


db = create_engine('sqlite:///:memory:',echo=False)
#db = create_engine('sqlite:///test.db',echo=False)
metadata = MetaData(db)
Session=sessionmaker(db)
session=Session()

class RAIDGroup(object):
    def __init__(self,RaidGroupID,Type,TotalSize,FreeSize,HighestContigFree):
        self.RaidGroupID=RaidGroupID
        self.Type=Type
        self.TotalSize=TotalSize
        self.FreeSize=FreeSize
        self.HighestContigFree=HighestContigFree
      

    def __repr__(self):
        return "<RAIDGroup('%s', '%s', '%s', '%s')>" % \
               (self.RaidGroupID,self.Type,self.TotalSize,self.FreeSize,self.HighestContigFree)


class StorageGroup(object):
    def __init__(self,SGName,SGWWN):
        self.SGName = SGName
        self.SGWWN = SGWWN

    def __repr__(self):
        return "<StorageGroup('%s', '%s')>" % (self.SGName,self.SGWWN)

    
class Frame(object):
    def __init__(self,SerialNumber,Model,SPA,SPB,CacheLWM,CacheHWM,WWN):
        self.SerialNumber=SerialNumber
        self.Model=Model
        self.SPA=SPA
        self.SPB=SPB
        self.CacheLWM=CacheLWM
        self.CacheHWM=CacheHWM
        self.WWN=WWN

    def __repr__(self):
        return "<Clariion('%s', '%s', '%s', '%s', '%s', '%s', '%s')>" % \
               (self.SerialNumber,self.Model,self.SPA,self.SPB,self.CacheHWM,self.CacheLWM,self.WWN)

class Host(object):
    def __init__(self,Name,IP,ManualReg,HostID):
        self.Name=Name
        self.IP=IP
        self.ManualReg=ManualReg
        self.HostID=HostID

    def __repr__(self):
        return "<Host('%s','%s','%s','%s')>" % (self.Name,self.IP,self.ManualReg,self.HostID)

class LUN(object):
    
    def __init__(self,ALU,Name,WWN,State,Capacity,Ownership,DefaultOwner,ReadCacheEnabled,WriteCacheEnabled,isMetaHead=0,isMetaMember=0):
        self.ALU=ALU
        self.Name=Name
        self.WWN=WWN
        self.State=State
        self.Capacity=Capacity
        self.Ownership=Ownership
        self.DefaultOwner=DefaultOwner
        self.ReadCacheEnabled=ReadCacheEnabled
        self.WriteCacheEnabled=WriteCacheEnabled
        self.isMetaHead=isMetaHead
        self.isMetaMember=isMetaMember

    def __repr__(self):
        return "<LUN('%s', '%s','%s','%s','%s','%s','%s','%s','%s', %s, %s)>" % \
               (self.ALU,self.Name,self.WWN,self.State,self.Capacity,self.Ownership,self.DefaultOwner,
                self.ReadCacheEnabled,self.WriteCacheEnabled,self.isMetaHead,self.isMetaMember)

class HostWWN(object):

    def __init__(self,HostWWN):
        self.HostWWN=HostWWN

    def __repr__(self):
        return "<HostWWN('%s', '%s')>" % (self.HostID,self.HostWWN)

class FrameSoftware(object):

    def __init__(self,Name,Revision,Status):
        self.Name=Name
        self.Revision=Revision
        self.Status=Status

    def __repr__(self):
        return "<FrameSoftware('%s', '%s', '%s', '%s')" % (self.FrameID,self.Name,self.Revision,self.Status)

class Drive(object):

    def __init__(self,Location,Type,RawCapacity,Manufacture,Model,Firmware,TLAPartNbr,Speed):
        self.Location=Location
        self.Type=Type
        self.RawCapacity=RawCapacity
        self.Manufacture=Manufacture
        self.Model=Model
        self.Firmware=Firmware
        self.TLAPartNbr=TLAPartNbr
        self.Speed=Speed

    def __repr__(self):
        return "<Drive('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')" % (self.Location,self.Type,self.RawCapacity,self.Manufacture,self.Model,self.Firmware,self.TLAPartNbr,self.Speed)

class SGHost(object):

    def __init__(self,HostID,SGWWN):
        self.HostID=HostID
        self.SGWWN=SGWWN

    def __repr__(self):
        return "<SGHost('%s', '%s')>" %(self.HostID,self.SGWWN)


class SGLUN(object):

    def __init__(self,SGWWN,HLU):
        self.SGWWN=SGWWN
        self.HLU=HLU

    def __repr__(self):
        return "<SGLUN('%s','%s','%s')" % (SGWWN,ALU,HLU)

def setup_sqlite_tables():
    raidgroups = Table('RAIDGroup',metadata,
                       Column('RaidID',Integer, primary_key=True,autoincrement=True),
                       Column('RaidGroupID',Integer),
                       Column('Type',String(255)),
                       Column('TotalSize',Integer),
                       Column('FreeSize',Integer),
                       Column('HighestContigFree',Integer))

    storagegroups = Table('StorageGroup',metadata,
                          Column('SGName',String(255)),
                          Column('SGWWN',String(255), primary_key=True))

    
    frames = Table('Frame',metadata,
                   Column('FrameID',Integer, primary_key=True,autoincrement=True),
                   Column('SerialNumber',String(25)),
                   Column('Model',String(25)),
                   Column('SPA',String(255)),
                   Column('SPB',String(255)),
                   Column('CacheLWM',Integer),
                   Column('CacheHWM',Integer),
                   Column('WWN',String(255)),
                   Column('DeleteData',DateTime))

    hosts = Table('Host',metadata,
                  Column('Name',String(30)),
                  Column('IP',String(20)),
                  Column('ManualReg',SMALLINT),
                  Column('HostID',String(60),primary_key=True))

    luns = Table('LUNS',metadata,
                 Column('LunID',Integer,primary_key=True,autoincrement=True),
                 Column('ALU',Integer),
                 Column('Name',String(50)),
                 Column('WWN',String(50)),
                 Column('State',Integer),
                 Column('Capacity',Integer),
                 Column('Ownership',String(30)),
                 Column('DefaultOwner',String(30)),
                 Column('ReadCacheEnabled',SMALLINT),
                 Column('WriteCacheEnabled',SMALLINT),
                 Column('isMetaHead',SMALLINT),
                 Column('isMetaMember',SMALLINT),
                 Column('RaidID',Integer,ForeignKey('RAIDGroup.RaidID')))

    hostwwns = Table('HostWWN',metadata,
                    Column('id',Integer,autoincrement=True,primary_key=True),
                    Column('HostID',String(60),ForeignKey('Host.HostID')),
                    Column('HostWWN',String(255)))


    framesoftwares = Table('FrameSoftware',metadata,
                           Column('id',Integer,autoincrement=True,primary_key=True),
                           Column('FrameID',Integer,ForeignKey('Frame.FrameID')),
                           Column('Name',String(25)),
                           Column('Revision',String(10)),
                           Column('Status',String(25)))

    drives = Table('Drive',metadata,
                   Column('DriveID',Integer,primary_key=True,autoincrement=True),
                   Column('Location',String(25)),
                   Column('Type',String(25)),
                   Column('RawCapacity',BigInteger),
                   Column('Manufacture',String(255)),
                   Column('Model',String(25)),
                   Column('Firmware',String(45)),
                   Column('TLAPartNbr',String(45)),
                   Column('Speed',Integer),
                   Column('RaidID',Integer,ForeignKey('RAIDGroup.RaidID')),
                   Column('FrameID',Integer,ForeignKey('Frame.FrameID')))

    sghosts = Table('SGHosts',metadata,
                    Column('id',Integer,autoincrement=True,primary_key=True),
                    Column('HostID',String(60),ForeignKey('Host.HostID')),
                    Column('SGWWN',String(255),ForeignKey('StorageGroup.SGWWN')))

    sgluns = Table('LUNStorage',metadata,
                   Column('id',Integer,autoincrement=True,primary_key=True),
                   Column('SGWWN',String(255),ForeignKey('StorageGroup.SGWWN')),
                   Column('HLU',Integer),
                   Column('LunID',Integer,ForeignKey('LUNS.LunID')))


    metadata.create_all(db)
    mapper(RAIDGroup,raidgroups)
    mapper(StorageGroup,storagegroups)
    mapper(Frame,frames)
    mapper(Host,hosts)
    mapper(LUN,luns,properties={
        'RAIDGroup': relation(RAIDGroup, backref=backref('luns')),
        })

    mapper(HostWWN,hostwwns,properties={
        'Host': relation(Host, backref=backref('WWNs')),
        })

    mapper(FrameSoftware,framesoftwares, properties={
        'Frame': relation(Frame, backref=backref('software')),
        })

    mapper(Drive,drives,properties ={
        'RAIDGROUP': relation(RAIDGroup,backref=backref('drives')),
        'Frame' : relation(Frame,backref=backref('drives'))
        })

    mapper(SGHost,sghosts, properties = {
        'Host' : relation(Host,backref=backref('SGHost')),
        'StorageGroup' : relation(StorageGroup,backref=backref('SGHost'))
        })

    mapper(SGLUN,sgluns,properties={
        'StorageGroup': relation(StorageGroup,backref=backref('SGLUN')),
        'luns': relation(LUN,backref=backref('SGLUN'))
        })

if __name__ == '__main__':
    setup_sqlite_tables()





