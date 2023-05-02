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

# Import OCI Official Python Library
# Requirement: pip install oci
import oci

# VARIABLE
TCS_BASE_IMAGE_NAME = 'Psiphon-TCS-V9.1-20230427'

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
class PsiOCI:
    def __init__(self, oracle_account):
        self.config = {
            "user": oracle_account.oci_user,
            "key_content": oracle_account.oci_user_ssh_key,
            "fingerprint": oracle_account.oci_user_ssh_key_fingerprint,
            "tenancy": oracle_account.oci_tenancy_id,
            "compartment": oracle_account.oci_compartment_id,
            "region": random.choice(oracle_account.regions),
            "log_requests": True
        }

        self.image_source_uri=oracle_account.oci_bucket_image_url
        self.base_image_ssh_authorized_keys = oracle_account.base_image_ssh_public_keys
        
        self.compute_api = oci.core.ComputeClient(self.config)
        self.vcn_api = oci.core.VirtualNetworkClient(self.config)
        self.identity_api = oci.identity.IdentityClient(self.config)

    def reload(self):
        self.compute_api = oci.core.ComputeClient(self.config)
        self.vcn_api = oci.core.VirtualNetworkClient(self.config)
        self.identity_api = oci.identity.IdentityClient(self.config)

    def get_image(self):
        return self.compute_api.list_images(compartment_id=self.config["compartment"], display_name=TCS_BASE_IMAGE_NAME).data[0]

    def get_regions_from_api(self):
        return self.identity_api.list_region_subscriptions(tenancy_id=self.config["tenancy"]).data

    def get_availability_domains(self):
        return self.identity_api.list_availability_domains(compartment_id=self.config["compartment"]).data

    def get_region(self):
        regions = {"ca-toronto-1": "CA",
                   "eu-marseille-1": "FR",
                   "eu-frankfurt-1": "DE",
                   "eu-milan-1": "IT",
                   "eu-amsterdam-1": "NL",
                   "eu-madrid-1": "ES",
                   "eu-stockholm-1": "SE",
                   "eu-zurich-1": "CH",
                   "uk-cardiff-1": "GB",
                   "us-phoenix-1": "US"}

        return regions.get(self.config["region"], '')

    def get_datacenter_names(self):
        datacenters = {"ca-toronto-1": "OCI Toronto, CA",
                   "eu-marseille-1": "OCI Marseille, FR",
                   "eu-frankfurt-1": "OCI Frankfurt, DE",
                   "eu-milan-1": "OCI Milan, IT",
                   "eu-amsterdam-1": "OCI Amsterdam, NL",
                   "eu-madrid-1": "OCI Madrid, ES",
                   "eu-stockholm-1": "OCI Stockholm, SE",
                   "eu-zurich-1": "OCI Zurich, CH",
                   "uk-cardiff-1": "OCI Cardiff, GB",
                   "us-phoenix-1": "OCI Phoenix, US"}

        return datacenters.get(self.config["region"], '')

    def list_instances(self):
        # TODO
        pass

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

    def create_image(self):
        image = self.compute_api.create_image(
            create_image_details=oci.core.models.CreateImageDetails(
                compartment_id=self.config["compartment"],
                display_name=TCS_BASE_IMAGE_NAME,
                launch_mode="PARAVIRTUALIZED",
                image_source_details=oci.core.models.ImageSourceViaObjectStorageUriDetails(
                    source_image_type="QCOW2", \
                    operating_system="Linux", \
                    source_type="objectStorageUri", \
                    source_uri=self.image_source_uri
                )
            )
        ).data

        return image
    
    def create_instance(self, host_id):
        instance = self.compute_api.launch_instance(
            launch_instance_details=oci.core.models.LaunchInstanceDetails(
                display_name=host_id,
                availability_domain=random.choice(self.get_availability_domains()).name,
                compartment_id=self.config["compartment"],
                image_id=self.get_image().id,
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    assign_public_ip=True,
                    subnet_id=self.vcn_api.list_subnets(compartment_id=self.config["compartment"], display_name="Psiphon 3 Hosts Public Subnet").data[0].id
                ),
                shape="VM.Standard.E4.Flex",
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    memory_in_gbs=16,
                    ocpus=4
                ),
                metadata={
                    "quake_bot_level" : "Severe", \
                    "ssh_authorized_keys" : self.base_image_ssh_authorized_keys
                }
            )
        ).data

        return instance, self.get_datacenter_names(), self.get_region()
###
#
# Server side SSH Interaction functions (Migrated from old code)
#
###
def refresh_credentials(oracle_account, ip_address, new_root_password, new_stats_password, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (stats_username))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

def set_allowed_users(oracle_account, ip_address, stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % stats_username)
    if not user_exists:
        ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % stats_username)
        ssh.exec_command('service ssh restart')

def get_host_name(oracle_account, ip_address):
    # Note: using base image credentials; call before changing credentials
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root',None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    return ssh.exec_command('hostname').strip()

def set_host_name(oracle_account, ip_address, new_hostname):
    # Note: hostnamectl is for systemd servers
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port,
                                   'root', None, None,
                                   host_auth_key=oracle_account.base_image_rsa_private_key)
    ssh.exec_command('hostnamectl set-hostname %s' % new_hostname)

def add_swap_file(oracle_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port, 'root', None, None, host_auth_key=oracle_account.base_image_rsa_private_key)
    ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
    ssh.exec_command('echo "/swapfile swap swap defaults 0 0" >> /etc/fstab')
    ssh.exec_command('swapon -a')

    ssh.close()
    return
###
#
# Main function
#
###
def get_servers(oracle_account):
    # TODO
    pass

def get_server(oracle_account, instance_id):
    # TODO
    pass

def remove_server(oracle_account, instance_id):
    # TODO
    pass

def get_server_ip_addresses(oracle_account, instance_id):
    oci_api = PsiOCI(oracle_account) # Use new API interface

    instance_network = oci_api.vcn_api.get_vnic(
        oci_api.compute_api.list_vnic_attachments(
            compartment_id=oci_api.config["compartment"], instance_id=instance_id
        ).data[0].vnic_id
    ).data

    return (instance_network.public_ip, instance_network.private_ip)

def launch_new_server(oracle_account, is_TCS, plugins, multi_ip=False):

    instance = None
    oci_api = PsiOCI(oracle_account) # Use new API interface

    try:
        # Create a new OCI instance
        region = oci_api.get_region()
        datacenter = oci_api.get_datacenter_names()
        host_id = 'oci' + '-' + region.lower() + datacenter[4:7].lower() + ''.join(random.choice(string.ascii_lowercase) for x in range(8))
        instance, datacenter_name, region = oci_api.create_instance(host_id)

        # Wait for job completion
        wait_while_condition(lambda: oci_api.compute_api.get_instance(instance.id).data.lifecycle_state != 'RUNNING',
                         30,
                         'Create OCI Instance')

        instance_ip_address, instance_internal_ip_address = get_server_ip_addresses(oracle_account, instance.id)

        new_stats_username = psi_utils.generate_stats_username()
        
        set_host_name(oracle_account, instance_ip_address, host_id)
        set_allowed_users(oracle_account, instance_ip_address, new_stats_username)
        add_swap_file(oracle_account, instance_ip_address)

        # Change the new oci instance's credentials
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(oracle_account, instance_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

    except Exception as ex:
        if instance:
            # TODO: Remove instance if failure
            pass
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            instance.id, instance_ip_address,
            oracle_account.base_image_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, None, instance_internal_ip_address)

if __name__ == '__main__':
    print(launch_new_server())
