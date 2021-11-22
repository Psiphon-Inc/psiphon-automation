#!/usr/bin/python
#
# Copyright (c) 2019, Psiphon Inc.
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

# Import Linode APIv4 Official Library
import linode_api4

# VARIABLE
tcs_image_id = 'private/8328933'

#==============================================================================

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

###
#
# General API Interaction functions
#
###
class PsiLinode:
    def __init__(self, linode_account):
        api_token = linode_account.api_token
        self.client = linode_api4.LinodeClient(api_token)

    def get_available_regions(self):
        # Get all available regions
        # excluding AU and IN
        available_regions = self.client.regions()
        allowed_regions = []
        for region in available_regions:
            if region.country.upper() not in ['AU', 'IN']:
                allowed_regions.append(region)
        return allowed_regions

    def get_region(self, region):
        # Get region's country code
        country_code = region.country.upper()
        if country_code == 'UK':
            country_code = 'GB'
        return country_code

    def get_datacenter_names(self, region):
        # from linode_api.get_available_regions():
        regions = {
            'ap-northeast': 'Linode Tokyo 2, JP',
            'ap-west': 'Linode Mumbai, India',
            'ap-south': 'Linode Singapore, SG',
            'ap-southeast': 'Linode Sydney, NSW, Australia',
            'ca-central': 'Linode Toronto, Ontario, CAN',
            'us-central': 'Linode Dallas, TX, USA',
            'us-west': 'Linode Fremont, CA, USA',
            'us-southeast': 'Linode Atlanta, GA, USA',
            'us-east': 'Linode Newark, NJ, USA',
            'eu-west': 'Linode London, England, UK',
            'eu-central': 'Linode Frankfurt, DE'
        }
        return regions.get(region.id, "")

    def list_linodes(self):
        # return all linodes in the account.
        return self.client.linode.instances()

    def linode_list(self, linode_id):
        # List single linode by searching its id
        return linode_api4.linode.Instance(self.client, linode_id)

    def linode_status(self, linode_id):
        # Return linode status
        # Status:
        # "running"
        # "offline"
        # "booting"
        # "rebooting"
        # "shutting_down"
        # "provisioning"
        # "deleting"
        # "migrating"
        # "rebuilding"
        # "cloning"
        # "restoring"
        return self.linode_list(linode_id).status

    def remove_linode(self, linode_id):
        return self.linode_list(linode_id).delete()
    
    def create_linode(self):
        available_regions = self.get_available_regions()
        choice_region = random.choice(available_regions)
        datacenter_name = self.get_datacenter_names(choice_region)

        # We are using Linode 4G: u'g6-standard-2'
        linode = self.client.linode.instance_create("g6-standard-2", choice_region.id)
        
        # Wait for job completion
        wait_while_condition(lambda: self.linode_list(linode.id).status == 'provisioning',
                         60,
                         'create a linode')
        assert(self.linode_list(linode.id).status == 'offline')

        # linode_api.linode_update(LinodeID=new_node_id, Alert_bwquota_enabled=0, Alert_bwout_enabled=0, Alert_bwin_enabled=0) Update to disable the alert
        return linode, datacenter_name, self.get_region(choice_region)

    def pubip_allocate(self, linode):
        return linode.ip_allocate(public=True).address

    def start_linode(self, linode_id, config=None):
        # Boot linode from API
        linode = self.linode_list(linode_id)
        linode.boot(config=config)
        # Wait for job completion

        wait_while_condition(lambda: self.linode_list(linode_id).status == 'booting',
                         60,
                         'boot the linode')
        assert(self.linode_list(linode_id).status == 'running')

    def stop_linode(self, linode_id):        
        # Shutdown linode from API
        linode = self.linode_list(linode_id)
        linode.shutdown()
        # Wait for job completion
        wait_while_condition(lambda: self.linode_list(linode_id).status == 'shutting_down',
                         150,
                         'shutdown the linode')
        assert(self.linode_list(linode_id).status == 'offline')
    
    def restart_linode(self, linode_id):
        # New method: restart linode from API
        linode = self.linode_list(linode_id)
        linode.reboot()
        # Wait for job completion
        wait_while_condition(lambda: self.linode_list(linode_id).status == 'rebooting',
                         60,
                         'reboot the linode')
        assert(self.linode_list(linode_id).status == 'running')

    def create_linode_disks(self, linode, bootstrap_password, is_TCS, plugins):
        if is_TCS:
            image = linode_api4.linode.Image(self.client, tcs_image_id)
            disk = linode.disk_create(29500, image=image, filesystem='ext4', root_pass=bootstrap_password)
        else: # Lagecy psiphon servers, NOT TESTED
            #TODO: THIS ONE ISN'T WORKING SINCE LINODE CHANGED THEIR IMAGE/DISTRIBUTION ID SYSTEM.
            # DistributionID = 130: 'Debian 7.6'
            # distribution_id = 130
            # for plugin in plugins:
            #     if hasattr(plugin, 'linode_distribution_id'):
            #         distribution_id = plugin.linode_distribution_id()

            # disk = linode.disk_create(29500, label='Psiphon 3 Disk Image', image=distribution_id, root_pass=bootstrap_password)
            pass

        # Wait for job completion
        wait_while_condition(lambda: disk.status == 'not ready',
                         120,
                         'create a disk from base image')
        assert(disk.status == 'ready')

        swap_disk = linode.disk_create(1024, label='Psiphon 3 Swap', filesystem='swap')

        # Wait for job completion
        wait_while_condition(lambda: swap_disk.status == 'not ready',
                         30,
                         'create a swap disk')
        assert(swap_disk.status == 'ready')

        return [disk.id, swap_disk.id]

    def create_linode_configurations(self, linode, disk_list, is_TCS, plugins, multi_ip=False):
        # KernelID = 138: Latest 64 bit
        bootstrap_kernel_id = "linode/latest-64bit" # New API Changed to use new naming schema

        if is_TCS:
            host_kernel_id = bootstrap_kernel_id
        else:
            # KernelID = 216: GRUB Legacy (KVM)
            host_kernel_id = "linode/grub-legacy" # New API Changed to use new naming schema

        for plugin in plugins: #TODO: Not tested.
            if hasattr(plugin, 'linode_kernel_ids'): #TODO: for plugins, if needed, need to change it to use name maing
                bootstrap_kernel_id, host_kernel_id = plugin.linode_kernel_ids()

        bootstrap_config = linode.config_create(kernel=bootstrap_kernel_id, label='Bootstrap', disks=disk_list)
        psiphon3_host_config = linode.config_create(kernel=host_kernel_id, label='Psiphon 3 Host', disks=disk_list, helpers={"network":multi_ip})
        
        return bootstrap_config, psiphon3_host_config

