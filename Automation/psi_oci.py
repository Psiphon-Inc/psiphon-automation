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
TCS_BASE_IMAGE_NAME = 'Psiphon-TCS-V10.2-20230720'

###
#
# Helper functions
#
###
def reload_api_client(oci_api, instance_id):
    oci_api_region = instance_id.split('.')[3]

    oci_api.config["region"] = oci_api_region
    oci_api.reload()

    return oci_api, instance_id

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
    def __init__(self, oracle_account, debug=False):
        self.config = {
            "user": oracle_account.oci_user,
            "key_content": oracle_account.oci_user_ssh_key,
            "fingerprint": oracle_account.oci_user_ssh_key_fingerprint,
            "tenancy": oracle_account.oci_tenancy_id,
            "compartment": oracle_account.oci_compartment_id,
            "region": random.choice(oracle_account.regions),
            "log_requests": debug
        }

        self.image_source_uri=oracle_account.oci_bucket_image_url
        self.base_image_ssh_authorized_keys = oracle_account.base_image_ssh_public_keys
        
        self.compute_api = oci.core.ComputeClient(self.config)
        self.vcn_api = oci.core.VirtualNetworkClient(self.config)
        self.identity_api = oci.identity.IdentityClient(self.config)
        self.storage_api = oci.core.BlockstorageClient(self.config)

    def reload(self):
        self.compute_api = oci.core.ComputeClient(self.config)
        self.vcn_api = oci.core.VirtualNetworkClient(self.config)
        self.identity_api = oci.identity.IdentityClient(self.config)
        self.storage_api = oci.core.BlockstorageClient(self.config)

    def get_image(self):
        return self.compute_api.list_images(compartment_id=self.config["compartment"], display_name=TCS_BASE_IMAGE_NAME).data[0]

    def get_regions_from_api(self):
        return self.identity_api.list_region_subscriptions(tenancy_id=self.config["tenancy"]).data

    def get_availability_domains(self):
        return self.identity_api.list_availability_domains(compartment_id=self.config["compartment"]).data

    def get_region(self):
        regions = {"ca-montreal-1": "CA",
                   "ca-toronto-1": "CA",
                   "eu-amsterdam-1": "NL",
                   "eu-frankfurt-1": "DE",
                   "eu-madrid-1": "ES",
                   "eu-marseille-1": "FR",
                   "eu-milan-1": "IT",
                   "eu-paris-1": "FR",
                   "eu-stockholm-1": "SE",
                   "eu-zurich-1": "CH",
                   "uk-cardiff-1": "GB",
                   "uk-london-1": "GB",
                   "us-ashburn-1": "US",
                   "us-chicago-1": "US",
                   "us-phoenix-1": "US",
                   "us-sanjose-1": "US"}

        return regions.get(self.config["region"], '')

    def get_datacenter_names(self):
        datacenters = {"ca-montreal-1": "OCI Montreal, CA",
                   "ca-toronto-1": "OCI Toronto, CA",
                   "eu-amsterdam-1": "OCI Amsterdam, NL",
                   "eu-frankfurt-1": "OCI Frankfurt, DE",
                   "eu-madrid-1": "OCI Madrid, ES",
                   "eu-marseille-1": "OCI Marseille, FR",
                   "eu-milan-1": "OCI Milan, IT",
                   "eu-paris-1": "OCI Paris, FR",
                   "eu-stockholm-1": "OCI Stockholm, SE",
                   "eu-zurich-1": "OCI Zurich, CH",
                   "uk-cardiff-1": "OCI Cardiff, GB",
                   "uk-london-1": "OCI London, GB",
                   "us-ashburn-1": "OCI Ashburn, US",
                   "us-chicago-1": "OCI Chicago, US",
                   "us-phoenix-1": "OCI Phoenix, US",
                   "us-sanjose-1": "OCI San Jose, US"}

        return datacenters.get(self.config["region"], '')

    def list_instances(self):
        instances = self.compute_api.list_instances(self.config["compartment"]).data

        return instances

    def get_instance(self, instance_id):
        instance = self.compute_api.get_instance(instance_id).data

        return instance

    def remove_instance(self, instance_id):
        instance = self.compute_api.get_instance(instance_id).data
        self.compute_api.terminate_instance(instance.id)

    def start_instance(self, instance_id):
        # TODO
        pass

    def stop_instance(self, instance_id):
        # TODO
        pass

    def restart_instance(self, instance_id):
        # TODO
        pass

    def resize_boot_volume(self, instance_id, resize_to=200):
        instance = self.compute_api.get_instance(instance_id).data

        boot_volume_attachments = self.compute_api.list_boot_volume_attachments(availability_domain=instance.availability_domain, compartment_id=instance.compartment_id, instance_id=instance.id).data

        boot_volume = self.storage_api.get_boot_volume(boot_volume_id=boot_volume_attachments[0].boot_volume_id).data

        if boot_volume.size_in_gbs < resize_to:
            updated_boot_volume = self.storage_api.update_boot_volume(
                boot_volume_id=boot_volume.id,
                update_boot_volume_details=oci.core.models.UpdateBootVolumeDetails(
                    size_in_gbs=resize_to
                )
            ).data

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
                    memory_in_gbs=4,
                    ocpus=1
                ),
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    source_type="image",
                    image_id=self.get_image().id,
                    boot_volume_size_in_gbs=200
                ),
                metadata={
                    "quake_bot_level" : "Severe", \
                    "ssh_authorized_keys" : self.base_image_ssh_authorized_keys
                }
            )
        ).data

        return instance, self.get_datacenter_names(), self.get_region()
    
    def create_secondary_vnic(self, instance_id):        
        secondary_vnic = self.compute_api.attach_vnic(
            attach_vnic_details=oci.core.models.AttachVnicDetails(
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    assign_public_ip=True,
                    subnet_id=self.vcn_api.list_subnets(compartment_id=self.config["compartment"], display_name="Psiphon 3 Hosts Public Subnet").data[0].id
                ),
                instance_id=instance_id
                ),
            ).data
        
        return secondary_vnic

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
    has_swap = ssh.exec_command('grep swap /etc/fstab')
    if not has_swap:
        ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
        ssh.exec_command('echo "/swapfile swap swap defaults 0 0" >> /etc/fstab')
        ssh.exec_command('swapon -a')

    ssh.close()
    return

