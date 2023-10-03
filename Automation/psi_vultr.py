#!/usr/bin/python
#
# Copyright (c) 2021, Psiphon Inc.
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

# Import Vultr Python Library
# Requirement: vultr directory with library file
from vultr import vultr

# VARIABLE
TCS_BASE_IMAGE_NAME = ''
TCS_VULTR_DEFAULT_PLAN = 'vc2-2c-4gb' # default 2vCore 4G RAM 'vc2-2c-4gb', Sao Paulo 'vc2-2c-4gb-sc1'

#==============================================================================
###
#
# General API Interaction functions
#
###
class PsiVultr:
    def __init__(self, vultr_account, debug=False):
        self.api_key = vultr_account.api_key
        self.plan = TCS_VULTR_DEFAULT_PLAN
        self.client = vultr.Vultr(api_key=self.api_key)

    def get_region(self, select_region=None):
        # Load region from API
        # region_id required for create_instance
        all_regions = self.client.list_regions()
        if select_region == None:
            regions = [r for r in all_regions if r['country'] == select_region]
        else:
            regions = all_regions

        region = random.choice(regions)

        return region['id'], region['country'], region['city']

    def create_instance(self, host_id):
        # Launch Instnace
        self.client.create_instance(region=region, plan=self.plan)

    def remove_instance(self, instance_id):
        # Delete instance
        pass

###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(oracle_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
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

def set_allowed_users(oracle_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    try:
        user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
        if not user_exists:
            ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
            ssh.exec_command('service ssh restart')
    finally:
        ssh.close()

def get_host_name(oracle_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root',None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    try:
        return ssh.exec_command('hostname').strip()
    finally:
        ssh.close()

def set_host_name(oracle_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    try:
        ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)
    finally:
        ssh.close()

def add_swap_file(oracle_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port, 'root', None, None, host_auth_key=oracle_account.base_image_rsa_private_key)
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
def launch_new_server(vultr_account, is_TCS, plugins, multi_ip=False):
    
    vultr_api = PsiVultr(vultr_account) # Use API interface

    try:
        region = vultr_api.get_region()
    except Exception as ex:
        if instance:
            vultr_api.remove_instance(instance.id)
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            instance.id, instance_ip_address,
            oracle_account.base_image_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, egress_ip_address if multi_ip else None, instance_internal_ip_address)

if __name__ == '__main__':
    print(launch_new_server)