###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def pave_linode(linode_account, ip_address, password):
    # Note: using auto-add-policy for host's SSH public key here since we can't get it through the Linode API.
    # There's a risk of man-in-the-middle.
    ssh = psi_ssh.make_ssh_session(ip_address, 22, 'root', password, None)
    ssh.exec_command('mkdir -p /root/.ssh')
    ssh.exec_command('echo "%s" > /root/.ssh/known_hosts' % (linode_account.base_known_hosts_entry,))
    ssh.exec_command('echo "%s" > /root/.ssh/id_rsa' % (linode_account.base_rsa_private_key,))
    ssh.exec_command('chmod 600 /root/.ssh/id_rsa')
    ssh.exec_command('echo "%s" > /root/.ssh/id_rsa.pub' % (linode_account.base_rsa_public_key,))
    ssh.exec_command('scp -P %d root@%s:%s %s' % (linode_account.base_ssh_port,
                                                 linode_account.base_ip_address,
                                                  linode_account.base_tarball_path,
                                                 linode_account.base_tarball_path))
    ssh.exec_command('apt-get update > /dev/null')
    ssh.exec_command('apt-get install -y bzip2 > /dev/null')
    ssh.exec_command('tar xvpfj %s -C / > /dev/null' % (linode_account.base_tarball_path,))

def refresh_credentials(linode_account, ip_address, password, host_public_key, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                                   'root', password, host_public_key)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (stats_username))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

def set_allowed_users(linode_account, ip_address, password, host_public_key, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                                   'root', password, host_public_key)
    user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
    if not user_exists:
        ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
        ssh.exec_command('service ssh restart')

def get_host_name(linode_account, ip_address, password, host_public_key):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                                   'root', password, host_public_key)
    return ssh.exec_command('hostname').strip()

def set_host_name(linode_account, ip_address, password, host_public_key, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                                   'root', password, host_public_key)
    ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)

