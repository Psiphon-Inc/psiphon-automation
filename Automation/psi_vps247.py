# NOTES: DO NOT USE THIS. HAVEN'T TEST.
# NOTES: DO NOT USE THIS. HAVEN'T TEST.
# NOTES: DO NOT USE THIS. HAVEN'T TEST.
import os
import sys
import time
import random
import string

try:
    from VPS247 import api as v247
except ImportError as e:
    raise e

import psi_utils
import psi_ssh

def generate_host_id():
    return 'v247-' + ''.join(random.choice(string.ascii_lowercase) for x in range(8))

def random_pick_ragion(regions):
    return random.choice(regions)

def get_region_id(region):
    return region['id']

def refresh_credentials(vps247_account, ip_address, new_root_password, new_stats_password, new_stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, vps247_account.base_ssh_port, 'debian', None, None, vps247_account.base_rsa_private_key)
                                   
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (new_stats_username))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (new_stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

def launch_server(vps247_account, is_TCS, _):

    # Try launch New VPS 247 Server

    try:
        v247_api = v247.Api(key=vps247_account.api_key)
               
        # Get random choice region id
        region_id = get_region_id(random_pick_ragion(v247_api.get_all_regions()))

        # Get preset default package id
        package_id=vps247_account.default_package_id
                   
        # Hostname generator
        hostname = generate_host_id()

        # Create VPS node
        instance_id = v247_api.create_vm(hostname, region_id, package_id)
              
        print 'Waiting for the droplet to power on and get an IP address'
        time.sleep(30)

        instance = v247_api.get_vm(instance_id)

        ip_address = instance['ip_assignments'][0]['ip_address']

        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_stats_username = psi_utils.generate_stats_username()

        new_host_public_key = refresh_credentials(vps247_account, ip_address, password, host_public_key, new_root_password, new_stats_password, new_stats_username)

    except Exception as e:
        print type(e), str(e)
        if instance:
            # TODO: If instance exist, delete the instance.
            pass
        raise

    # Get all informations
    host_id = instance['name']
    provider_id = str(instance['id'])
    region_code = v247_api.get_region(str(instance['region_id']))['country_code']
    datacenter_name = 'VPS247 ' + region_code

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None, provider_id, ip_address,
            vps247_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region_code, None, None, None, None)