#!/usr/bin/python
"""
acXMLreader.py : Reads in arrayconfig files from naviseccli and parses to SQLite database
"""

from xml.etree import ElementTree
import DBSetup as DBConfig
import re

xml_file = './testdata/arrayconfig.slough.xml'

namespace_uri_template = {"SAN": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_SAN_schema}%s",
                          "CLAR": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}%s",
                          "FILEMETADATA": "{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_Type_schema}%s"}



DBConfig.setup_sqlite_tables()

array_block_size = 512   # This seems to be the standard from EMC.....

# We're gonna strip a lot of tag names here..., and this Regex kinda looks like boobs
getTagName = re.compile(r'{.*}(.*)')

tree = ElementTree.parse(xml_file)
root = tree.getroot()

# Locate Attached Servers
attached_servers = tree.find('.//' + namespace_uri_template['SAN'] % ('Servers'))
for server in attached_servers:
    hostname = None
    ip = None
    manual_registration = None
    clariion_hostid = None

    for tag in server:
        if tag.attrib['type'] == 'Property':
            m = getTagName.match(tag.tag)
            serverAttrib = m.group(1)
            if 'HostName' in serverAttrib:
                hostname = tag.text
            elif 'HostIPAddress' in serverAttrib:
                ip = tag.text
            elif 'HostID' in serverAttrib:
                if 'MANUAL' in tag.text:
                    manual_registration = 1
                else:
                    manual_registration = 0
                clariion_hostid = tag.text

    new_server = DBConfig.Host(hostname,ip,manual_registration,clariion_hostid)
    DBConfig.session.add(new_server)
    DBConfig.session.commit()
    

