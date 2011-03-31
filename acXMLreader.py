#!/usr/bin/env python

from xml.etree import ElementTree
import dblayer as db_layer
import re

# EMC Namespaces
namespace_uri_template = {"SAN": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_SAN_schema}%s",
                          "CLAR": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}%s",
                          "FILEMETADATA": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_Type_schema}%s"}


emc_block_size = 512

emc_rg_types = {'32':'HotSpare',
                '1' : 'RAID5',
                '64': 'RAID1/0'}

class acXMLreader():
    """reads and parses xml file into database structure"""

    def __init__(self,array_config_xml=None):

        self.array_config_xml=array_config_xml
        self.schema_major_version = None
        self.schema_minor_version = None
        self.dbconn = db_layer.session
        self.frame_serial = None
        self.rg_to_lun_map = dict()

        try: 
            self.tree = ElementTree.parse(self.array_config_xml)
        except IOError:
            print "Unable to read and/or access file %s" % (self.array_config_xml)
            exit()

        schema_major = self.tree.find('.//' + namespace_uri_template['FILEMETADATA'] % ('MajorVersion'))
        schema_minor = self.tree.find('.//' + namespace_uri_template['FILEMETADATA'] % ('MinorVersion'))
        self.schema_major_version = schema_major.text
        self.schema_minor_version = schema_minor.text

    def __repr__(self):
        return "acXMLreader<EMC XML Schema Major: %s Minor %s>" % (self.schema_major_version, self.schema_minor_version)

    def _locate_server_physical(self):
        """
        Locate attached physical servers in the configuration
        """
        attached_servers = self.tree.find('.//' + namespace_uri_template['SAN'] % ('Servers'))
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

            self.dbconn.add(new_server)
            self.dbconn.commit()
    
    def _locate_clariion_info(self):
        """
        Locate and create objects for base frame information and software
        """
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        if clariion_root is not None:
            clar = db_layer.Frame()

            # Base info
            serial_num = clariion_root.find(namespace_uri_template['CLAR'] % 'SerialNumber')
            model = clariion_root.find(namespace_uri_template['CLAR'] % ('ModelNumber'))
            hwm = clariion_root.find(namespace_uri_template['CLAR'] % ('HighWatermark'))
            lwm = clariion_root.find(namespace_uri_template['CLAR'] % ('LowWatermark'))
            wwn = clariion_root.find(namespace_uri_template['CLAR'] % ('WWN'))

            clar.serial_number = serial_num.text
            self.frame_serial = serial_num.text
            clar.model=model.text
            clar.cache_hwm = hwm.text
            clar.cache_lwm = lwm.text
            clar.wwn = wwn.text

            # SP IP addresses
            sps = clariion_root.find(namespace_uri_template['CLAR'] % ('Physicals') + '/' + namespace_uri_template['CLAR'] % ('StorageProcessors'))
            for sp in sps:
                ip = sp.find(namespace_uri_template['CLAR'] % ('IPAddress'))
                name = sp.find(namespace_uri_template['CLAR'] % ('Name'))
                if 'A' in name.text:
                    clar.spa_ip=ip.text
                else:
                    clar.spb_ip=ip.text

            self.dbconn.add(clar)
            self.dbconn.commit()

            # Installed Frame Software
            softwares = clariion_root.find(namespace_uri_template['CLAR'] % ('Softwares'))
            for installed_package in softwares:
                name = installed_package.find(namespace_uri_template['CLAR'] % ('Name'))

                if name.text.startswith('-'):
                    continue

                ver = installed_package.find(namespace_uri_template['CLAR'] % ('Revision'))
                status = installed_package.find(namespace_uri_template['CLAR'] % ('IsActive'))

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

        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        if clariion_root is not None:
            drives = clariion_root.find(namespace_uri_template['CLAR'] % ('Physicals') + '/' + namespace_uri_template['CLAR'] % ('Disks'))
            for drive in drives:

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
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))
        raid_groups = logical_root_node.find(namespace_uri_template['CLAR'] % ('RAIDGroups'))

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
            drive_root = group.find(namespace_uri_template['CLAR'] % ('Disks'))
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

            # Find our LUNs and map them for later assignment to the RAID group
            raid_group_lun_root = group.find(namespace_uri_template['CLAR'] % ('LUNs'))
            for lun in raid_group_lun_root:
                for tag in lun:
                    if tag.tag.endswith('}WWN'):
                        self.rg_to_lun_map[tag.text] = new_raid_group.group_number
   

    def _locate_logical_luns(self):
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))    
        luns_node = logical_root_node.find(namespace_uri_template['CLAR'] % ('LUNs'))

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
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))    
        metaluns = logical_root_node.find('.//{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}MetaLUNInstances')

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

            self.dbconn.add(new_meta_head)
            
            if new_meta_head.wwn in self.rg_to_lun_map:
                raid_group = self.dbconn.query(db_layer.RAIDGroup).filter(
                                      db_layer.RAIDGroup.group_number==self.rg_to_lun_map[new_meta_head.wwn]).first()
           
                raid_group.luns.append(new_meta_head)

            self.dbconn.commit()

            component_luns = meta.findall('/'.join((namespace_uri_template['CLAR'] % ('Components'),
                                      namespace_uri_template['CLAR'] % ('Component'),
                                      namespace_uri_template['CLAR'] % ('LUNs'))))

            for lun in component_luns:
                wwns = lun.findall('.//' + namespace_uri_template['CLAR'] % ('WWN'))
                for wwn in wwns:
                    member_lun = self.dbconn.query(db_layer.LUN).filter(db_layer.LUN.wwn==wwn.text).one()
                    member_lun.is_meta_member = 1
                    member_lun.meta_head = new_meta_head.wwn

                self.dbconn.commit()

    def _locate_connected_hbas(self):
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))    
        connected_hbas = logical_root_node.find(namespace_uri_template['CLAR']
                % ('ConnectedHBAs'))

        for hba in connected_hbas:

            hostid = hba.find('/'.join((namespace_uri_template['CLAR'] % ('AttachedSystems'),
                                            namespace_uri_template['CLAR'] % ('Server'),
                                            namespace_uri_template['CLAR'] % ('HostID'))))

            print "**** - FINDING SERVER"
            server = self.dbconn.query(db_layer.Host).filter(db_layer.Host.id==hostid.text).one()
	    print "FOUND SERVER!"
            wwn = hba.find(namespace_uri_template['CLAR'] % ('WWN'))
            adapter = db_layer.HostWWN()
            adapter.wwn = wwn.text
            server.wwns.append(adapter)
            self.dbconn.add(adapter)

        self.dbconn.commit()

  
    def _locate_storage_groups(self):
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))    
        storage_groups = logical_root_node.find(namespace_uri_template['CLAR'] % ('StorageGroups'))

        for group in storage_groups:
            new_storage_group = db_layer.StorageGroup()

            for tag in group:
                if tag.tag.endswith('Name'):
                    new_storage_group.name = tag.text
                elif tag.tag.endswith('WWN'):
                    new_storage_group.wwn = tag.text

            if new_storage_group.name.startswith('~'): 
                continue

            self.dbconn.add(new_storage_group)
            self.dbconn.commit()

            # find all our hosts and add them to the storage group
            sg_hba_connections = group.findall('.//' + namespace_uri_template['CLAR'] % ('ConnectedHBA') +
                                                '/' + namespace_uri_template['CLAR'] % ('WWN'))

            if sg_hba_connections is not None:
                for connection in sg_hba_connections:
                    server = self.dbconn.query(db_layer.Host).filter(db_layer.HostWWN.host_id==db_layer.Host.id).filter(db_layer.HostWWN.wwn==connection.text).first()

                    new_storage_group.host.append(server)
                    self.dbconn.commit()

            sg_lu_connections = group.findall('.//' + namespace_uri_template['CLAR'] % ('LUs') +
                                              '/' + namespace_uri_template['CLAR'] % ('LU'))

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
                    attached_lun = self.dbconn.query(db_layer.LUN).filter(db_layer.LUN.wwn==lun_wwn).one()
                    attached_lun.hlu = hlu
                    new_storage_group.luns.append(attached_lun) 
                    self.dbconn.commit()

    def parse(self):
        self._locate_server_physical()
        self._locate_clariion_info()
        self._locate_clariion_drives()
        self._locate_logical_raidgroups()
        self._locate_logical_luns()
        self._locate_meta_luns()
        self._locate_connected_hbas()
        self._locate_storage_groups()



if __name__ == "__main__":
    print "Parsing san and nas"
    clar = acXMLreader('./testdata/arrayconfig.sannas.xml')
    clar.parse()
    print "Parsing Nas only"
    clar2 = acXMLreader('./testdata/arrayconfig.nasonly.xml')
    clar2.parse()
