#!/usr/bin/python
#
# Copyright (c) 2014, Psiphon Inc.
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

import collections
import random
import string
import time

import psi_utils
import psi_ssh

import digitalocean

def refresh_credentials(digitalocean_account, ip_address, new_root_password, new_stats_password):
    # Note: using auto-add-policy for host's SSH public key here since we can't get it through the API.
    # There's a risk of man-in-the-middle.
    ssh = psi_ssh.make_ssh_session(ip_address, digitalocean_account.base_ssh_port, 'root', None, None, digitalocean_account.base_rsa_private_key)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (digitalocean_account.base_stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

def update_system_packages(digitalocean_account, ip_address):
    ssh = psi_ssh.make_ssh_session(ip_address, digitalocean_account.base_ssh_port, 'root', None, None, digitalocean_account.base_rsa_private_key)
    ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && aptitude update -q && aptitude safe-upgrade -y -o Dpkg::Options::="--force-confdef"')

def get_datacenter_region(region):
    '''
        nyc1 New York 1
        ams1 Amsterdam 1
        sfo1 San Francisco
        nyc2 New York 2
        ams2 Amsterdam 2
        sgp1 Singapore 1
        lon1 London 1
        nyc3 New York 3
        ams3 Amsterdam 3
    '''
    if 'nyc' or 'sfo' in region:
        return 'US'
    if 'ams' in region:
        return 'NL'
    if 'sgp' in region:
        return 'SG'
    if 'lon' in region:
        return 'GB'
    return ''

def wait_on_action(droplet=None, interval=10, action_type='create', action_status='completed'):
    """
        Check an action periodically
    """
    try:
        if droplet is None:
            raise 'Droplet not defined'
        
        droplet_actions = droplet.get_actions()
        for attempt in range(10):
            droplet_actions = droplet.get_actions()
            if len(droplet_actions) < 1:
                time.sleep(int(interval))
                continue
            for action in droplet_actions:
                if action.type == action_type and action.status == action_status:
                    return True
            print '%s. %s - %s not found - trying again in %ss' % (str(attempt), action_type, action_status, interval)
            time.sleep(int(interval))
    except Exception as e:
        raise e
    
    return False

def get_image_by_id(digitalocean_account=None, image_id=None):
    try:
        do_image = digitalocean.Image(token=digitalocean_account.oauth_token, 
                                          id=image_id)
        image = do_image.load()
        return image
    except Exception as e:
        raise e

def get_droplet_by_id(digitalocean_account=None, droplet_id=None):
    try:
        do_droplet = digitalocean.Droplet(token=digitalocean_account.oauth_token, 
                                          id=droplet_id)
        droplet = do_droplet.load()
        return droplet
    except Exception as e:
        raise e

def update_image(digitalocean_account=None, droplet_id=None, droplet_name=None, droplet_size=None):
    try:
        if not digitalocean_account:
            raise Exception('DigitalOcean account must be provided')

        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 
                                                     'size', 'backups'])

        base_droplet = get_image_by_id(digitalocean_account, digitalocean_account.base_id)
        base_droplet = base_droplet.load()

        Droplet.image = base_droplet.id if not droplet_id else droplet_id
        Droplet.name = base_droplet.name if not droplet_name else droplet_name
        Droplet.size = digitalocean_account.base_size_slug if not droplet_size else droplet_size
        Droplet.region = base_droplet.regions[0] if len(base_droplet.regions) > 0 else 'nyc1'

        sshkeys = do_mgr.get_all_sshkeys()
        # treat sshkey id as unique
        if not unicode(digitalocean_account.ssh_key_template_id) in [unicode(k.id) for k in sshkeys]:
            raise 'No SSHKey found'

        droplet = digitalocean.Droplet(token=digitalocean_account.oauth_token,
                                       name=Droplet.name,
                                       region=Droplet.region,
                                       image=Droplet.image,
                                       size=Droplet.size,
                                       backups=False)

        droplet.create(ssh_keys=str(digitalocean_account.ssh_key_template_id))
        if not wait_on_action(droplet, interval=30, action_type='create', action_status='completed'):
            raise Exception('Event did not complete in time')

        droplet = get_droplet_by_id(digitalocean_account, droplet.id)
        update_system_packages(digitalocean_account, droplet.ip_address)
    except Exception as e:
        print type(e), str(e)

def launch_new_server(digitalocean_account, _):
    try:
        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 
                                                     'size', 'backups'])

        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()

        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)

        # Get the base image
        base_droplet = get_image_by_id(digitalocean_account, digitalocean_account.base_id)
        Droplet.image = base_droplet.id

        Droplet.name = str('do-' + 
                           ''.join(random.choice(string.ascii_lowercase) for x in range(8)))

        # Set the default size
        droplet_sizes = do_mgr.get_all_sizes()
        if not unicode(digitalocean_account.base_size_slug) in [unicode(s.slug) for s in droplet_sizes]:
            raise 'Size slug not found'

        Droplet.size = digitalocean_account.base_size_slug

        droplet_regions = do_mgr.get_all_regions()
        common_regions = list(set([r.slug for r in droplet_regions if r.available])
                                 .intersection(base_droplet.regions))

        Droplet.region = random.choice(common_regions)

        sshkeys = do_mgr.get_all_sshkeys()
        # treat sshkey id as unique
        if not unicode(digitalocean_account.ssh_key_template_id) in [unicode(k.id) for k in sshkeys]:
            raise 'No SSHKey found'

        droplet = digitalocean.Droplet(token=digitalocean_account.oauth_token,
                                       name=Droplet.name,
                                       region=Droplet.region,
                                       image=Droplet.image,
                                       size=Droplet.size,
                                       backups=False)

        droplet.create(ssh_keys=str(digitalocean_account.ssh_key_template_id))
        if not wait_on_action(droplet, interval=30, action_type='create', action_status='completed'):
            raise Exception('Event did not complete in time')

        droplet = get_droplet_by_id(digitalocean_account, droplet.id)
        
        region = get_datacenter_region(droplet.region['slug'])
        datacenter_name = 'Digital Ocean ' + droplet.region['name']
        
        new_droplet_public_key = refresh_credentials(digitalocean_account, 
                                                     droplet.ip_address, 
                                                     new_root_password, 
                                                     new_stats_password)
        assert(new_droplet_public_key)
    
    except Exception as e:
        print type(e), str(e)
        if droplet != None:
            droplet.destroy()
        else:
            print type(e), "No droplet to be destroyed: ", str(droplet)
        raise
    
    return (droplet.name, None, droplet.id, droplet.ip_address, 
            digitalocean_account.base_ssh_port, 'root', new_root_password, 
            ' '.join(new_droplet_public_key.split(' ')[:2]),
            digitalocean_account.base_stats_username, new_stats_password,
            datacenter_name, region, None, None, None, None)
