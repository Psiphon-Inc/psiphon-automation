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
import random
import string
import time
import psi_ssh
import psi_utils

# Import scaleway APIv4 Official Library
# Requirement: pip install slumber cachetools
from scaleway.scaleway import apis as ScalewayApis

# VARIABLE
tcs_image_name = 'Debian Buster'
tcs_instance_size = 'DEV1-M'

#==============================================================================
###
#
# General API Interaction functions
#
###
class PsiScaleway:
    def __init__(self, scaleway_account):
        self.api_token = scaleway_account.api_token
        self.region = random.choice(scaleway_account.regions)
        self.client = ScalewayApis.ComputeAPI(auth_token=self.api_token, region=self.region)
        self.organizations = ScalewayApis.AccountAPI(auth_token=self.api_token).query().organizations.get()['organizations'][0]['id']

    def get_image(self):
        images = self.client.query().images.get()['images']

        return [image for image in images if image['name'] == tcs_image_name and image['root_volume']['volume_type'] == 'l_ssd'][0]

    def get_region(self):
        # 'fr-par-1',
        # 'fr-par-2',
        # 'nl-ams-1',
        # 'pl-waw-1',

        # Get region's country code
        if 'fr' in self.region:
            country_code = 'FR'
        elif 'nl' in self.region:
            country_code = 'NL'
        elif 'pl' in self.region:
            country_code = 'PL'

        return country_code

    def get_datacenter_names(self):
        # from scaleway_api.get_available_regions():
        regions = {
            'fr-par-1': 'Scaleway Paris One, FR',
            'fr-par-2': 'Scaleway Paris Two, FR',
            'nl-ams-1': 'Scaleway Amsterdam, NL',
            'pl-waw-1': 'Scaleway Warsaw, PL'
        }
        return regions.get(self.region, '')

    def list_scaleways(self):
        # return all scaleways in the account.
        return self.client.query().servers.get()['servers']

    def scaleway_list(self, scaleway_id):
        # List single scaleway by searching its id
        return self.client.query().servers(scaleway_id).get()['server']

    def remove_scaleway(self, scaleway_id):
        scaleway = self.client.query().servers(scaleway_id).get()['server']
        # Poweroff instance first
        self.client.query().servers(scaleway['id']).action.post({'action': 'poweroff'})
        time.sleep(5)
        # Delete instance
        self.client.query().servers(scaleway['id']).delete()
        time.sleep(5)
        # Delete volumes
        self.client.query().volumes(scaleway['volumes']['0']['id']).delete()

    def start_scaleway(self, scaleway_id):
        # Boot scaleway from API
        return self.client.query().servers(scaleway_id).action.post({'action': 'poweron'})

    def stop_scaleway(self, scaleway_id):        
        # Shutdown scaleway from API
        return self.client.query().servers(scaleway_id).action.post({'action': 'poweroff'})

    def restart_scaleway(self, scaleway_id):
        # New method: restart scaleway from API
        return self.client.query().servers(scaleway_id).action.post({'action': 'reboot'})

    def create_scaleway(self, host_id):
        # We are using Scaleway 3 vCPUs 4 GB: u'DEV1-M'
        scaleway = self.client.query().servers.post({'project': self.organizations, 'name': host_id, 'commercial_type': tcs_instance_size, 'image': self.get_image()['id']})
        time.sleep(5)
        res = self.start_scaleway(scaleway['server']['id'])
        time.sleep(5)
        return self.scaleway_list(scaleway['server']['id']), self.get_datacenter_names(), self.get_region()

###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(scaleway_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, scaleway_account.base_ssh_port,
                                   'root', None, None,
                                   host_auth_key=scaleway_account.base_rsa_private_key)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (stats_username))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

def set_allowed_users(scaleway_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, scaleway_account.base_ssh_port,
                                   'root', None, None,
                                   host_auth_key=scaleway_account.base_rsa_private_key)
    user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
    if not user_exists:
        ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
        ssh.exec_command('service ssh restart')

def get_host_name(scaleway_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, scaleway_account.base_ssh_port,
                                   'root',None, None,
                                   host_auth_key=scaleway_account.base_rsa_private_key)
    return ssh.exec_command('hostname').strip()

def set_host_name(scaleway_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, scaleway_account.base_ssh_port,
                                   'root', None, None,
                                   host_auth_key=scaleway_account.base_rsa_private_key)
    ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)

###
#
# Main function
#
###
def get_servers(scaleway_account):
    scaleway_api = PsiScaleway(scaleway_account)
    scaleways = scaleway_api.list_scaleways()
    return [(s['id'], s['name']) for s in scaleways]

def get_server(scaleway_account, scaleway_id):
    scaleway_api = PsiScaleway(scaleway_account)
    scaleway = scaleway_api.scaleway_list(scaleway_id)
    return scaleway

def remove_server(scaleway_account, scaleway_id):
    scaleway_api = PsiScaleway(scaleway_account)
    try:
        scaleway_api.remove_scaleway(scaleway_id)
    except Exception as e:
        raise e

def launch_new_server(scaleway_account, is_TCS, plugins, multi_ip=False):

    scaleway = None
    scaleway_api = PsiScaleway(scaleway_account) # Use new API interface

    try:
        # Create a new scaleway
        region = scaleway_api.get_region()
        host_id = 'sw' + '-' + region.lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        scaleway, datacenter_name, region = scaleway_api.create_scaleway(host_id)

        scaleway_ip_address = scaleway['public_ip']['address']

        new_stats_username = psi_utils.generate_stats_username()
        # scaleways created by an image keep the image's hostname.  Override this
        set_host_name(scaleway_account, scaleway_ip_address, host_id)
        set_allowed_users(scaleway_account, scaleway_ip_address, new_stats_username)

        # Change the new scaleway's credentials
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(scaleway_account, scaleway_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

    except Exception as ex:
        if scaleway:
            scaleway_api.remove_scaleway(scaleway['id'])
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None, scaleway['id'], scaleway_ip_address,
            scaleway_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, None, None, None, None, None)

if __name__ == '__main__':
    print launch_new_server()
