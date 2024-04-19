#!/usr/bin/python
#
# Copyright (c) 2023, Psiphon Inc.
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

# Import hetzner Python Library
# Requirement: hetzner directory with library file
from hcloud import Client
from hcloud.images import Image
from hcloud.server_types import ServerType

# VARIABLE
TCS_BASE_IMAGE_ID = None
# Plans:
# cx11  = 1C2G
# cx21  = 2C4G
# cx31  = 2C8G
# cpx21 = 3C4G (AMD)
# cpx31 = 4C8G (AMD)
TCS_HETZNER_DEFAULT_PLAN_LIST = ['cx21', 'cpx21']

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
class PsiHetzner:
    def __init__(self, hetzner_account, debug=False):
        self.api_token = hetzner_account.api_token
        self.regions = hetzner_account.regions
        self.datacenters = hetzner_account.datacenters
        self.plan_list = TCS_HETZNER_DEFAULT_PLAN_LIST
        self.base_image_id = hetzner_account.default_base_image_id if TCS_BASE_IMAGE_ID == None else TCS_BASE_IMAGE_ID
        self.ssh_key_name = hetzner_account.dafault_base_image_ssh_key_name
        self.ssh_private_key = hetzner_account.default_base_image_ssh_private_key
        self.client = Client(token=self.api_token)

    def get_region(self, select_region=None):
        # Load region from API
        # region_id required for create_instance
        all_regions = self.client.locations.get_all()
        if select_region != None:
            regions = [r for r in all_regions if r.name == select_region]
        else:
            regions = [r for r in all_regions]

        region = random.choice(regions)

        return region

    def get_datacenter(self, select_datacenter=None):
        # Load datacenter from API
        all_datacenters = self.client.datacenters.get_all()
        if select_datacenter != None:
            datacenters = [d for d in all_datacenters if d.name == select_datacenter]
        else:
            datacenters = [d for d in all_datacenters]

        datacenter = random.choice(datacenters)

        return datacenter

    def get_region_code(self, select_region):
        regions = {
            "fsn1": "DE",
            "nbg1": "DE",
            "hel1": "FI",
            "ash" : "US",
            "hil" : "US"
        }

        return regions.get(select_region, '')

    def get_datacenter_names(self, select_datacenter):
        datacenters = {
            "fsn1": "Hetzner Falkenstein, DE",
            "nbg1": "Hetzner Nuremberg, DE",
            "hel1": "Hetzner Helsinki, FI",
            "ash" : "Hetzner Ashburn VA, US",
            "hil" : "Hetzner Hillsboro OR, US"
            }

        return datacenters.get(select_datacenter, '')

    def get_server_type(self, datacenter, server_type=TCS_HETZNER_DEFAULT_PLAN_LIST):
        #server_launch_type = self.client.server_types.get_by_name(server_type)
        server_launch_type = [t for t in datacenter.server_types.available if t.name in server_type][0]

        return server_launch_type

    def get_image(self, image_id=None):
        if image_id == None:
            server_launch_image = self.client.images.get_by_name('debian-12')
        else:
            server_launch_image = self.client.images.get_by_id(image_id)

        return server_launch_image

    def get_ssh_key(self, ssh_key_name=None):
        if ssh_key_name == None:
            server_default_ssh_key = self.client.ssh_keys.get_by_name(self.ssh_key_name)
        else:
            server_default_ssh_key = self.client.ssh_keys.get_by_name(ssh_key_name)

        return server_default_ssh_key

    def list_instances(self):
        all_instances = self.client.servers.get_all()
        # This will return a list of Servers Object
        return all_instances

    def get_instance(self, instance_id):
        instance = self.client.servers.get_by_id(instance_id)
        # instance.id == provider_id
        # instance.name == host_id (or any name)
        # intsnace.status == running status (either 'running' or 'stopped')
        # instance.power_on or instance.power_off would be the power control
        # instance.public_net == PublicNetwork object, where include a instance.public_net.ipv4 and instance.public_net.ipv4.ip to get IP address
        return instance

    def remove_instance(self, instance_id):
        instance = self.client.servers.get_by_id(instance_id)
        instance.delete()
        print("Deleting Instances: {} / {} - IP: {}".format(instance.id, instance.name, instance.public_net.ipv4.ip))

    def create_instance(self, host_id, datacenter=None, labels={"type":"psiphond"}):
        # Launch Instnace
        instance = self.client.servers.create(
            name=host_id,
            server_type=self.get_server_type(datacenter, TCS_HETZNER_DEFAULT_PLAN_LIST),
            image=self.get_image(self.base_image_id),
            ssh_keys=[self.get_ssh_key(self.ssh_key_name)],
            location=self.get_region(datacenter.location.name),
            labels=labels
        )

        return instance.server

