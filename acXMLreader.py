#!/usr/bin/env python

import dblayer as db_layer
import re
import sys
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from xml.etree import ElementTree

# EMC Namespaces
old_namespace_uri_template = {"SAN": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_SAN_schema}%s",
                              "CLAR": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}%s",
                              "FILEMETADATA": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_Type_schema}%s"}

new_namespace_uri_template = {"SAN": "{http://navisphere.clrcase.lab.emc.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_SAN_schema}%s",
                              "CLAR": "{http://navisphere.clrcase.lab.emc.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}%s",
                              "FILEMETADATA": "{http://navisphere.clrcase.lab.emc.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_Type_schema}%s"}

emc_block_size = 512

emc_rg_types = {'32':'HotSpare',
                '6':'HotSpare',
                '1' : 'RAID5',
                '7' : 'RAID5',
                '0' : 'Unbound',
                '4' : 'RAID1',
                '64': 'RAID1/0'}

class acXMLreader():
    """reads and parses xml file into database structure"""

    sharedDB = None

    def __init__(self,array_config_xml=None,is_shared_db=True,db_engine=None,db_debug=False):

        # Setup our shared or non-shared DB connection
        db = None
        if not db_engine:  # We default to in-memory sqlite
            db_engine = "sqlite:///:memory:"

        if is_shared_db == True:
            if not acXMLreader.sharedDB:
                acXMLreader.sharedDB = create_engine(db_engine,echo=db_debug)
            db = acXMLreader.sharedDB
        else:
            db = create_engine(db_engine,echo=db_debug)

        # Run our database create and build our session
        db_layer.Base.metadata.create_all(db)
        Session = sessionmaker(bind=db)
        self.dbconn = Session()

        self.array_config_xml=array_config_xml
        self.schema_major_version = None
        self.schema_minor_version = None
        self.frame_serial = None
        self.rg_to_lun_map = {}
        self.ns_template = {}
        self.snapshots = {}

        try: 
            self.tree = ElementTree.parse(self.array_config_xml)
        except IOError:
            print "Unable to read and/or access file %s" % (self.array_config_xml)
            exit()

        root = self.tree.getroot()
        if 'clrcase' in root[0].tag:
             self.ns_template = new_namespace_uri_template
        else:
             self.ns_template = old_namespace_uri_template

        schema_major = self.tree.find('.//' + self.ns_template['FILEMETADATA'] % ('MajorVersion'))
        schema_minor = self.tree.find('.//' + self.ns_template['FILEMETADATA'] % ('MinorVersion'))
        self.schema_major_version = schema_major.text
        self.schema_minor_version = schema_minor.text

    def __repr__(self):
        return "acXMLreader<EMC XML Schema Major: %s Minor %s>" % (self.schema_major_version, self.schema_minor_version)

    def _locate_server_physical(self):
        """
        Locate attached physical servers in the configuration
        """
        # We need to keep track of our frame, so we can properly add it
        clariion = self.dbconn.query(db_layer.Frame).filter(db_layer.Frame.serial_number==self.frame_serial).one()

        attached_servers = self.tree.find('.//' + self.ns_template['SAN'] % ('Servers'))
        for server in attached_servers:
            new_server = db_layer.Host()

            for xml_tag in server:
                if xml_tag.tag.endswith('HostName'):
                    new_server.name = xml_tag.text
                elif xml_tag.tag.endswith('HostIPAddress'):
                    new_server.ip = xml_tag.text
                elif xml_tag.tag.endswith('HostID'):
                    new_server.id = xml_tag.text
                    if 'MANUAL' in xml_tag.text:
                        new_server.manual_registration = 1
                    else:
                        new_server.manual_registration = 0

            # Determine if this host is already in the table, if so we just set
            # the new host to be the existing one so we can add the frame
            # association
            host_lookup = self.dbconn.query(db_layer.Host).filter(db_layer.Host.id==new_server.id)
            if host_lookup.count() == 1:
                new_server = host_lookup.one()
            else :
                self.dbconn.add(new_server)

            # Add our frame association
            new_server.frames.append(clariion)
            self.dbconn.commit()
    
    def _locate_clariion_info(self):
        """
        Locate and create objects for base frame information and software
        """
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        if clariion_root is not None:
            clar = db_layer.Frame()

            # Base info
            serial_num = clariion_root.find(self.ns_template['CLAR'] % 'SerialNumber')
            model = clariion_root.find(self.ns_template['CLAR'] % ('ModelNumber'))
            hwm = clariion_root.find(self.ns_template['CLAR'] % ('HighWatermark'))
            lwm = clariion_root.find(self.ns_template['CLAR'] % ('LowWatermark'))
            wwn = clariion_root.find(self.ns_template['CLAR'] % ('WWN'))

            clar.serial_number = serial_num.text
            self.frame_serial = serial_num.text
            clar.model=model.text
            clar.cache_hwm = hwm.text
            clar.cache_lwm = lwm.text
            clar.wwn = wwn.text

            # SP IP addresses
            sps = clariion_root.find(self.ns_template['CLAR'] % ('Physicals') + '/' + self.ns_template['CLAR'] % ('StorageProcessors'))
            for sp in sps:
                ip = sp.find(self.ns_template['CLAR'] % ('IPAddress'))
                name = sp.find(self.ns_template['CLAR'] % ('Name'))
                if 'A' in name.text:
                    clar.spa_ip=ip.text
                else:
                    clar.spb_ip=ip.text

            self.dbconn.add(clar)
            self.dbconn.commit()

            # Installed Frame Software
            softwares = clariion_root.find(self.ns_template['CLAR'] % ('Softwares'))
            for installed_package in softwares:
                name = installed_package.find(self.ns_template['CLAR'] % ('Name'))

                if name.text.startswith('-'):
                    continue

                ver = installed_package.find(self.ns_template['CLAR'] % ('Revision'))
                status = installed_package.find(self.ns_template['CLAR'] % ('IsActive'))

                if 'true' in status.text:
                    status = 'Active'
                else:
                    status = 'InActive'

                package = db_layer.FrameSoftware()
                package.name = name.text
                package.rev = ver.text
                package.frame = clar
                package.status= status

                self.dbconn.add(package)

            self.dbconn.commit() 

    def _locate_clariion_drives(self):
        clariion = self.dbconn.query(db_layer.Frame).filter(db_layer.Frame.serial_number==self.frame_serial).one()

        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        if clariion_root is not None:
            drives = clariion_root.find(self.ns_template['CLAR'] % ('Physicals') + '/' + self.ns_template['CLAR'] % ('Disks'))
            for drive in drives:
		capacity = drive.find(self.ns_template['CLAR'] % ('UserCapacityInBlocks'))
                if int(capacity.text) == 0:
                    continue;

                new_drive = db_layer.Drive()

                bus = None
                enc = None
                slot = None

                for xml_tag in drive:
                    if xml_tag.tag.endswith('Bus'):
                        bus = xml_tag.text
                    elif xml_tag.tag.endswith('Enclosure'):
                        enc = xml_tag.text
                    elif xml_tag.tag.endswith('Slot'):
                        slot = xml_tag.text
                    elif xml_tag.tag.endswith('Type'):
                        new_drive.drive_type = xml_tag.text
                    elif xml_tag.tag.endswith('UserCapacityInBlocks'):
                        if int(xml_tag.text) < 10000000:   # Correct for BUG in some versions on Unisphere CLI
                            new_drive.capacity = int(xml_tag.text) * 1024 * 1024
                        else:
                            new_drive.capacity = int(xml_tag.text) * emc_block_size
                    elif xml_tag.tag.endswith('Vendor'):
                        new_drive.manufacturer = xml_tag.text
                    elif xml_tag.tag.endswith('Product'):
                        new_drive.model = xml_tag.text
                    elif xml_tag.tag.endswith('ProductRevision'):
                        new_drive.firmware = xml_tag.text
                    elif xml_tag.tag.endswith('TLANumber'):
                        new_drive.tla_part_num = xml_tag.text
                    elif xml_tag.tag.endswith('CurrentSpeed'):
                        new_drive.speed = int(xml_tag.text)

                new_drive.location = '_'.join([str(bus),str(enc),str(slot)])
                new_drive.frame = clariion

                self.dbconn.add(new_drive)
            self.dbconn.commit()

    def _locate_logical_raidgroups(self):
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(self.ns_template['CLAR'] % ('Logicals'))
        raid_groups = logical_root_node.find(self.ns_template['CLAR'] % ('RAIDGroups'))

        for group in raid_groups:

            new_raid_group = db_layer.RAIDGroup()
            for xml_tag in group:
                if xml_tag.tag.endswith('}ID'):
                    new_raid_group.group_number = int(xml_tag.text)
                elif xml_tag.tag.endswith('Type'):
                    new_raid_group.raid_type = emc_rg_types[xml_tag.text]
                elif xml_tag.tag.endswith('Capacity'):
                    new_raid_group.total_size = int(xml_tag.text)
                elif xml_tag.tag.endswith('FreeSpace'):
                    new_raid_group.free_size = int(xml_tag.text)
                elif xml_tag.tag.endswith('LargestUnboundSegmentSize'):
                    new_raid_group.highest_contig_free = int(xml_tag.text)

            self.dbconn.add(new_raid_group)
            self.dbconn.commit()

            # Locate associated disks
            drive_root = group.find(self.ns_template['CLAR'] % ('Disks'))
            location_list = []
            for disk in drive_root:
                bus = None
                enclosure = None
                slot = None
                for tag in disk:
                    if tag.tag.endswith('Bus'):
                         bus=tag.text
                    elif tag.tag.endswith('Enclosure'):
                        enclosure = tag.text
                    elif tag.tag.endswith('Slot'):
                        slot = tag.text

                location_list.append('_'.join([str(bus),str(enclosure),str(slot)]))

            # Pull our physical drives from the DB that are in the locations and set the RAID ID
	        raid_group_drives = self.dbconn.query(db_layer.Drive).filter(db_layer.Drive.location.in_(location_list))
	        for drive in raid_group_drives.all():
	            drive.raidgroup = new_raid_group
            self.dbconn.commit()

            # Find our LUNs and map them for later assignment to the RAID group, note we have to check for unbound RAID groups
            raid_group_lun_root = group.find(self.ns_template['CLAR'] % ('LUNs'))
            if raid_group_lun_root is not None:
                for lun in raid_group_lun_root:
                    for tag in lun:
                        if tag.tag.endswith('}WWN'):
                            self.rg_to_lun_map[tag.text] = new_raid_group.group_number
   

    def _locate_logical_luns(self):
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(self.ns_template['CLAR'] % ('Logicals'))    
        luns_node = logical_root_node.find(self.ns_template['CLAR'] % ('LUNs'))

        for lun in luns_node:
            new_lun = db_layer.LUN()
            for tag in lun:
                if tag.tag.endswith('Number'):
                    new_lun.alu = int(tag.text)
                elif tag.tag.endswith('}Name'):
                    new_lun.name = tag.text
                elif tag.tag.endswith('WWN'):
                    new_lun.wwn = tag.text
                elif tag.tag.endswith('}State'):
                    new_lun.state = tag.text
                elif tag.tag.endswith('}Capacity'):
                    new_lun.capacity = int(tag.text) * emc_block_size
                elif tag.tag.endswith('CurrentOwner'):
                    if int(tag.text) == 2:
                        new_lun.current_owner = 'B'
                    else:
                        new_lun.current_owner = 'A'
                elif tag.tag.endswith('DefaultOwner'):
                    if int(tag.text) == 2:
                        new_lun.default_owner='B'
                    else:
                        new_lun.default_owner='A'
                elif tag.tag.endswith('ReadCacheEnabled'):
                    if tag.text == 'true':
                        new_lun.is_read_cache_enabled = 1
                    else:
                        new_lun.is_read_cache_enabled = 0
                elif tag.tag.endswith('WriteCacheEnabled'):
                    if tag.text == 'true':
                        new_lun.is_write_cache_enabled = 1
                    else:
                        new_lun.is_write_cache_enabled = 0

            self.dbconn.add(new_lun)

            # Update the RAID group config with this lun
            raid_group = self.dbconn.query(db_layer.RAIDGroup).filter(
                                      db_layer.RAIDGroup.group_number==self.rg_to_lun_map[new_lun.wwn]).first()

            raid_group.luns.append(new_lun)

            self.dbconn.commit()

    def _locate_meta_luns(self):
        # MetaLUNs are added into the LUNs table, but have the isMeta,
        # isMetaHead, and MetaHead properties set        
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(self.ns_template['CLAR'] % ('Logicals'))    
        metaluns = logical_root_node.find('.//' + self.ns_template['CLAR'] % ('MetaLUNInstances'))

        if metaluns is None:   # If there aren't any metas, we just bail
            return    

        for meta in metaluns:
            new_meta_head = db_layer.LUN()
            new_meta_head.is_meta_head = 1
            for tag in meta:
                if tag.tag.endswith('Number'):
                    new_meta_head.alu = int(tag.text)
                elif tag.tag.endswith('}Name'):
                    new_meta_head.name = tag.text
                elif tag.tag.endswith('WWN'):
                    new_meta_head.wwn = tag.text
                elif tag.tag.endswith('}State'):
                    new_meta_head.state = tag.text
                elif tag.tag.endswith('}Capacity'):
                    new_meta_head.capacity = int(tag.text) * emc_block_size
                elif tag.tag.endswith('CurrentOwner'):
                    if int(tag.text) == 2:
                        new_meta_head.current_owner = 'B'
                    else:
                        new_meta_head.current_owner = 'A'
                elif tag.tag.endswith('DefaultOwner'):
                    if int(tag.text) == 2:
                        new_meta_head.default_owner='B'
                    else:
                        new_meta_head.default_owner='A'

                if new_meta_head.state == None:
                    new_meta_head.state="Bound"

            self.dbconn.add(new_meta_head)
            
            if new_meta_head.wwn in self.rg_to_lun_map:
                raid_group = self.dbconn.query(db_layer.RAIDGroup).filter(
                                      db_layer.RAIDGroup.group_number==self.rg_to_lun_map[new_meta_head.wwn]).first()
           
                raid_group.luns.append(new_meta_head)

            self.dbconn.commit()

            component_luns = meta.findall('/'.join((self.ns_template['CLAR'] % ('Components'),
                                      self.ns_template['CLAR'] % ('Component'),
                                      self.ns_template['CLAR'] % ('LUNs'))))

            for lun in component_luns:
                wwns = lun.findall('.//' + self.ns_template['CLAR'] % ('WWN'))
                for wwn in wwns:
                    member_lun = self.dbconn.query(db_layer.LUN).filter(db_layer.LUN.wwn==wwn.text).one()
                    member_lun.is_meta_member = 1
                    member_lun.meta_head = new_meta_head.wwn

                self.dbconn.commit()

    def _locate_connected_hbas(self):
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(self.ns_template['CLAR'] % ('Logicals'))    
        connected_hbas = logical_root_node.find(self.ns_template['CLAR']
                % ('ConnectedHBAs'))

        for hba in connected_hbas:

            hostid = hba.find('/'.join((self.ns_template['CLAR'] % ('AttachedSystems'),
                                            self.ns_template['CLAR'] % ('Server'),
                                            self.ns_template['CLAR'] % ('HostID'))))

            wwn = hba.find(self.ns_template['CLAR'] % ('WWN'))

            if ':' in hostid.text:   # Unregistered HBA
		continue

            try:
                server = self.dbconn.query(db_layer.Host).filter(db_layer.Host.id==hostid.text).one()
            except NoResultFound, e:
                print "Warning:  No HostID found for WWN: %s" % (wwn.text)
                continue

            adapter = db_layer.HostWWN()
            adapter.wwn = wwn.text
            server.wwns.append(adapter)
            self.dbconn.add(adapter)

        self.dbconn.commit()

  
    def _locate_storage_groups(self):
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(self.ns_template['CLAR'] % ('Logicals'))    
        storage_groups = logical_root_node.find(self.ns_template['CLAR'] % ('StorageGroups'))

        for group in storage_groups:
            new_storage_group = db_layer.StorageGroup()

            for tag in group:
                if tag.tag.endswith('Name'):
                    new_storage_group.name = tag.text
                elif tag.tag.endswith('WWN'):
                    new_storage_group.wwn = tag.text

            if new_storage_group.name.startswith('~') or new_storage_group.name.startswith('FAR_'): 
                continue

            self.dbconn.add(new_storage_group)
            self.dbconn.commit()

            # find all our hosts and add them to the storage group
            sg_hba_connections = group.findall('.//' + self.ns_template['CLAR'] % ('ConnectedHBA') +
                                                '/' + self.ns_template['CLAR'] % ('WWN'))

            if sg_hba_connections is not None:
                for connection in sg_hba_connections:
                    server = self.dbconn.query(db_layer.Host).filter(db_layer.HostWWN.host_id==db_layer.Host.id).filter(db_layer.HostWWN.wwn==connection.text).first()

                    new_storage_group.hosts.append(server)
                    self.dbconn.commit()

            sg_lu_connections = group.findall('.//' + self.ns_template['CLAR'] % ('LUs') +
                                              '/' + self.ns_template['CLAR'] % ('LU'))

            if sg_lu_connections is not None:
                for lu in sg_lu_connections:
                    lun_wwn = None
                    hlu = None

                    for lun_connection in lu:

                        if lun_connection.tag.endswith('WWN'):
                            lun_wwn = lun_connection.text
                        elif 'Virtual' in lun_connection.tag:
                            hlu = int(lun_connection.text)

                    # Set the LUN parameters and the storage group
                    if lun_wwn not in self.snapshots:
                        attached_lun = self.dbconn.query(db_layer.LUN).filter(db_layer.LUN.wwn==lun_wwn).one()
                        attached_lun.hlu = hlu
                        new_storage_group.luns.append(attached_lun) 

                    self.dbconn.commit()

    def _locate_snapshot_luns(self):
        # We're currently throwing these away
        # TODO: properly handle snapshots with a table in the DB
        clariion_root = self.tree.find('.//' + self.ns_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(self.ns_template['CLAR'] % ('Logicals'))
        snapshots = logical_root_node.findall('.//' + self.ns_template['CLAR'] % ('SnapViews') + 
                                             '/' + self.ns_template['CLAR'] % ('SnapView') + 
                                             '/' + self.ns_template['CLAR'] % ('SnapShots') +
                                             '/' + self.ns_template['CLAR'] % ('SnapShot'))

        for snap in snapshots:
            wwn = snap.findtext('./' + self.ns_template['CLAR'] % ('WWN'))
            self.snapshots[wwn] = 1

    def parse(self):
        self._locate_clariion_info()
        self._locate_server_physical()
        self._locate_clariion_drives()
        self._locate_logical_raidgroups()
        self._locate_logical_luns()
        self._locate_meta_luns()
        self._locate_snapshot_luns()
        self._locate_connected_hbas()
        self._locate_storage_groups()

if __name__ == "__main__":
    clar = acXMLreader(sys.argv[1])
    clar.parse()
