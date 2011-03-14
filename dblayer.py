from sqlalchemy import *
from sqlalchemy.orm import mapper, sessionmaker, relation, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
db = create_engine('sqlite:///:memory:',echo=False)

class RAIDGroup(Base):
    __tablename__ = 'raidgroups'

    RaidID = Column(Integer, primary_key=True,autoincrement=True)
    RaidGroupID = Column(Integer)
    Type = String(255)
    TotalSize = Integer
    FreeSize = Integer
    HighestContigFree = Integer

    def __init__(self):
        pass

    def __repr__(self):
        repr_items = [self.RaidID,self.RaidGroupID,self.Type,self.TotalSize,self.FreeSize,self.HighestContigFree]
        map(str(),repr_items)
        repr_string = "RAIDGroup<'%s'>" % ("', '".join(tuple(repr_items))

Base.metadata.create_all(db)
Session = sessionmaker(bind=db)
session = Session()


