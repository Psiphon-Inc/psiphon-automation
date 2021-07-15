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

# Import scaleway APIv4 Official Library
# Requirement: pip install slumber cachetools
from scaleway.scaleway import apis as ScalewayApis
from slumber import exceptions as slexc

# VARIABLE
tcs_image_name = 'Psiphon-TCS-V8-20210410'
tcs_instance_size = 'DEV1-M'

###
#
# Helper functions
#
###
def reload_proper_api_client(scaleway_api, scaleway_id):
    scaleway_id_list = scaleway_id.split('_')
    scaleway_api_region = scaleway_id_list[0]
    scaleway_instance_id = scaleway_id_list[1]

    scaleway_api.region = scaleway_api_region
    scaleway_api.reload()

    return scaleway_api, scaleway_instance_id

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
class PsiScaleway:
    def __init__(self, scaleway_account):
        self.api_token = scaleway_account.api_token
        self.region = random.choice(scaleway_account.regions)
        self.client = ScalewayApis.ComputeAPI(auth_token=self.api_token, region=self.region)
        self.organizations = ScalewayApis.AccountAPI(auth_token=self.api_token).query().tokens.get()['tokens'][0]['organization_id']

    def reload(self):
        self.client = ScalewayApis.ComputeAPI(auth_token=self.api_token, region=self.region)

    def get_image(self):
        try:
            images = self.client.query().images.get()['images']

            return [image for image in images if image['name'] == tcs_image_name and image['root_volume']['volume_type'] == 'l_ssd'][0]
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

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

    def check_task_status(self, task_id):
        try:
            task = self.client.query().tasks(task_id).get()
            return task['task']['status']
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def list_scaleways(self):
        try:
            # return all scaleways in the account.
            return self.client.query().servers.get()['servers']
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def scaleway_list(self, scaleway_id):
        try:
            # List single scaleway by searching its id
            return self.client.query().servers(scaleway_id).get()['server']
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def remove_scaleway(self, scaleway_id):
        try:
            scaleway = self.client.query().servers(scaleway_id).get()['server']
            if scaleway['state'] != 'poweroff':
                # Poweroff instance first
                off_res = self.client.query().servers(scaleway['id']).action.post({'action': 'poweroff'})
                # Wait for job completion
                wait_while_condition(lambda: self.scaleway_list(scaleway['id'])['state'] != 'stopped',
                                    60,
                                    'Stopping Scaleway Instance')

            # Delete instance
            del_res = self.client.query().servers(scaleway['id']).delete()

            # Delete volumes
            vol_res = self.client.query().volumes(scaleway['volumes']['0']['id']).delete()
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def start_scaleway(self, scaleway_id):
        try:
            # Boot scaleway from API
            self.client.query().servers(scaleway_id).action.post({'action': 'poweron'})
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def stop_scaleway(self, scaleway_id):        
        # Shutdown scaleway from API
        try:
            self.client.query().servers(scaleway_id).action.post({'action': 'poweroff'})
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def restart_scaleway(self, scaleway_id):
        try:
            # New method: restart scaleway from API
            self.client.query().servers(scaleway_id).action.post({'action': 'reboot'})
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

    def create_scaleway(self, host_id):
        try:
            # We are using Scaleway 3 vCPUs 4 GB: u'DEV1-M'
            scaleway = self.client.query().servers.post({'project': self.organizations, 'name': host_id, 'commercial_type': tcs_instance_size, 'image': self.get_image()['id']})

            res = self.start_scaleway(scaleway['server']['id'])
            wait_while_condition(lambda: self.scaleway_list(scaleway['server']['id'])['state'] != 'running',
                                 60,
                                 'Starting Scaleway Instance')

            return self.scaleway_list(scaleway['server']['id']), self.get_datacenter_names(), self.get_region()
        except slexc.HttpClientError as exc:
            print(json.dumps(exc.response.json(), indent=2))

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
    scaleways = []

    for region in scaleway_account.regions:
        scaleway_api.region = region
        scaleway_api.reload()

        instances = scaleway_api.list_scaleways()
        scaleways += instances

    # return id in the same format that we store it in Host.provider_id (see launch_new_server below)
    return [(s['zone'] + '_' + s['id'], s['name']) for s in scaleways]

def get_server(scaleway_account, scaleway_id):
    scaleway_api = PsiScaleway(scaleway_account)
    scaleway_api, scaleway_id = reload_proper_api_client(scaleway_api, scaleway_id)
    scaleway = scaleway_api.scaleway_list(scaleway_id)
    return scaleway

def remove_server(scaleway_account, scaleway_id):
    scaleway_api = PsiScaleway(scaleway_account)
    scaleway_api, scaleway_id = reload_proper_api_client(scaleway_api, scaleway_id)
    try:
        scaleway_api.remove_scaleway(scaleway_id)
    except Exception as e:
        raise e

def get_server_ip_addresses(scaleway_account, scaleway_id):
    scaleway_api = PsiScaleway(scaleway_account)
    scaleway_api, scaleway_id = reload_proper_api_client(scaleway_api, scaleway_id)
    scaleway = scaleway_api.scaleway_list(scaleway_id)

    public_ip = scaleway['public_ip']['address']
    private_ip = scaleway['private_ip']

    return (public_ip, private_ip)

def launch_new_server(scaleway_account, is_TCS, plugins, multi_ip=False):

    scaleway = None
    scaleway_api = PsiScaleway(scaleway_account) # Use new API interface

    try:
        # Create a new scaleway
        region = scaleway_api.get_region()
        host_id = 'sw' + '-' + region.lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        scaleway, datacenter_name, region = scaleway_api.create_scaleway(host_id)

        scaleway_ip_address = scaleway['public_ip']['address']
        scaleway_internal_ip_address = scaleway['private_ip']

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

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            scaleway_api.region + '_' + scaleway['id'], scaleway_ip_address,
            scaleway_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, None, None, None, None, None, scaleway_internal_ip_address)

if __name__ == '__main__':
    print launch_new_server()
