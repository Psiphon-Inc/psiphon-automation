#!/usr/bin/python
#
# Copyright (c) 2011, Psiphon Inc.
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
import linode.api


#==============================================================================


def wait_while_condition(condition, max_wait_seconds, description):
    total_wait_seconds = 0
    wait_seconds = 1
    while condition() == True:
        if total_wait_seconds > max_wait_seconds:
            raise Exception('Took more than %d seconds to %s' % (max_wait_seconds, description))
        time.sleep(wait_seconds)
        total_wait_seconds = total_wait_seconds + wait_seconds
        

def create_linode(linode_api):
    datacenter_id = random.choice(linode_api.avail_datacenters())['DATACENTERID']
    # We use PlanID = 3: linode 1024
    new_node_id = linode_api.linode_create(DatacenterID=datacenter_id, PlanID=3, PaymentTerm=1)['LinodeID']
    # Status flag values: (partial list)
    # -1: Being Created
    #  0: Brand New
    wait_while_condition(lambda: linode_api.linode_list(LinodeID=new_node_id)[0]['STATUS'] == -1,
                         30,
                         'create a linode')
    assert(linode_api.linode_list(LinodeID=new_node_id)[0]['STATUS'] == 0)
    return new_node_id


def create_linode_disks(linode_api, linode_id, bootstrap_password):
    # DistributionID = 77: Debian 6
    create_disk_job = linode_api.linode_disk_createfromdistribution(LinodeID=linode_id, DistributionID=77, rootPass=bootstrap_password, Label='Psiphon 3 Disk Image', Size=40704)
    wait_while_condition(lambda: linode_api.linode_job_list(LinodeID=linode_id, JobID=create_disk_job['JobID'])[0]['HOST_SUCCESS'] == '',
                         120,
                         'create a disk from distribution')
    assert(linode_api.linode_job_list(LinodeID=linode_id, JobID=create_disk_job['JobID'])[0]['HOST_SUCCESS'] == 1)
    
    create_swap_job = linode_api.linode_disk_create(LinodeID=linode_id, Type='swap', Label='Psiphon 3 Swap', Size=256)
    wait_while_condition(lambda: linode_api.linode_job_list(LinodeID=linode_id, JobID=create_swap_job['JobID'])[0]['HOST_SUCCESS'] == '',
                         30,
                         'create a swap disk')
    assert(linode_api.linode_job_list(LinodeID=linode_id, JobID=create_swap_job['JobID'])[0]['HOST_SUCCESS'] == 1)

    return str(create_disk_job['DiskID']), str(create_swap_job['DiskID'])

    
def create_linode_configurations(linode_api, linode_id, disk_list):
    # KernelID = 110: Latest 2.6
    bootstrap_config_id = linode_api.linode_config_create(LinodeID=linode_id, KernelID=110, Label='BootStrap', DiskList=disk_list)
    # KernelID = 92: pv-grub-x86_32
    psiphon3_host_config_id = linode_api.linode_config_create(LinodeID=linode_id, KernelID=92, Label='Psiphon 3 Host', DiskList=disk_list, helper_xen=0)
    return bootstrap_config_id['ConfigID'], psiphon3_host_config_id['ConfigID']
    

def start_linode(linode_api, linode_id, config_id):
    if config_id:
        boot_job_id = linode_api.linode_boot(LinodeID=linode_id, ConfigID=config_id)['JobID']
    else:
        boot_job_id = linode_api.linode_boot(LinodeID=linode_id)['JobID']
    wait_while_condition(lambda: linode_api.linode_job_list(LinodeID=linode_id, JobID=boot_job_id)[0]['HOST_SUCCESS'] == '',
                         60,
                         'boot the linode')
    assert(linode_api.linode_job_list(LinodeID=linode_id, JobID=boot_job_id)[0]['HOST_SUCCESS'] == 1)
    
    
def stop_linode(linode_api, linode_id):
    shutdown_job_id = linode_api.linode_shutdown(LinodeID=linode_id)['JobID']
    wait_while_condition(lambda: linode_api.linode_job_list(LinodeID=linode_id, JobID=shutdown_job_id)[0]['HOST_SUCCESS'] == '',
                         60,
                         'shutdown the linode')
    assert(linode_api.linode_job_list(LinodeID=linode_id, JobID=shutdown_job_id)[0]['HOST_SUCCESS'] == 1)
    

def pave_linode(linode_account, ip_address, password):
    # Note: using auto-add-policy for host's SSH public key here since we can't get it through the Linode API.
    # There's a risk of man-in-the-middle.
    ssh = psi_ssh.make_ssh_session(ip_address, 22, 'root', password, None)
    ssh.exec_command('mkdir -p /root/.ssh')
    ssh.exec_command('echo "%s" > /root/.ssh/known_hosts' % (linode_account.base_known_hosts_entry,))
    ssh.exec_command('echo "%s" > /root/.ssh/id_rsa' % (linode_account.base_rsa_private_key,))
    ssh.exec_command('chmod 600 /root/.ssh/id_rsa')
    ssh.exec_command('echo "%s" > /root/.ssh/id_rsa.pub' % (linode_account.base_rsa_public_key,))
    ssh.exec_command('scp -P %d root@%s:%s /' % (linode_account.base_ssh_port,
                                                 linode_account.base_ip_address,
                                                 linode_account.base_tarball_path))
    ssh.exec_command('apt-get install -y bzip2 &> /dev/null')
    ssh.exec_command('tar xvpfj %s -C / &> /dev/null' % (linode_account.base_tarball_path,))
    
    
def refresh_credentials(linode_account, ip_address, new_root_password, new_stats_password):
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                               'root', linode_account.base_root_password,
                               linode_account.base_host_public_key)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (linode_account.base_stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')


def get_host_name(linode_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, linode_account.base_ssh_port,
                               'root', linode_account.base_root_password,
                               linode_account.base_host_public_key)
    return ssh.exec_command('hostname').strip()

    
def launch_new_server(linode_account):
    linode_api = linode.api.Api(key=linode_account.api_key)
    
    # Power on the base image linode
    start_linode(linode_api, linode_account.base_id, None)
    
    # Create a new linode
    new_root_password = psi_utils.generate_password()
    linode_id = create_linode(linode_api)
    disk_ids = create_linode_disks(linode_api, linode_id, new_root_password)
    bootstrap_config_id, psiphon3_host_config_id = create_linode_configurations(linode_api, linode_id, ','.join(disk_ids))
    start_linode(linode_api, linode_id, bootstrap_config_id)
    
    # Clone the base linode
    linode_ip_address = linode_api.linode_ip_list(LinodeID=linode_id)[0]['IPADDRESS']
    pave_linode(linode_account, linode_ip_address, new_root_password)
    stop_linode(linode_api, linode_id)
    start_linode(linode_api, linode_id, psiphon3_host_config_id)
    
    # Power down the base image linode
    stop_linode(linode_api, linode_account.base_id)

    # Query hostname
    hostname = get_host_name(linode_account, linode_ip_address)

    # Change the new linode's credentials
    new_stats_password = psi_utils.generate_password()
    new_host_public_key = refresh_credentials(linode_account, linode_ip_address, new_root_password, new_stats_password)

    return (hostname, None, str(linode_id), linode_ip_address,
            linode_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            linode_account.base_stats_username, new_stats_password)


def remove_server(linode_account, server_id):
    linode_api = linode.api.Api(key=linode_account.api_key)
    linode_api.linode_delete(LinodeID=server_id, skipChecks=True)
    
    
if __name__ == "__main__":
    print launch_new_server()
