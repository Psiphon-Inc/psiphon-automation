#!/usr/bin/python
#
# Copyright (c) 2026, Psiphon Inc.
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

import os
import sys
import json
import random
import string
import time
import psi_ssh
import psi_utils

# Import VPSNET Python Library
# Requirement: VPSNET directory with library file
from VPSNET import vpsnet

# VARIABLE
TCS_BASE_IMAGE_ID = 'Psiphon3-TCS-V12.8-20250812' # most current base image label
TCS_VPS_DEFAULT_PLAN = 'V4' # 'id': 328, 'label': '4 Cores / 2GB RAM / 80GB SSD / 4TB Bandwidth', 'price': '16.00', 'product_name': 'V3'

###
#
# Helper functions
#
###
def wait_while_condition(condition, max_wait_seconds, description):
    total_wait_seconds = 0
    wait_seconds = 5
    while condition() == True:
        if total_wait_seconds > max_wait_seconds:
            raise Exception('Took more than %d seconds to %s' % (max_wait_seconds, description))
        time.sleep(wait_seconds)
        total_wait_seconds = total_wait_seconds + wait_seconds

#==============================================================================
###
#
# General API Interaction functions
#
###
class PsiVpsnet:
    def __init__(self, vpsnet_account, debug=False):
        self.api_key = vpsnet_account.api_key
        self.plan = TCS_VPS_DEFAULT_PLAN
        self.base_image_id = TCS_BASE_IMAGE_ID
        self.client = vpsnet.VPSNET(api_key=self.api_key)

    def get_location(self, select_location=None):
        # Load location from API
        # region_id required for create_instance
        all_locations = self.client.get_vps_locations()
        if select_location != None:
            locations = [r for r in all_locations if r['id'] == select_location]
        else:
            locations = all_locations

        location = random.choice(locations)

        location_id = location['id']
        datacenter_name, region = location['name'].split(", ")

        if region == 'UK':
            region = 'GB'

        return region, location_id, datacenter_name

    def get_datacenter_name(datacenter_name, region):
        return f"VPSNET {datacenter_name}, {region}"

    #
    def list_instances(self):
        all_instances = self.client.get_vms()
        return all_instances

    #
    def get_instance(self, provider_id):
        location_id, server_id = self.client.provider_id_to_location_server_ids(provider_id)
        instance = self.client.get_vm_server_details(location_id, server_id)
        return instance

    #
    def remove_instance(self, provider_id):
        location_id, server_id = self.client.provider_id_to_location_server_ids(provider_id)
        print("Deleting Instances: {}".format(location_id - server_id))
        self.client.delete_vm_vps_server(location_id, server_id)


    def create_instance(self, location_id, data):
        # Launch Instance
        instance = self.client.create_vm(location_id, data)
        return instance


###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(vpsnet_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)
    try:
        ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
        ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (stats_username))
        ssh.exec_command('echo "%s:%s" | chpasswd' % (stats_username, new_stats_password))
        ssh.exec_command('rm /etc/ssh/ssh_host_*')
        ssh.exec_command('rm -rf /root/.ssh')
        ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && dpkg-reconfigure openssh-server')
        return ssh.exec_command('cat /etc/ssh/ssh_host_ed25519_key.pub')
    finally:
        ssh.close()

def set_allowed_users(vpsnet_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)
    try:
        user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
        if not user_exists:
            ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
            ssh.exec_command('service ssh restart')
    finally:
        ssh.close()

def get_host_name(vpsnet_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)

def add_swap_file(vpsnet_account, ip_address, password):
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_ssh_port, 'root', password, None, None)
    try:
        has_swap = ssh.exec_command('grep swap /etc/fstab')
        if not has_swap:
            ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
            ssh.exec_command('echo "/swapfile swap swap defaults 0 0" >> /etc/fstab')
            ssh.exec_command('swapon -a')
    finally:
        ssh.close()

def wait_on_action(vpsnet_conn, node, interval=30):
    for attempt in range(10):
        node = vpsnet_conn.get_ssd_node(node.id)
        if 'running' in node.state.lower():
            return True
        else:
            print('node state : %s.  Trying again in %s' % (node.state, interval))
            time.sleep(int(interval))

    return False


def get_region_name(region):
    '''
        65:  LON-K-SSD:                     London GB (Not available)
        66:  SLC-G-SSD:                     Salt Lake City US (Not available)
        91:  LON-M-SSD:                     London GB (Not available)
        113: SLC-H-SSD:                     Salt Lake City US
        116: (New York) - NYC-A-SSD:        New York US (Not available)
        117: (Los Angeles) - LAX-A-SSD:     Los Angeles US
        118: SLC-K-SSD:                     Salt Lake City US
        119: TOR-A-SSD:                     Toronto CA
        120: AMS-B-SSD:                     Amsterdam NL
        121: LON-P-SSD:                     London GB (Not available)
        124: (Miami) - MIA-A-SSD:           Miami US
        125: (Chicago) - CHI-C-SSD:         Chicago US
        126: (Dallas) - DAL-B-SSD           Dallas US
        127: LON-R-SSD                      London GB
        128: VAN-A-SSD                      Vancouver CA
        129: (New York) - NYC-B-SSH         New York US
        130: PHX-A-SSD                      City of Phoenix US
        131: (Seattle) - SEA-B-SSD          Seattle US
        132: ATL-G-SSD                      Atlanta US
        133: (New York) - NYC-C-SSD         New York US
        134: LON-Q-SS                       London GB
        135: FRA-B-SSD                      Frankfurt DE
        148: SLC-A-SSD                      SLC US
        151: CHI-G-SSD                      Chicago US
        154: ATL-A-SSD                      Atlanta US
        157: SIN-B-SSD                      Singapore SG
        160: DAL-C-SSD                      Dallas US
    '''
    if region['cloud_id'] in [65, 91, 121, 127, 134, 137]:
        return 'GB'
    if region['cloud_id'] in [66, 113, 116, 117, 118, 124, 125, 126, 129, 130, 131, 132, 133, 141, 142, 143, 144, 148, 151, 154, 160]:
        return 'US'
    if region['cloud_id'] in [119, 128]:
        return 'CA'
    if region['cloud_id'] in [120]:
        return 'NL'
    if region['cloud_id'] in [135, 139]:
        return 'DE'
    if region['cloud_id'] in [145, 157]:
        return 'SG'
    return ''