# Find the Clariion
clariion_root = tree.find('.//' + namespace_uri_template['CLAR'] % ('CLARiiON'))
if clariion_root is not None:

    # our base information
    serial_num = clariion_root.find('.//' + namespace_uri_template['CLAR'] % 'SerialNumber')
    model = clariion_root.find('.//' + namespace_uri_template['CLAR'] % ('ModelNumber'))
    hwm = clariion_root.find(namespace_uri_template['CLAR'] % ('HighWatermark'))
    lwm = clariion_root.find(namespace_uri_template['CLAR'] % ('LowWatermark'))
    wwn = clariion_root.find(namespace_uri_template['CLAR'] % ('WWN'))


    # Frame Physical Configuration
    sps = clariion_root.find(namespace_uri_template['CLAR'] % ('Physicals') + '/' + namespace_uri_template['CLAR'] % ('StorageProcessors'))
    spa_ip = None
    spb_ip = None
    for sp in sps:
        name = sp.find(namespace_uri_template['CLAR'] % ('IPAddress'))
        IP = sp.find(namespace_uri_template['CLAR'] % ('Name'))
        if 'A' in name:
            spa_ip=IP.text
        else:
            spb_IP=IP.text

    clar = DBConfig.Frame(serial_num.text,model.text,spa_ip,spb_ip,hwm.text,lwm.text,wwn.text)
    DBConfig.session.add(clar)
    

    # Frame Software Info
    softwares = clariion_root.find(namespace_uri_template['CLAR'] % ('Softwares'))
    for installed_package in softwares:
        name = installed_package.find(namespace_uri_template['CLAR'] % ('Name'))

        if name.text.startswith('-'):
            continue

        ver = installed_package.find(namespace_uri_template['CLAR'] % ('Revision'))
        status = installed_package.find(namespace_uri_template['CLAR'] % ('IsActive'))

        if 'true' in status:
            status = 'Active'
        else:
            status = 'InActive'

        package = DBConfig.FrameSoftware(name.text,ver.text,status)
        clar.software.append(package)

    DBConfig.session.commit()

    
    drives = clariion_root.find(namespace_uri_template['CLAR'] % ('Physicals') + '/' + namespace_uri_template['CLAR'] % ('Disks'))
    for drive in drives:
        bus = None
        enclosure = None
        slot = None
        vendor = None
        capacity = None
        model = None
        firmware = None
        TLAPartNum = None
        speed = None
        location = None
        type = None

        for tag in drive:
            if tag.attrib['type'] == 'Property':
                m = getTagName.match(tag.tag)
                serverAttrib = m.group(1)
                if serverAttrib.endswith('Bus'):
                    bus = tag.text
                elif 'Enclosure' in serverAttrib:
                    enclosure = tag.text
                elif 'Slot' in serverAttrib:
                    slot = tag.text
                elif 'Type' in serverAttrib:
                    type = tag.text
                elif 'UserCapacity' in serverAttrib:
                    capacity = int(tag.text) * array_block_size
                elif 'Vendor' in serverAttrib:
                    vendor = tag.text
                elif serverAttrib.endswith('Product'):
                    model = tag.text
                elif 'ProductRevision' in serverAttrib:
                    firmware = tag.text
                elif 'TLANumber' in serverAttrib:
                    TLAPartNum = tag.text
                elif 'CurrentSpeed' in serverAttrib:
                    speed = tag.text

        
        location = '_'.join([str(bus),str(enclosure),str(slot)])

        new_drive = DBConfig.Drive(location,type,capacity,vendor,model,firmware,TLAPartNum,speed)
        DBConfig.session.add(new_drive)
        clar.drives.append(new_drive)

    DBConfig.session.commit()

    # Now we need to start working on the Logical items
    logical_root_node = clariion_root.find(namespace_uri_template['CLAR'] % ('Logicals'))

    # RAIDGroups
    raid_groups = logical_root_node.find(namespace_uri_template['CLAR'] % ('RAIDGroups'))

    rgtypes = {'32':'RAID5','1':'RAID1', '64': 'RAID1/0'}
    lun_wwn_map = dict()

    for group in raid_groups:
        rgid = None
        type = None
        totalsize = None
        freesize = None
        hgfs = None

        for tag in group:
            if tag.attrib['type'] == 'Property':
                m = getTagName.match(tag.tag)
                serverAttrib = m.group(1)
                if 'ID' in serverAttrib:
                    rgid = tag.text
                elif 'Type' in serverAttrib:
                    type = rgtypes[tag.text]
                elif 'Capacity' in serverAttrib:
                    totalsize = int(tag.text) * array_block_size
                elif 'FreeSpace' in serverAttrib:
                    freesize = int(tag.text) * array_block_size
                elif 'LargestUnbound' in serverAttrib:
                    hgfs = int(tag.text) * array_block_size

        new_raidgroup = DBConfig.RAIDGroup(rgid,type,totalsize,freesize,hgfs)
        DBConfig.session.add(new_raidgroup)
        DBConfig.session.commit()

        # Find all the disks that should be in the associated raid group
        raid_group_drive_root = group.find(namespace_uri_template['CLAR'] % ('Disks'))
        location_list = []
        for disk in raid_group_drive_root:
            bus = None
            enclosure = None
            slot = None
            for tag in disk:
                if 'Bus' in tag.tag:
                    bus = tag.text
                elif 'Enclosure' in tag.tag:
                    enclosure = tag.text
                elif 'Slot' in tag.tag:
                    slot = tag.text

            location_list.append('_'.join([str(bus),str(enclosure),str(slot)]))


        # Re-extract the drives from the DB that ar in the locations and set their RAID ID
        raid_group_drives = DBConfig.session.query(DBConfig.Drive).filter(DBConfig.Drive.Location.in_(location_list))
        for drive in raid_group_drives.all():
            drive.RaidID = new_raidgroup.RaidID

        DBConfig.session.commit()

        # Extract our LUNs and just keep the mapping for later insertion when we create them
        raidgroup_lun_root = group.find(namespace_uri_template['CLAR'] % ('LUNs'))
        for lun in raidgroup_lun_root:
            for tag in lun:
                if tag.tag.endswith('}WWN'):
                    lun_wwn_map[tag.text] = new_raidgroup.RaidGroupID

    # LUNs
    luns = logical_root_node.find(namespace_uri_template['CLAR'] % ('LUNs'))
    for lun in luns:
        alu = None
        name = None
        wwn = None
        state = None
        capacity = None
        ownership = None
        default_owner = None
        read_cache_enabled = None
        write_cache_enabled = None

        for tag in lun:
            if tag.attrib['type'] == 'Property':
                if tag.tag.endswith('}Number'):
                    alu = int(tag.text)
                elif '}Name' in tag.tag:
                    name = tag.text
                elif 'WWN' in tag.tag:
                    wwn = tag.text
                elif '}State' in tag.tag:
                    state = tag.text
                elif '}Capacity' in tag.tag:
                    capacity = int(tag.text) * array_block_size
                elif 'CurrentOwner' in tag.tag:
                    if int(tag.text) == 2:
                        ownership = 'B'
                    else:
                        ownership = 'A'
                elif 'DefaultOwner' in tag.tag:
                    if int(tag.text) == 2:
                        default_owner = 'B'
                    else:
                        default_owner = 'A'
                elif 'ReadCacheEnabled' in tag.tag:
                    if tag.text == 'true':
                        read_cache_enabled = 1
                    else:
                        read_cache_enabled = 0
                elif 'WriteCacheEnabled' in tag.tag:
                    if tag.text == 'true':
                        write_cache_enabled = 1
                    else:
                        write_cache_enabled = 0
                        
        new_lun = DBConfig.LUN(alu,name,wwn,state,capacity,ownership,default_owner,read_cache_enabled,write_cache_enabled)
        DBConfig.session.add(new_lun)

        raidgroup = DBConfig.session.query(DBConfig.RAIDGroup).filter(DBConfig.RAIDGroup.RaidGroupID==lun_wwn_map[wwn]).one()
        raidgroup.luns.append(new_lun)

    DBConfig.session.commit()

    # Handle Metaluns, they exist in the luns table, but have a couple flags set.
    metaluns = logical_root_node.find('.//{http://navisphere.us.dg.com/docs/Schemas/CommonClariionSchema/01/Common_CLARiiON_schema}MetaLUNInstances')
    for meta in metaluns:

        alu = None
        name = None
        wwn = None
        state = None
        capacity = None
        ownership = None
        default_owner = None
        for tag in meta:
            if tag.attrib['type'] == 'Property':
                if tag.tag.endswith('}Number'):
                    alu = int(tag.text)
                elif '}Name' in tag.tag:
                    name = tag.text
                elif 'WWN' in tag.tag:
                    wwn = tag.text
                elif '}State' in tag.tag:
                    state = tag.text
                elif 'Capacity' in tag.tag:
                    capacity = int(tag.text) * array_block_size
                elif 'CurrentOwner' in tag.tag:
                    if int(tag.text) == 2:
                        ownership = 'B'
                    else:
                        ownership = 'A'
                elif 'DefaultOwner' in tag.tag:
                    if int(tag.text) == 2:
                        default_owner = 'B'
                    else:
                        default_owner = 'A'

        # Add the LUN
        new_lun = DBConfig.LUN(alu,name,wwn,state,capacity,ownership,default_owner,-1,-1,1)
        DBConfig.session.add(new_lun)
        # Figger out the RAID group we're in, if at all?
        if wwn in lun_wwn_map:
            raidgroup = DBConfig.session.query(DBConfig.RAIDGroup).filter(DBConfig.RAIDGroup.RaidGroupID==lun_wwn_map[wwn]).one()
            raidgroup.luns.append(new_lun)

        DBConfig.session.commit()

        # Now we find our components
        component_luns = meta.findall('/'.join((namespace_uri_template['CLAR'] % ('Components'),
                                      namespace_uri_template['CLAR'] % ('Component'),
                                      namespace_uri_template['CLAR'] % ('LUNs'))))

        for lun in component_luns:
            wwns = lun.findall('.//' + namespace_uri_template['CLAR'] % ('WWN'))
            for wwn in wwns:
                member_lun = DBConfig.session.query(DBConfig.LUN).filter(DBConfig.LUN.WWN==wwn.text).one()
                member_lun.isMetaMember = 1

        DBConfig.session.commit()

    # Find our Connected HBAs
    connectedhbas = logical_root_node.find(namespace_uri_template['CLAR'] % ('ConnectedHBAs'))
    for connectedhba in connectedhbas:

        hostid = connectedhba.find('/'.join((namespace_uri_template['CLAR'] % ('AttachedSystems'),
                                            namespace_uri_template['CLAR'] % ('Server'),
                                            namespace_uri_template['CLAR'] % ('HostID'))))

        wwn = connectedhba.find(namespace_uri_template['CLAR'] % ('WWN'))
        adapter = DBConfig.HostWWN(wwn.text)
        DBConfig.session.add(adapter)
        server = DBConfig.session.query(DBConfig.Host).filter(DBConfig.Host.HostID==hostid.text).one()
        server.WWNs.append(adapter)

    DBConfig.session.commit()

    # Storage Groups
    #  These are a bit ugly, particularly because of all of the relational references.  Hopefully we can do the necessary
    #  Processing easily

    storage_groups = logical_root_node.find(namespace_uri_template['CLAR'] % ('StorageGroups'))
    for group in storage_groups:
        storage_group_name = None
        storage_group_wwn = None
        for tag in group:
            if tag.attrib['type'] == 'Property':
                if 'Name' in tag.tag:
                    storage_group_name = tag.text
                elif 'WWN' in tag.tag:
                    storage_group_wwn = tag.text

        new_storage_group = DBConfig.StorageGroup(storage_group_name,storage_group_wwn)
        DBConfig.session.add(new_storage_group)
        DBConfig.session.commit()

        hba_connections = group.findall('.//'+ namespace_uri_template['CLAR'] % ('ConnectedHBA') +
                                        '/' + namespace_uri_template['CLAR'] % ('WWN'))

        if hba_connections is not None:
            for connection in hba_connections:
                server = DBConfig.session.query(DBConfig.Host).filter(DBConfig.HostWWN.HostWWN==connection.text).all()
                newconn = DBConfig.SGHost(server[0].HostID,new_storage_group.SGWWN)
                DBConfig.session.add(newconn)
                new_storage_group.SGHost.append(newconn)

        DBConfig.session.commit()

        lu_connections = group.findall('.//' + namespace_uri_template['CLAR'] % ('LUs') + '/' + namespace_uri_template['CLAR'] % ('LU'))
        if lu_connections is not None:
            for lu in lu_connections:
                wwn = None
                hlu = None
                for lunconn in lu:
                    if 'WWN' in lunconn.tag:
                        wwn = lunconn.text
                    if 'Virtual' in lunconn.tag:
                        hlu = int(lunconn.text)

                new_storage_group_lun = DBConfig.SGLUN(new_storage_group.SGWWN,hlu)
                attached_lun = DBConfig.session.query(DBConfig.LUN).filter(DBConfig.LUN.WWN==wwn).all()
                new_storage_group_lun.luns = attached_lun[0]
                DBConfig.session.add(new_storage_group_lun)

        DBConfig.session.commit()
