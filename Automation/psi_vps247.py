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

AUTOMATION_DIR = os.path.abspath(os.path.join('..', 'Automation'))

def add_swap_file(vps247_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, vps247_account.base_ssh_port, 'root', vps247_account.default_root_password, None)
    ssh.exec_command('dd if=/dev/zero of=/swapfile bs=1024 count=1048576 && mkswap /swapfile && chown root:root /swapfile && chmod 0600 /swapfile')
    ssh.exec_command('echo "/swapfile swap swap defaults 0 0" >> /etc/fstab')
    ssh.exec_command('swapon -a')
    
    ssh.close()
    return

def generate_host_id():
    return 'v247-' + ''.join(random.choice(string.ascii_lowercase) for x in range(8))

def random_pick_ragion(regions):
    return random.choice(regions)

def get_region_id(region):
    return region['id']

def reset_root_password(vps247_account, ip_address, init_pass):
    ssh = psi_ssh.make_ssh_session(ip_address, 22, 'debian', None, None, vps247_account.base_rsa_private_key)
    ssh.put_file(AUTOMATION_DIR + "/update_root_password.sh", "/home/debian/update.sh")
    ssh.put_file(AUTOMATION_DIR + "/base_image_init_native.sh", "/home/debian/native.sh")
    
    cmd = 'sh -c "sleep 1; echo '+ init_pass +'" | script -qc "su -c \'bash /home/debian/update.sh\' - root"'
    ssh.exec_command(cmd)
    
    ssh.close()
    return

def install_tcs(vps247_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, 22, 'root', vps247_account.default_root_password, None)
    ssh.exec_command('bash /home/debian/native.sh > /home/debian/installing.log')
    
    ssh.close()
    return

def refresh_credentials(vps247_account, ip_address, new_root_password, new_stats_password, new_stats_username):
    ssh = psi_ssh.make_ssh_session(ip_address, vps247_account.base_ssh_port, 'root', vps247_account.default_root_password, None)
                                   
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('useradd -M -d /var/log -s /bin/sh -g adm %s' % (new_stats_username))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (new_stats_username, new_stats_password))
    
    user_exists = ssh.exec_command('grep %s /etc/ssh/sshd_config' % new_stats_username)
    if not user_exists:
        ssh.exec_command('sed -i "s/^AllowUsers.*/& %s/" /etc/ssh/sshd_config' % new_stats_username)
        ssh.exec_command('service ssh restart')
    
    ssh.exec_command('rm /home/debian/*')
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

def launch_server(vps247_account, is_TCS, _):

    # Try launch New VPS 247 Server

    try:
        v247_api = v247.Api(key=vps247_account.api_key)
               
        # Get random choice region id or use default region id: 25 (ES)
        if vps247_account.default_region_id != 0:
            region_id = vps247_account.default_region_id
        else:
            region_id = get_region_id(random_pick_ragion(v247_api.get_all_regions()))

        # Get preset default package id
        package_id = vps247_account.default_package_id
                   
        # Hostname generator
        hostname = generate_host_id()

        # Create VPS node
        instance_id = v247_api.create_vm(hostname, region_id, package_id)
              
        print 'Waiting for the instance to power on and get instance information'
        time.sleep(30)

        instance = v247_api.get_vm(str(instance_id))

        instance_ip_address = instance['ip_assignments'][0]['ip_address']
        instance_init_password = str(instance['initial_password'])

        print 'Reset init password to default root password'
        reset_root_password(vps247_account, instance_ip_address, instance_init_password)
        print 'Installing TCS Dependencies..'
        install_tcs(vps247_account, instance_ip_address)

        print 'Waiting for TCS installation finished.'
        time.sleep(150) # Time needed to reboot the instances

        add_swap_file(vps247_account, instance_ip_address)
        
        print 'Refreshing Credential..'
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_stats_username = psi_utils.generate_stats_username()
        
        new_host_public_key = refresh_credentials(vps247_account, instance_ip_address, new_root_password, new_stats_password, new_stats_username)

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

    return (host_id, is_TCS, 'NATIVE' if is_TCS else None, None, provider_id, instance_ip_address,
            vps247_account.base_ssh_port, 'root', new_root_password,
            ' '.join(new_host_public_key.split(' ')[:2]),
            new_stats_username, new_stats_password,
            datacenter_name, region_code, None, None, None, None)