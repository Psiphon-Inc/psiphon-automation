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

import random
import string
import time

import psi_ssh
import psi_utils

from lightsail import lightsail

# VARIABLE
TCS_BASE_SNAPSHOT_NAME = 'Psiphon-TCS-V12.5-20260422'
# Available bundle IDs (general purpose):
#   nano_3_0    - 0.5 GB RAM, 2 vCPU, 20 GB SSD, 1 TB xfer - $5/mo
#   micro_3_0   - 1 GB RAM,   2 vCPU, 40 GB SSD, 2 TB xfer - $7/mo
#   small_3_0   - 2 GB RAM,   2 vCPU, 60 GB SSD, 3 TB xfer - $12/mo
#   medium_3_0  - 4 GB RAM,   2 vCPU, 80 GB SSD, 4 TB xfer - $24/mo
#   large_3_0   - 8 GB RAM,   2 vCPU, 160 GB SSD, 5 TB xfer - $44/mo
#   xlarge_3_0  - 16 GB RAM,  4 vCPU, 320 GB SSD, 6 TB xfer - $84/mo
#   2xlarge_3_0 - 32 GB RAM,  8 vCPU, 640 GB SSD, 7 TB xfer - $164/mo
# Note: bundle must be >= original snapshot's bundle when creating from snapshot.
TCS_BUNDLE_ID = 'micro_3_0'

#==============================================================================

###
#
# Helper functions
#
###
def wait_while_condition(condition, max_wait_seconds, description):
    total_wait_seconds = 0
    wait_seconds = 5
    while condition():
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
class PsiLightsail:
    def __init__(self, lightsail_account, debug=False):
        self.aws_access_key_id = lightsail_account.aws_access_key_id
        self.aws_secret_access_key = lightsail_account.aws_secret_access_key
        self.region = random.choice(lightsail_account.regions)
        self.bundle_id = TCS_BUNDLE_ID
        self.snapshot_name = TCS_BASE_SNAPSHOT_NAME
        self.key_pair_name = getattr(lightsail_account, 'key_pair_name', None)
        self.client = lightsail.Lightsail(
            region_name=self.region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def reload(self):
        self.client = lightsail.Lightsail(
            region_name=self.region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def get_region(self, select_region=None):
        """Pick a region and return (country_code, availability_zone, datacenter_name).

        If *select_region* is given it is used directly; otherwise a random
        available zone from the current client region is selected.
        """
        regions = self.client.list_regions(include_availability_zones=True)

        if select_region is not None:
            matching = [r for r in regions if r['name'] == select_region]
        else:
            matching = [r for r in regions if r['name'] == self.region]

        if not matching:
            raise Exception('Region %s not found' % (select_region or self.region))

        region_info = matching[0]
        available_zones = [
            az['zoneName']
            for az in region_info.get('availabilityZones', [])
            if az.get('state') == 'available'
        ]
        if not available_zones:
            raise Exception('No available zones in region %s' % region_info['name'])

        zone = random.choice(available_zones)
        country_code = region_info['name'].split('-')[0].upper()
        datacenter_name = 'AWS LightSail %s' % region_info.get('displayName', region_info['name'])

        return country_code, zone, datacenter_name

    def list_instances(self):
        return self.client.list_instances()

    def get_instance(self, instance_name):
        return self.client.get_instance(instance_name)

    def remove_instance(self, instance_name):
        print("Deleting Instance: %s" % instance_name)
        self.client.delete_instance(instance_name)

    def create_instance(self, host_id, availability_zone):
        operations = self.client.create_instance_from_snapshot(
            instance_name=host_id,
            availability_zone=availability_zone,
            bundle_id=self.bundle_id,
            instance_snapshot_name=self.snapshot_name,
            key_pair_name=self.key_pair_name,
            tags=[{'key': 'Name', 'value': host_id}],
        )
        return operations

    def open_all_ports(self, instance_name):
        self.client.put_instance_public_ports(
            instance_name=instance_name,
            port_infos=[{
                'fromPort': 0,
                'toPort': 65535,
                'protocol': 'all',
                'cidrs': ['0.0.0.0/0'],
                'ipv6Cidrs': ['::/0'],
            }],
        )

###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(lightsail_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, lightsail_account.base_ssh_port,
                                   'root', lightsail_account.base_ssh_root_password, None)
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

def set_allowed_users(lightsail_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, lightsail_account.base_ssh_port,
                                   'root', lightsail_account.base_ssh_root_password, None)
    try:
        user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
        if not user_exists:
            ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
            ssh.exec_command('service ssh restart')
    finally:
        ssh.close()

def set_host_name(lightsail_account, ip_address, new_hostname):
    ssh = psi_ssh.make_ssh_session(ip_address, lightsail_account.base_ssh_port,
                                   'root', lightsail_account.base_ssh_root_password, None)
    try:
        ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)
    finally:
        ssh.close()