def set_host_name(vpsnet_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)
    try:
        ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)
    finally:
        ssh.close()

def add_swap_file(vpsnet_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)
    try:
        has_swap = ssh.exec_command('grep swap /etc/fstab')

        if not has_swap:
            ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
            ssh.exec_command('echo "/swapfile swap swap defaults 0 0" >> /etc/fstab')
            ssh.exec_command('swapon -a')
    finally:
        ssh.close()
###

###
#
# Main function
#
###
def get_servers(vpsnet_account): #
    vpsnet_api = PsiVpsnet(vpsnet_account)
    instances = vpsnet_api.client.get_vms()
    return [(str(v['location']['id']) + '-' + str(v['id']), v['hostname']) for v in instances]

def get_server(vpsnet_account, provider_id): #
    vpsnet_api = PsiVpsnet(vpsnet_account)
    location_id, server_id = vpsnet_api.client.provider_id_to_location_server_ids(provider_id)
    return vpsnet_api.client.get_vm_server_details(location_id, server_id)

def remove_server(vpsnet_account, provider_id): #
    try:
        vpsnet_api = PsiVpsnet(vpsnet_account)
        location_id, server_id = vpsnet_api.client.provider_id_to_location_server_ids(provider_id)
        vpsnet_api.client.delete_vm_vps_server(location_id, server_id)
    except:
        print("ERROR: Remove server failed: {}".format(provider_id))

def launch_new_server(vpsnet_account, is_TCS, plugins, multi_ip=False):

    instance = None
    vpsnet_api = PsiVpsnet(vpsnet_account) # Use API interface

    try:
        # Create a new vpsnet instance
        region, location_id, datacenter_name = vpsnet_api.get_location()
        host_id = "vn" + '-' + region.lower() + datacenter_name[:3].lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        custom_template_id = vpsnet_api.client.get_custom_os_id(str(location_id), TCS_BASE_IMAGE_ID)
        hostname_vpsnet = host_id + ".vps.net"

        #data = (f"{{"
        #    f"\"label\": \"{host_id}\", "
        #    f"\"hostname\": \"{hostname_vpsnet}\", "
        #    f"\"backups\": false, "
        #    f"\"bill_hourly\": true, "
        #    f"\"product_name\": \"{TCS_VPS_DEFAULT_PLAN}\", "
        #    f"\"custom_template_id\": \"{custom_template_id}\""
        #    f"}}")

        # For test only
        data = (f"{{"
            f"\"label\": \"{host_id}\", "
            f"\"hostname\": \"{hostname_vpsnet}\", "
            f"\"backups\": false, "
            f"\"bill_hourly\": true, "
            f"\"product_name\": \"{TCS_VPS_DEFAULT_PLAN}\", "
            f"\"os_component_code\": \"SSDVPSDEBIAN12\""
            f"}}")

        instance_info = vpsnet_api.create_instance(location_id, data)

        # Waiting to be restored from snapshot
        time.sleep(30)
        server_id = vpsnet_api.client.get_server_id_by_host_id(hostname_vpsnet)
        vps_provider_id = str(location_id) + "-" + str(server_id)

        # Waiting for job completion
        wait_while_condition(lambda: vpsnet_api.client.get_vm_server_status(location_id, server_id)['status'] != 1,
                         30,
                         'Creating VPSNET Instance')

        print(instance_info)

        instance = vpsnet_api.client.get_vm_server_details(location_id, server_id)

        instance_ip_address = instance['ip_addresses'][0]['ip_address']['address']

        new_stats_username = psi_utils.generate_stats_username()
        set_host_name(vpsnet_account, instance_ip_address, host_id)
        set_allowed_users(vpsnet_account, public_ip_address, new_root_password, stats_username)
        add_swap_file(vpsnet_account, public_ip_address, new_root_password)

        generated_root_password = instance['initial_root_password']

        # Change the new vpsnet instance's credentials
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        node_public_key = refresh_credentials(vpsnet_account, public_ip_address,
                                              generated_root_password,
                                              new_root_password, new_stats_password, stats_username)
        assert(node_public_key)

    except Exception as ex:
        if instance:
            vpsnet_api.remove_instance(vps_provider_id)
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            vps_provider_id, instance_ip_address,
            vpsnet_account.base_ssh_port, 'root', new_root_password,
            ' '.join(node_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            get_datacenter_name(datacenter_name, region),
            region,
            None, None
            )

if __name__ == '__main__':
    print(launch_new_server)