def get_egress_ip_address(linode_account, ip_address, password, host_public_key):
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                                   'root', password, host_public_key)
    egress_ip = ssh.exec_command("/sbin/ifconfig eth0 | grep 'inet addr' | cut -d: -f2 | awk '{print $1}'")
    return egress_ip.split("\n")[0]

###
#
# Main function
#
###
def get_servers(linode_account):
    linode_api = PsiLinode(linode_account)
    linodes = linode_api.list_linodes()
    return [(str(li.id), li.label) for li in linodes if not li.tags]

def get_server(linode_account, linode_id):
    linode_api = PsiLinode(linode_account)
    linode =linode_api.linode_list(linode_id)
    return linode

def remove_server(linode_account, linode_id):
    linode_api = PsiLinode(linode_account)
    try:
        linode_api.remove_linode(int(linode_id))
    except linode_api4.ApiError as ex:
        # 'Not found' means this server has already been removed
        if 'Not found' not in ex.errors:
            raise ex

def launch_new_server(linode_account, is_TCS, plugins, multi_ip=False):

    linode = None
    linode_id = None
    linode_api = PsiLinode(linode_account) # Use new API interface

    if is_TCS:
        # New APIv4 require root_pass when create disk from image
        root_password = linode_account.tcs_base_root_password
        host_public_key = linode_account.tcs_base_host_public_key
    else:
        # Power on the base image linode if it is not already running
        if linode_api.linode_status(linode_account.base_id) != 'running':
            linode_api.start_linode(linode_account.base_id) # Lagecy psiphon servers, NOT TESTED

        # root_password = linode_account.base_root_password
        # in order to use New APIv4 and make sure the legacy host also working as before, generate a root_password ahead
        root_password = psi_utils.generate_password()
        host_public_key = linode_account.base_host_public_key

    try:
        # Create a new linode
        new_root_password = psi_utils.generate_password()
        linode, datacenter_name, region = linode_api.create_linode()
        
        if multi_ip:
            linode_second_ip_address = linode_api.pubip_allocate(linode)
        
        disk_ids = linode_api.create_linode_disks(linode, root_password, is_TCS, plugins)
        bootstrap_config, psiphon3_host_config = linode_api.create_linode_configurations(linode, disk_ids, is_TCS, plugins, multi_ip)
        
        # Clone the base linode
        linode_ip_details = linode.ips.ipv4.public
        linode_ip_address = linode_ip_details[0].address
        egress_ip_address = None

        linode_rdns_name = linode_ip_details[0].rdns.split('.', 1)[0]
        host_id = 'li-' + region.lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))

        if not is_TCS:
            # Lagecy psiphon servers, NOT TESTED
            linode_api.start_linode(linode.id, config=bootstrap_config_id)
            pave_linode(linode_account, linode_ip_address, root_password)
            linode_api.stop_linode(linode.id)

        linode_api.start_linode(linode.id, config=psiphon3_host_config)
        stats_username = linode_account.base_stats_username

        if is_TCS:
            print(linode.label)
            # Linodes created by an image keep the image's hostname.  Override this
            set_host_name(linode_account, linode_ip_address, root_password,
                          host_public_key, host_id)
            stats_username = psi_utils.generate_stats_username()
            set_allowed_users(linode_account, linode_ip_address, root_password,
                              host_public_key, stats_username)

        # Query hostname
        hostname = get_host_name(linode_account, linode_ip_address, root_password, host_public_key)

        # Change the new linode's credentials
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(linode_account, linode_ip_address,
                                                  root_password, host_public_key,
                                                  new_root_password, new_stats_password,
                                                  stats_username)

        if multi_ip:
            egress_ip_address = get_egress_ip_address(linode_account, linode_ip_address, new_root_password, new_host_public_key)
            linode_ip_address = linode_ip_details[1].address if linode_ip_address == egress_ip_address else linode_ip_address

    except Exception as ex:
        if linode:
            linode_api.remove_linode(linode.id)
        raise ex
    finally:
        # Power down the base image linode
        #stop_linode(linode_api, linode_account.base_id)
        # New: we'll leave this on now due to parallelization
        pass

    return (hostname, is_TCS, 'NATIVE' if is_TCS else None, None, str(linode.id), linode_ip_address,
            linode_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            stats_username, new_stats_password,
            datacenter_name, region, egress_ip_address, None)

if __name__ == "__main__":
    print launch_new_server()
