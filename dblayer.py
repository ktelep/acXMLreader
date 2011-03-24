from sqlalchemy import *
from sqlalchemy.orm import mapper, sessionmaker, relation, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
#db = create_engine('sqlite:///:memory:', echo=True)
db = create_engine('sqlite:////tmp/test.db', echo=False)


class RAIDGroup(Base):
    __tablename__ = 'RAIDGroup'

    rid = Column('RaidID', Integer, primary_key=True, autoincrement=True)
    group_number = Column('RaidGroupID', Integer)
    raid_type = Column('Type', String(25))
    total_size = Column('TotalSize', BigInteger)
    free_size = Column('FreeSize', BigInteger)
    highest_contig_free = Column('HighestContigFree', BigInteger)
    luns = relation('LUN', backref='raid_group')

    def __init__(self):
        pass

    def __repr__(self):
        repr_items = [self.raid_rid, self.raid_group_id, self.raid_type,
                      self.total_size, self.free_size,
                      self.highest_contig_free]

        repr_string = "', '".join(tuple(map(str, repr_items)))
        return "RAIDGroup<'%s'>" % repr_string


class StorageGroup(Base):
    __tablename__ = 'StorageGroup'

    name = Column('SGName', String(255))
    category = Column('category', String(255))
    wwn = Column('SGWWN', String(255), primary_key=True)
    luns = relation('LUN', backref='storage_group')
    host = relation('Host', backref='storage_group')

    def __init__(self):
        pass

    def __repr__(self):
        repr_items = [self.storage_group_name, self.storage_group_wwn]
        repr_string = "', '".join(tuple(map(str, repr_items)))
        return "StorageGroup<'%s'>" % (repr_string)


class Frame(Base):
    __tablename__ = 'Frame'

    rid = Column('FrameID', Integer, primary_key=True, autoincrement=True)
    serial_number = Column('SerialNumber', String(25))
    model = Column('Model', String(25))
    spa_ip = Column('SPA', String(100))
    spb_ip = Column('SPB', String(100))
    cache_hwm = Column('CacheHWM', Integer)
    cache_lwm = Column('CacheLWM', Integer)
    wwn = Column('WWN', String(255))

    def __init__(self):
        pass

    def __repr__(self):
        repr_items = [self.serial_number, self.model, self.spa_ip, self.spb_ip]
        repr_string = "', '".join(tuple(map(str, repr_items)))
        return "Frame<'%s'>" % repr_string


class HostWWN(Base):
    __tablename__ = 'hostwwns'

    id = Column(Integer, autoincrement=True, primary_key=True)
    host_id = Column(String(60), ForeignKey('Host.HostID'))
    host = relation('Host', backref='wwns')
    wwn = Column('HostWWN', String(60))

    def __init__(self):
        pass

    def __repr__(self):
        return "HostWWN<'%s', '%s'>" % (wwn, host_id)


class Host(Base):
    __tablename__ = 'Host'

    id = Column('HostID', String(60), primary_key=True)
    name = Column('Name', String(60))
    ip = Column('IP', String(20))
    manual_registration = ('ManualReg', SMALLINT)
    storage_group_wwn = Column('StorageGroup', String(255),
                               ForeignKey('StorageGroup.SGWWN'))

    def __init__(self):
        pass

    def __repr__(self):
        return "Host<'%s', '%s', '%s', ManReg: %s>" % (
                self.id, self.name, self.ip, str(self.manual_registration))


class LUN(Base):
    __tablename__ = 'LUNS'

    wwn = Column('WWN', String(50), primary_key=True)
    alu = Column('ALU', Integer)
    name = Column('Name', String(50))
    state = Column('State', String(50))
    capacity = Column('Capacity', BigInteger)
    current_owner = Column('Ownership', String(5))
    default_owner = Column('DefaultOwner', String(5))
    is_read_cache_enabled = Column('ReadCacheEnabled', SMALLINT)
    is_write_cache_enabled = Column('WriteCacheEnabled', SMALLINT)
    is_meta_head = Column('isMetaHead', SMALLINT)
    is_meta_member = Column('isMetaMember', SMALLINT)
    meta_head = Column('MetaHead', String(50))
    raidgroup_id = Column('RaidID', Integer, ForeignKey('RAIDGroup.RaidID'))
    storage_group_wwn = Column('StorageGroup', Integer,
                               ForeignKey('StorageGroup.SGWWN'))
    hlu = Column('HLU', Integer)


    def __init__(self):
        pass

    def __repr__(self):
        return "LUN<'%s','%s','%s','%s'>" % (
                self.wwn, str(self.alu), self.name, str(self.capacity))


class FrameSoftware(Base):
    __tablename__ = 'FrameSoftware'

    rid = Column(Integer, autoincrement=True, primary_key=True)
    frame_id = Column('FrameID', Integer, ForeignKey('Frame.FrameID'))
    frame = relation('Frame',  backref='software')
    name = Column('Name', String(25))
    rev = Column('Revision', String(20))
    status = Column('Status', String(25))

    def __init__(self):
        pass

    def __repr__(self):
        return "FrameSoftware<'%s','%s','%s'>" % (
                self.name, self.rev, self.status)


class Drive(Base):
    __tablename__ = 'Drive'

    rid = Column('DriveID', Integer, primary_key=True, autoincrement=True)
    location = Column('Location', String(25))
    drive_type = Column('Type', String(25))
    capacity = Column('RawCapacity', BigInteger)
    manufacturer = Column('Manufacture', String(255))
    model = Column('Model', String(25))
    firmware = Column('Firmware', String(45))
    tla_part_num = Column('TLAPartNbr', String(45))
    speed = Column('Speed', Integer)
    raidgroup_id = Column('RaidID', Integer, ForeignKey('RAIDGroup.RaidID'))
    frame_id = Column('FrameID', Integer, ForeignKey('Frame.FrameID'))
    raidgroup = relation('RAIDGroup', backref='drives')
    frame = relation('Frame', backref='drives')

    def __init__(self):
        pass

    def __repr__(self):
        return "Drive<'%s', '%s', '%s'>" % (
                self.location, self.drive_type, str(self.capacity))


Base.metadata.create_all(db)
Session = sessionmaker(bind=db)
session = Session()