def resize_sda1(oracle_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, oracle_account.base_image_ssh_port, 'root', None, None, host_auth_key=oracle_account.base_image_rsa_private_key)
    ssh.exec_command('resize2fs /dev/sda1')
    ssh.close()
    return

###
#
# Main function
#
###
def import_images_to_all_regions(oracle_account):
    oci_api = PsiOCI(oracle_account)

    for region in oracle_account.regions:
        oci_api.config['region'] = region
        oci_api.reload()

        oci_api.create_image()

def get_servers(oracle_account):
    oci_api = PsiOCI(oracle_account)
    instances = []

    for region in oracle_account.regions:
        oci_api.config['region'] = region
        oci_api.reload()

        oci_instances = oci_api.list_instances()
        instances += oci_instances

    return [(instance.id, instance.display_name) for instance in instances if instance.lifecycle_state!='TERMINATED']

def get_server(oracle_account, instance_id):
    oci_api = PsiOCI(oracle_account)
    oci_api, instance_id = reload_api_client(oci_api, instance_id)
    try:
        return oci_api.get_instance(instance_id)
    except Exception as e:
        raise e

def remove_server(oracle_account, instance_id):
    oci_api = PsiOCI(oracle_account)
    oci_api, instance_id = reload_api_client(oci_api, instance_id)
    try:
        oci_api.remove_instance(instance_id)
    except Exception as e:
        raise e

def resize_volume(oracle_account, instance_id, resize_to=200):
    oci_api = PsiOCI(oracle_account)
    oci_api, instance_id = reload_api_client(oci_api, instance_id)
    try:
        oci_api.resize_boot_volume(instance_id, resize_to)
    except Exception as e:
        raise e

def get_server_ip_addresses(oracle_account, instance_id):
    oci_api = PsiOCI(oracle_account) # Use new API interface
    oci_api, instance_id = reload_api_client(oci_api, instance_id)
    vnic_ids = [attachment.vnic_id for attachment in oci_api.compute_api.list_vnic_attachments(compartment_id=oci_api.config["compartment"], instance_id=instance_id).data]
    instance_network = oci_api.vcn_api.get_vnic(
        vnic_id = [vnic_id for vnic_id in vnic_ids if oci_api.vcn_api.get_vnic(vnic_id).data.is_primary == True]
    ).data

    return (instance_network.public_ip, instance_network.private_ip)

def get_secondary_ip_addresses(oracle_account, instance_id):
    oci_api = PsiOCI(oracle_account) # Use new API interface
    oci_api, instance_id = reload_api_client(oci_api, instance_id)
    vnic_ids = [attachment.vnic_id for attachment in oci_api.compute_api.list_vnic_attachments(compartment_id=oci_api.config["compartment"], instance_id=instance_id).data]
    secondary_instance_network = oci_api.vcn_api.get_vnic(
        vnic_id = [vnic_id for vnic_id in vnic_ids if oci_api.vcn_api.get_vnic(vnic_id).data.is_primary == False]
    ).data

    return (secondary_instance_network.public_ip, secondary_instance_network.private_ip)

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
                         60,
                         'Create OCI Instance')

        if multi_ip:
            egress_ip_address, egress_internal_ip_address = get_server_ip_addresses(oracle_account, instance.id)
            secondary_vnic = oci_api.create_secondary_vnic(instance.id)
            wait_while_condition(lambda: oci_api.compute_api.get_vnic_attachment(vnic_attachment_id=secondary_vnic.id).data.lifecycle_state != 'ATTACHED',
                            60,
                            'Attach secondary VNIC')
            time.sleep(15) # This is for the secondary VNIC metadata to be ready
            # Activating secondary Vnic
            ssh = psi_ssh.make_ssh_session(egress_ip_address, oracle_account.base_image_ssh_port, 'root', None, None, host_auth_key=oracle_account.base_image_rsa_private_key)
            ssh.exec_command('bash /opt/egress_ip.sh -c')
            ssh.exec_command('sed -i "/exit 0/i \\bash /opt/egress_ip.sh -c" /etc/rc.local')
            ssh.close()

            instance_ip_address, instance_internal_ip_address = get_secondary_ip_addresses(oracle_account, instance.id)
            
        else:
            instance_ip_address, instance_internal_ip_address = get_server_ip_addresses(oracle_account, instance.id)

        new_stats_username = psi_utils.generate_stats_username()
        
        set_host_name(oracle_account, instance_ip_address, host_id)
        set_allowed_users(oracle_account, instance_ip_address, new_stats_username)
        add_swap_file(oracle_account, instance_ip_address)
        resize_sda1(oracle_account, instance_ip_address)

        # Change the new oci instance's credentials
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_host_public_key = refresh_credentials(oracle_account, instance_ip_address,
                                                  new_root_password, new_stats_password,
                                                  new_stats_username)

        assert(new_host_public_key)

    except Exception as ex:
        if instance:
            oci_api.remove_instance(instance.id)
        raise ex

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None,
            instance.id, instance_ip_address,
            oracle_account.base_image_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region, egress_ip_address if multi_ip else None, instance_internal_ip_address)

if __name__ == '__main__':
    print(launch_new_server())
