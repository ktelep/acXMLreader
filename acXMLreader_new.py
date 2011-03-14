#!/usr/bin/python

from xml.etree import ElementTree
import dblayer as db_layer
import re

# EMC Namespaces
namespace_uri_template = {"SAN": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_SAN_schema}%s",
                          "CLAR": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}%s",
                          "FILEMETADATA": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_Type_schema}%s"}

# EMC has standardized on a 512-byte block size for their data, but for some
# reason it looks like there are some arrays that take 1024...  
# TODO: Need to figure out which arrays are 512 byte blocks vs. 1024
#       Maybe when we pull drives, we see if there's a sizeMB tag and divide it
#       by blocks?

emc_block_size = 1024
emc_rg_types = {'32':'RAID5',
                '1' : 'RAID1',
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

    def _locate_logical_raidgroups()
        clariion_root = self.tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
        logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))
        raid_groups = logical_root_node.find(namespace_uri_template['CLAR'] % ('RAIDGroups'))

        new_raid_group = db_layer.RAIDGroup()

        for group in raid_groups:
            for xml_tag in group:
                if xml_tag.tag.endswith('ID'):
                    new_raid_group.group_number = xml_tag.text
                elif xml_tag.tag.endswith('Type'):
                    new_raid_group.raid_type = emc_rg_types[xml_tag.text]
                elif xml_tag.tag.endswith('Capacity'):
                    new_raid_group.total_size = int(xml_tag.text)
                elif xml_tag.tag.endswith('FreeSpace'):
                    new_raid_group.free_size = int(xml_tag.text)
                elif xml-tag.tag.endswith('LargestUnbound'):
                    new_raid_group.highest_contig_free = int(xml_tag.text)

            self.dbconn.add(new_raid_group)
            self.dbconn.commit()

            # Locate associated disks





    def parse(self):
        self._locate_server_physical()
        self._locate_clariion_info()
        self._locate_clariion_drives()

if __name__ == "__main__":
    clar = acXMLreader('/Users/ktelep/src/acXMLreader/testdata/arrayconfig.sannas.xml')
    clar.parse()