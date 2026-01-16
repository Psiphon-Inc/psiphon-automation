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
from vpsnet import vpsnet

# VARIABLE
TCS_BASE_IMAGE_ID = 'Psiphon3-TCS-V12.8-20250812' # most current base image label
TCS_VPS_DEFAULT_PLAN = 'V3' # 'id': 328, 'label': '4 Cores / 2GB RAM / 80GB SSD / 4TB Bandwidth', 'price': '16.00', 'product_name': 'V3'

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
        self.ssh_key_id = vpsnet_account.base_image_ssh_key_id
        self.client = vps.vpsnet(api_key=self.api_key)

    def get_location(self, select_location=None):
        # Load location from API
        # region_id required for create_instance
        all_locations = self.client.get_vps_locations()
        if select_location != None:
            locations = [r for r in all_locations['data'] if r['id'] == select_location]
        else:
            locations = all_locations['data']

        location = random.choice(locations)

        country = location['name'][-2:]
        city = location['name'][:-8].rstrip()
        location_id = location['id']

        return country, location_id, f"VPSNET {city}, {country}"

    #
    def list_instances(self):
        all_instances = self.client.get_vms()
        return all_instances

    #
    def get_instance(self, provider_id):
        split_ids = self.client.provider_id_to_location_server_ids(provider_id)
        location_id = split_ids[0]
        server_id = split_ids[1]
        instance = self.client.get_vm_server_details(location_id, server_id)
        return instance

    #
    def remove_instance(self, provider_id):
        split_ids = self.client.provider_id_to_location_server_ids(provider_id)
        location_id = split_ids[0]
        server_id = split_ids[1]
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
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_image_ssh_port,
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
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_image_ssh_port,
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
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_image_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)
    try:
        return ssh.exec_command('hostname').strip()
    finally:
        ssh.close()

def set_host_name(vpsnet_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_image_ssh_port,
                                   'root', None, vpsnet_account.base_image_ssh_public_key,
                                   host_auth_key=vpsnet_account.base_image_ssh_private_key)
    try:
        ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)
    finally:
        ssh.close()

def add_swap_file(vpsnet_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, vpsnet_account.base_image_ssh_port,
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
    instances = vpsnet_api.get_vms()
    return [(v['id'], v['label']) for v in instances['data']]

def get_server(vpsnet_account, provder_id): #
    split_ids = self.client.provider_id_to_location_server_ids(provider_id)
    location_id = split_ids[0]
    server_id = split_ids[1]
    vpsnet_api = PsiVpsnet(vpsnet_account)
    return vpsnet_api.get_vm_server_details(location_id, server_id)

def remove_server(vpsnet_account, provider_id): #
    split_ids = self.client.provider_id_to_location_server_ids(provider_id)
    location_id = split_ids[0]
    server_id = split_ids[1]
    vpsnet_api = PsiVpsnet(vpsnet_account)
    vpsnet_api.delete_vm_vps_server(location_id, server_id)

def launch_new_server(vpsnet_account, is_TCS, plugins, multi_ip=False):

    instance = None
    vpsnet_api = PsiVpsnet(vpsnet_account) # Use API interface

    try:
        # Create a new vpsnet instance
        region, location_id, datacenter_name = vpsnet_api.get_location()
        host_id = "vt" + '-' + region.lower() + location_id.lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        custom_template_id = vpsnet_api.get_custom_os_id(location_id, TCS_BASE_IMAGE_ID)
        data = (f"{{"
            f"\"label\": \"{host_id}\", "
            f"\"hostname\": \"{host_id}\", "
            f"\"backups\": false, "
            f"\"bill_hourly\": true, "
            f"\"product_name\": \"{TCS_BASE_IMAGE_ID}\", "
            f"\"custom_template_id\": \"{custom_template_id}\""
            f"}}")

        instance_info = vpsnet_api.create_vm(location_id, data)

        # Waiting to be restored from snapshot
        time.sleep(30)
        host_id_vpsnet = host_id + ".vps.net"
        server_id = vpsnet_api.client.get_server_id_by_host_id(host_id_vpsnet)
        vps_provider_id = location_id + "-" + server_id

        # Waiting for job completion
        wait_while_condition(lambda: vpsnet_api.client.get_vm_server_status(location_id, server_id)['message'] != 'Powered On',
                         30,
                         'Creating VPSNET Instance')

        instance = vpsnet_api.client.get_vm_server_details(location_id, server_id))

        instance_ip_address = instance['data']['ip_addresses'][0]['ip_address']['address']

        new_stats_username = psi_utils.generate_stats_username()
        set_host_name(vpsnet_account, instance_ip_address, host_id)
        set_allowed_users(vpsnet_account, instance_ip_address, new_stats_username)
        add_swap_file(vpsnet_account, instance_ip_address)

        # Change the new vpsnet instance's credentials
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(vpsnet_account, instance_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

    except Exception as ex:
        if instance:
            vpsnet_api.remove_instance(vps_provider_id)
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            vps_provider_id, instance_ip_address,
            vpsnet_account.base_image_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, None, None)

if __name__ == '__main__':
    print(launch_new_server)

