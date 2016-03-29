#!/usr/bin/env python
#
# Copyright (c) 2016, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import collections
import string
import random
import time
import sys
import os

import psi_utils
import psi_ssh

libcloud_path = os.path.join(os.path.abspath('.'), 'libcloud')
sys.path.insert(0, libcloud_path)

try:
    from libcloud.compute.drivers import vpsnet
    import libcloud.security
except ImportError as error:
    raise error

libcloud.security.CA_CERTS_PATH = ['./libcloud/cacerts/ca-bundle.crt']
if not os.path.exists(libcloud.security.CA_CERTS_PATH[0]):
    print '''
    Could not find valid certificate path.
    See: https://libcloud.readthedocs.org/en/latest/other/ssl-certificate-validation.html
    '''


def get_vpsnet_connection(vpsnet_account):
    '''
        This connects to libclouds VPSNet driver and returns a connection
    '''
    vpsnet_conn = vpsnet.VPSNetNodeDriver(
        key=vpsnet_account.account_id,
        secret=vpsnet_account.api_key,
        secure=True)
    return vpsnet_conn


def refresh_credentials(vpsnet_account, ip_address, generated_root_password,
                        new_root_password, new_stats_password):
    ssh = psi_ssh.make_ssh_session(
        ip_address, vpsnet_account.base_ssh_port, 
        'root', generated_root_password, None, None,
        )
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (
        vpsnet_account.base_stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')


def wait_on_action(vpsnet_conn, node, interval=30):
    for attempt in range(10):
        node = vpsnet_conn.get_ssd_node(node.id)
        if 'running' in node.state.lower():
            return True
        else:
            print 'node state : %s.  Trying again in %s' % (node.state, interval)
            time.sleep(int(interval))
    
    return False


def get_region_name(region):
    '''
        65:  LON-K-SSD:                     London GB
        66:  SLC-G-SSD:                     Salt Lake City US
        91:  LON-M-SSD:                     London GB
        113: SLC-H-SSD:                     Salt Lake City US
        116: (New York) - NYC-A-SSD:        US
        117: (Los Angeles) - LAX-A-SSD:     US
        118: SLC-K-SSD:                     Salt Lake City US
        119: TOR-A-SSD:                     Toronto CA
        120: AMS-B-SSD:                     Amsterdam NL
        121: LON-P-SSD:                     London GB
        124: (Miami) - MIA-A-SSD:           Miami US
        125: (Chicago) - CHI-C-SSD:         Chicago US
    '''
    if region['cloud_id'] in [65, 91, 121]:
        return 'GB'
    if region['cloud_id'] in [66, 113, 116, 117, 118, 124, 125]:
        return 'US'
    if region['cloud_id'] in [119]:
        return 'CA'
    if region['cloud_id'] in [120]:
        return 'NL'
    return ''


def get_server(account, node_id):
    '''
        get_server returns a vps.net node object
    '''
    node = None
    try:
        vpsnet_conn = get_vpsnet_connection(account)
        node = vpsnet_conn.get_ssd_node(node_id)
    except Exception as e:
        raise e
    
    return node


def get_servers(account):
    nodes = list()
    try:
        vpsnet_conn = get_vpsnet_connection(account)
        nodes = vpsnet_conn.list_ssd_nodes()
    except Exception as e:
        raise e
    return nodes


def remove_server(vpsnet_account, node_id):
    '''
        remove_server destroys a node using vps.net API calls
    '''
    try:
        vpsnet_conn = get_vpsnet_connection(vpsnet_account)
        node = vpsnet_conn.get_ssd_node(node_id)
        result = vpsnet_conn.delete_ssd_node(node)
        if not result:
            raise Exception('Could not destroy node: %s' % str(node_id))
    except Exception as e:
        raise e


def launch_new_server(vpsnet_account, _):
    """
        launch_new_server is called from psi_ops.py to create a new server.
    """
    try:
        VPSNetHost = collections.namedtuple('VPSNetHost',
                                            ['ssd_vps_plan', 'fqdn', 
                                             'system_template_id',
                                             'cloud_id', 'backups_enabled', 
                                             'rsync_backups_enabled',
                                             'licenses'])

        vpsnet_conn = get_vpsnet_connection(vpsnet_account)
        
        # Get a list of regions (clouds) that can be used
        vpsnet_clouds = vpsnet_conn.get_available_ssd_clouds()
        
        # Check each available cloud for a psiphon template to use.
        # Populate a list of templates and the cloud IDs.
        psiphon_templates = list()
        print 'Available Regions:\n'
        for region in vpsnet_clouds:
            print '%s -> %s' % (region['cloud']['id'], region['cloud']['label'])
            for template in region['cloud']['system_templates']:
                if 'psiphon-template' in template['label'].lower():
                    print '\tFound psiphon template id %s in region %s' % (
                        template['id'], region['cloud']['id'])
                    template['cloud_id'] = region['cloud']['id']
                    template['cloud_label'] = region['cloud']['label']
                    psiphon_templates.append(template)
        
        region_template = random.choice(psiphon_templates)
        VPSNetHost.cloud_id = region_template['cloud_id']
        VPSNetHost.system_template_id = region_template['id']
        
        print 'Using template: %s with cloud_id: %s' % (
            VPSNetHost.system_template_id, VPSNetHost.cloud_id)
       
        '''
            package/plan for the new SSD server. 
            (VPS 1GB - 1, VPS 2GB - 2, VPS 4GB - 3, VPS 8GB - 4, VPS 16GB - 5)
        '''
        VPSNetHost.ssd_vps_plan = vpsnet_account.base_ssd_plan
        VPSNetHost.fqdn = str('vn-' +
                              ''.join(random.choice(string.ascii_lowercase) for x in range(8)) +
                              '.vps.net')
        VPSNetHost.backups_enabled = False
        VPSNetHost.rsync_backups_enabled = False
        VPSNetHost.licenses = None

        node = vpsnet_conn.create_ssd_node(
            fqdn=VPSNetHost.fqdn, 
            image_id=VPSNetHost.system_template_id,
            cloud_id=VPSNetHost.cloud_id,
            size=VPSNetHost.ssd_vps_plan,
            backups_enabled=VPSNetHost.backups_enabled,
            rsync_backups_enabled=VPSNetHost.rsync_backups_enabled,
            )

        if not wait_on_action(vpsnet_conn, node, 30):
            raise "Could not power on node"
        else:
            node = vpsnet_conn.get_ssd_node(node.id)
        
        generated_root_password = node.extra['password']
        
        # Get the Node IP address
        if isinstance(node.public_ips, list):
            for public_ip in node.public_ips:
                if 'ip_address' in (public_ip and public_ip['ip_address']):
                    public_ip_address = public_ip['ip_address']['ip_address']
        
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        node_public_key = refresh_credentials(vpsnet_account, public_ip_address, 
                                              generated_root_password,
                                              new_root_password, new_stats_password)
    except Exception as e:
        print type(e), str(e)
        if node is not None:
            remove_server(vpsnet_account, node.id)
        else:
            print type(e), "No node to be destoryed: %s", str(node)
        raise
        
    return (
        VPSNetHost.fqdn, 
        None, 
        node.id, 
        public_ip_address,
        vpsnet_account.base_ssh_port,
        'root',
        new_root_password,
        ' '.join(node_public_key.split(' ')[:2]),
        vpsnet_account.base_stats_username,
        new_stats_password,
        region_template['cloud_label'],
        get_region_name(region_template),
        None, None, None, None, None, None, None,
        )
