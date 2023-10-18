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
        self.config = {
            # ??
        }
        self.api_key = vultr_account.api_key
        self.plan = TCS_VULTR_DEFAULT_PLAN
        self.client = vultr.Vultr(api_key=self.api_key)

    def reload(self):
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

    def get_datacenter_names(self) :
        datacenters = {
            "ewr" : "VULT New Jersey, US",
            "ord" : "VULT Chicago, US",
            "dfw" : "VULT Dallas, US",
            "sea" : "VULT Seattle, US",
            "lax" : "VULT Los Angeles, US",
            "atl" : "VULT Atlanta, US",
            "ams" : "VULT Amsterdam, NL",
            "lhr" : "VULT London, GB",
            "fra" : "VULT Frankfurt, DE",
            "sjc" : "VULT Silicon Valley, US",
            "syd" : "VULT Sydney, AU",
            "yto" : "VULT Toronto, CA",
            "cdg" : "VULT Paris, FR",
            "nrt" : "VULT Tokyo, JP",
            "waw" : "VULT Warsaw, PL",
            "mad" : "VULT Madrid, ES",
            "icn" : "VULT Seoul, KR",
            "mia" : "VULT Miami, US",
            "sgp" : "VULT Singapore, SG",
            "sto" : "VULT Stockholm, SE",
            "mex" : "VULT Mexico City, MX",
            "mel" : "VULT Melbourne, AU",
            "bom" : "VULT Mumbai, IN",
            "jnb" : "VULT Johannesburg, ZA",
            "tlv" : "VULT Tel Aviv, IL",
            "blr" : "VULT Bangalore, IN",
            "del" : "VULT Delhi NCR, IN",
            "scl" : "VULT Santiago, CL",
            "itm" : "VULT Osaka, JP",
            "man" : "VULT Manchester, GB",
            "hnl" : "VULT Honolulu, US", #hnl and sao does not have vc2-2c-4gb available.
            "sao" : "VULT Sao Paulo, BR" # this is a mistake/error as per their api: https://api.vultr.com/v2/regions; should be: Sao Paulo
            }

        return datacenters.get(self.client["region"], '')

    def list_instances(self):
        # TODO
        all_instances = self.client.list_instances()
        #pass
        return all_instances

    def remove_instance(self, instance_id):
        # TODO
        pass

    def start_instance(self, instance_id):
        # TODO
        pass

    def stop_instance(self, instance_id):
        # TODO
        pass

    def restart_instance(self, instance_id):
        # TODO
        pass

    def create_instance(self, host_id):
        # Launch Instnace
        instance = self.client.create_instance(
		region=region,
		plan=self.plan,
 	 	label="Psiphon 3 Hosts Public Subnet", #host_id?
  		os_id=352, #352 -> Debian 10 x64 (buster) || 477 -> Debian 11 x64 (bullseye)"
  		user_data="QmFzZTY0IEV4YW1wbGUgRGF0YQ==", #The user-supplied, base64 encoded user data to attach to this instance. -> random.choice(string.ascii_lowercase) for x in range(24)
  		backups="disabled",
  		hostname=host_id,
  		tags = ["Psiphon 3 Hosts Public Subnet"])

	return instance, self.get_datacenter_names(), self.get_region()

    def remove_instance(self, instance_id):
        # Delete instance
        pass

###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(vultr_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, vultr_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=vultr_account.base_image_rsa_private_key)
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

def set_allowed_users(vultr_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, vultr_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=vultr_account.base_image_rsa_private_key)
    try:
        user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
        if not user_exists:
            ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
            ssh.exec_command('service ssh restart')
    finally:
        ssh.close()

def get_host_name(vultr_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, vultr_account.base_image_ssh_port,
                                   'root',None, None,
                                   host_auth_key=vultr_account.base_image_rsa_private_key)
    try:
        return ssh.exec_command('hostname').strip()
    finally:
        ssh.close()

def set_host_name(vultr_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, vultr_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=vultr_account.base_image_rsa_private_key)
    try:
        ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)
    finally:
        ssh.close()

def add_swap_file(vultr_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, vultr_account.base_image_ssh_port, 'root', None, None, host_auth_key=vultr_account.base_image_rsa_private_key)
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
def get_servers(vultr_account):
    # TODO
    vultrs = []

    for region in vultr_account.regions:
        vultr_api.region = region
        vultr_api.reload()

        instances = vultr_api.list_instances()
        vultrs += instances

    # return id in the same format that we store it in Host.provider_id (see launch_new_server below)
    return [(v['region'] + '_' + v['id'], v['label']) for v in vultrs]
    pass

def get_server(vultr_account, vultr_id):
    # TODO
    return vultr_api.get_instance(self, vultr_id, 
    pass

def remove_server(vultr_account, vultr_id):
    # TODO
    pass

def get_server_ip_addresses(vultr_account, vultr_id): #probably not needed?
    vultr_api = PsiVultr(vultr_account)
    vultr_api, vultr_id = reload_proper_api_client(vultr_api, vultr_id)
    vultr = vultr_api.vultr_list(vultr_id)

    public_ip = vultr['main_ip']
    private_ip = vultr['internal_ip']

    return (public_ip, private_ip)


def launch_new_server(vultr_account, is_TCS, plugins, multi_ip=False):

    instance = None
    vultr_api = PsiVultr(vultr_account) # Use API interface

    try:
        #Create a new Vultr instance
        region = vultr_api.get_region()
        datacenter = vultr_api.get_datacenter_names()
        # Is it vt or vl or ???
        host_id = "vt" + '-' + region.lower() + datacenter[0:3].lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        instance, datacenter_name, region = vultr_api.create_instance(host_id)

###
        # Wait for job completion
        wait_while_condition(lambda: vultr_api.compute_api.get_instance(instance.id).data.lifecycle_state != 'RUNNING',
                         30,
                         'Creating VULTR Instance')

        instance_ip_address = instance["main_ip"]
        instance_internal_ip_address = instance["internal_ip"]

        new_stats_username = psi_utils.generate_stats_username()
        set_host_name(vultr_account, instance_ip_address, host_id)
        set_allowed_users(vultr_account, instance_ip_address, new_stats_username)
        add_swap_file(vultr_account, instance_ip_address)

        # Change the new vultr instance's credentials
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(vultr_account, instance_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

###

    except Exception as ex:
        if instance:
            vultr_api.remove_instance(instance.id)
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            instance.id, instance_ip_address,
            vultr_account.base_image_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, egress_ip_address if multi_ip else None, instance_internal_ip_address)

if __name__ == '__main__':
    print(launch_new_server)