###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(hetzner_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, hetzner_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=hetzner_account.default_base_image_ssh_private_key)
    try:
        ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
        ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (stats_username))
        ssh.exec_command('echo "%s:%s" | chpasswd' % (stats_username, new_stats_password))
        ssh.exec_command('rm /etc/ssh/ssh_host_*')
        ssh.exec_command('rm -rf /root/.ssh')
        ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && dpkg-reconfigure openssh-server')
        return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')
    finally:
        ssh.close()

def set_allowed_users(hetzner_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, hetzner_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=hetzner_account.default_base_image_ssh_private_key)
    try:
        user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
        if not user_exists:
            ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
            ssh.exec_command('service ssh restart')
    finally:
        ssh.close()

def get_host_name(hetzner_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, hetzner_account.base_image_ssh_port,
                                   'root',None, None,
                                   host_auth_key=hetzner_account.default_base_image_ssh_private_key)
    try:
        return ssh.exec_command('hostname').strip()
    finally:
        ssh.close()

def set_host_name(hetzner_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, hetzner_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=hetzner_account.default_base_image_ssh_private_key)
    try:
        ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)
    finally:
        ssh.close()

def add_swap_file(hetzner_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, hetzner_account.base_image_ssh_port, 'root', None, None, host_auth_key=hetzner_account.default_base_image_ssh_private_key)
    try:
        has_swap = ssh.exec_command('grep swap /etc/fstab')

        if not has_swap:
            ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
            ssh.exec_command('echo "/swapfile swap swap defaults 0 0" >> /etc/fstab')
            ssh.exec_command('swapon -a')
    finally:
        ssh.close()

###
#
# Main function
#
###
def get_servers(hetzner_account):
    hetzner_api = PsiHetzner(hetzner_account)
    instances = hetzner_api.list_instances()
    #return [(v['region'] + '_' + v['id'], v['label']) for v in hetzners]
    return instances

def get_server(hetzner_account, hetzner_id):
    hetzner_api = PsiHetzner(hetzner_account)
    return hetzner_api.get_instance(hetzner_id) 

def remove_server(hetzner_account, hetzner_id):
    hetzner_api = PsiHetzner(hetzner_account)
    hetzner_api.remove_instance(hetzner_id)

def launch_new_server(hetzner_account, is_TCS, plugins, multi_ip=False):

    instance = None
    hetzner_api = PsiHetzner(hetzner_account) # Use API interface

    try:
        #Create a new hetzner instance
        #region = hetzner_api.get_region()
        datacenter = hetzner_api.get_datacenter()
        host_id = "htz" + '-' + ''.join(datacenter.name.lower().split('-')) + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        instance_info = hetzner_api.create_instance(host_id, datacenter)

        # Wait for job completion
        # Hetzner initializing will take longer when restore from snapshot. 
        wait_while_condition(lambda: hetzner_api.client.servers.get_by_id(instance_info.id).status != 'running',
                         150,
                         'Creating Hetzner Instance')
        instance = hetzner_api.client.servers.get_by_id(instance_info.id)

        instance_ip_address = instance.public_net.ipv4.ip
        region_code = hetzner_api.get_region_code(instance.datacenter.location.name)
        datacenter_name = hetzner_api.get_datacenter_names(instance.datacenter.location.name)

        # Generate new credentials
        new_stats_username = psi_utils.generate_stats_username()
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()

        # Setup Hosts
        set_host_name(hetzner_account, instance_ip_address, host_id)
        set_allowed_users(hetzner_account, instance_ip_address, new_stats_username)
        add_swap_file(hetzner_account, instance_ip_address)

        # Change the new hetzner instance's credentials

        new_host_public_key = refresh_credentials(hetzner_account, instance_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

    except Exception as ex:
        if instance:
            hetzner_api.remove_instance(instance.id)
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            instance.id, instance_ip_address,
            hetzner_account.base_image_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region_code, egress_ip_address if multi_ip else None, None)

if __name__ == '__main__':
    print(launch_new_server)