def add_swap_file(lightsail_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, lightsail_account.base_ssh_port,
                                   'root', lightsail_account.base_ssh_root_password, None)
    try:
        has_swap = ssh.exec_command('grep swap /etc/fstab')
        if not has_swap:
            ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
            ssh.exec_command('echo "/swapfile swap swap defaults 0 0" | tee -a /etc/fstab')
            ssh.exec_command('swapon -a')
    finally:
        ssh.close()

###
#
# Main function
#
###
def reload_proper_api_client(lightsail_api, provider_id):
    parts = provider_id.split('_', 1)
    region = parts[0]
    instance_name = parts[1]

    lightsail_api.region = region
    lightsail_api.reload()

    return lightsail_api, instance_name

def copy_snapshot_to_all_regions(lightsail_account, source_region):
    lightsail_api = PsiLightsail(lightsail_account)
    snapshot_name = TCS_BASE_SNAPSHOT_NAME

    for target_region in lightsail_account.regions:
        if target_region == source_region:
            continue

        lightsail_api.region = target_region
        lightsail_api.reload()
        existing = [s['name'] for s in lightsail_api.client.list_snapshots()]
        if snapshot_name in existing:
            print('Snapshot %s already exists in %s, skipping' % (snapshot_name, target_region))
            continue

        print('Copying snapshot %s from %s to %s' % (snapshot_name, source_region, target_region))
        lightsail_api.client.copy_snapshot(
            source_snapshot_name=snapshot_name,
            target_snapshot_name=snapshot_name,
            source_region=source_region,
            target_region=target_region,
        )

def get_servers(lightsail_account):
    lightsail_api = PsiLightsail(lightsail_account)
    all_instances = []

    for region in lightsail_account.regions:
        lightsail_api.region = region
        lightsail_api.reload()
        instances = lightsail_api.list_instances()
        all_instances += [(region + '_' + i['name'], i['name']) for i in instances]

    return all_instances

def get_server(lightsail_account, provider_id):
    lightsail_api = PsiLightsail(lightsail_account)
    lightsail_api, instance_name = reload_proper_api_client(lightsail_api, provider_id)
    return lightsail_api.get_instance(instance_name)

def remove_server(lightsail_account, provider_id):
    lightsail_api = PsiLightsail(lightsail_account)
    lightsail_api, instance_name = reload_proper_api_client(lightsail_api, provider_id)
    try:
        lightsail_api.remove_instance(instance_name)
    except Exception as e:
        if 'NotFoundException' not in str(e):
            raise e

def launch_new_server(lightsail_account, is_TCS, plugins, multi_ip=False):

    instance = None
    lightsail_api = PsiLightsail(lightsail_account)

    try:
        region, availability_zone, datacenter_name = lightsail_api.get_region()
        host_id = "aws" + '-' + 'l' + region.lower() + datacenter_name.split(' ')[2][:3].lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))

        lightsail_api.create_instance(host_id, availability_zone)

        wait_while_condition(
            lambda: lightsail_api.client.get_instance_state(host_id) != 'running',
            120,
            'Creating Lightsail Instance')

        lightsail_api.open_all_ports(host_id)

        time.sleep(30)
        instance = lightsail_api.get_instance(host_id)

        instance_ip_address = instance['publicIpAddress']
        instance_private_ip_address = instance['privateIpAddress']

        new_stats_username = psi_utils.generate_stats_username()
        set_host_name(lightsail_account, instance_ip_address, host_id)
        set_allowed_users(lightsail_account, instance_ip_address, new_stats_username)
        add_swap_file(lightsail_account, instance_ip_address)

        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(lightsail_account, instance_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

    except Exception as ex:
        if instance:
            print("Removing instances due to failure...")
            #lightsail_api.remove_instance(instance['name'])
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            lightsail_api.region + '_' + instance['name'], instance_ip_address,
            lightsail_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, None, instance_private_ip_address)

if __name__ == '__main__':
    print(launch_new_server)
