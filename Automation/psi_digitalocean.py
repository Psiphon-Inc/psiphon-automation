#!/usr/bin/python
#
# Copyright (c) 2013, Psiphon Inc.
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

import sys
import random
import string
import time

import psi_utils
import psi_ssh

import digitalocean.DigitalOceanAPI


# A default public image
_PUBLIC_IMAGE = {'distribution': 'Debian', 'slug': None, 'public': True, 
                 'id': 12573, 'name': 'Debian 6.0 x64'}

# Our preferred image settings
# Region : Amsterdam, Image: Debian 6 x64, Size: 1GB
_DEFAULT_IMAGE_PARAMS = {'region_id': 2, 'image_id': 12573, 'size_id': 63}


def check_default_image(do_api, default_image):
    images = do_api.get_all_images()
    return (default_image in images)

def show_running_droplets():
        do_api=digitalocean.DigitalOceanAPI.DigitalOceanAPI(digitalocean_account.client_id,
                                                            digitalocean_account.api_key)
        resp = do_api.get_running_droplets()
        print 'Running Droplets: %s' % (len(resp))
        print '%s' % ([l for l in resp])

def check_response(resp):
    if resp['status'] == 'OK':
        return resp
    else:
        print 'Invalid Response: %s ' % (resp['status'])
        sys.exit()

def wait_on_event_completion(do_api, event_id, interval=10):
    for attempt in range(10):
        resp = check_response(do_api.get_event(event_id))
        if resp['event']['action_status'] == 'done':
            return True
        print '%s. event %s status: %s - trying again in %ss' % (str(attempt), str(event_id), resp['event']['action_status'], interval)
        time.sleep(int(interval))
    print 'Event %s did not complete in time' % (str(event_id))
    return False

def stop_droplet(droplet_id):
    do_api=digitalocean.DigitalOceanAPI.DigitalOceanAPI(digitalocean_account.client_id,
                                                        digitalocean_account.api_key)
    print 'Powering down droplet: %s' % (droplet_id)
    droplet_off = check_response(do_api.droplet_power_off(droplet_id))
    if not wait_on_event_completion(do_api, droplet_off['event_id'], interval=60):
        droplet_state = check_response(do_api.droplet_show(droplet_id))['droplet']['status']
        if droplet_state == 'off':
            return True
        else:
            print 'Problem powering droplet off, droplet state: %s' % (str(droplet_state))
            raise Exception

def start_droplet(droplet_id):
    do_api=digitalocean.DigitalOceanAPI.DigitalOceanAPI(digitalocean_account.client_id,
                                                        digitalocean_account.api_key)
    print 'Powering on droplet: %s' % (droplet_id)
    droplet_state = check_response(do_api.droplet_power_on(droplet_id))
    if not wait_on_event_completion(do_api, droplet_state['event_id'], interval=60):
        droplet_state = check_response(do_api.droplet_show(droplet_id))['droplet']['status']
        if droplet_state == 'active':
            return True
        else:
            print 'Problem powering droplet on, droplet state: %s' (str(droplet_state))
            raise Exception

def take_snapshot(digitalocean_account, droplet_id, snapshot_name={'name': None}):
    do_api = digitalocean.DigitalOceanAPI.DigitalOceanAPI(digitalocean_account.client_id,
                                                          digitalocean_account.api_key)
    resp = check_response(do_api.droplet_show(droplet_id))
    droplet_state = resp['droplet']['status']
    droplet_id = resp['droplet']['id']
    try:
        if droplet_state == 'active': # droplet is on
            print 'Powering down droplet: %s' % (droplet_id)
            stop_droplet(droplet_id, do_api)
        print 'Beginning snapshot'
        resp = check_response(do_api.droplet_snapshot(droplet_id, snapshot_name))
        if not wait_on_event_completion(do_api, resp['event_id'], interval=60):
            print 'Could not take snapshot'
            raise
        # We are not sure what state the droplet will be returned in. (one would assume the state it was previously in
        print 'Snapshot complete, restoring droplet to previous state'
        if droplet_state == 'active':
            if not wait_on_event_completion(do_api, check_response(do_api.droplet_power_on(droplet_id))['event_id'], interval=10):
                raise
        else:
            stop_droplet(droplet_id)
        return resp
    except Error as e:
        print '%s' % (e)


def get_datacenter_region(location):
    #[{u'slug': u'nyc1', u'id': 1, u'name': u'New York 1'}, 
    # {u'slug': u'ams1', u'id': 2, u'name': u'Amsterdam 1'}, 
    # {u'slug': u'sfo1', u'id': 3, u'name': u'San Francisco 1'}, 
    # {u'slug': u'nyc2', u'id': 4, u'name': u'New York 2'}]
    if location in [1, 3, 4]:
        return 'US'
    if location in [2]:
        return 'NL'
    return ''

def generate_random_string(prefix=None, size=8):
    if not prefix:
        prefix=''
    return '%s%s' % (prefix, ''.join(random.choice(string.ascii_lowercase) for x in range(size)))

def refresh_credentials(digitalocean_account, ip_address, new_root_password, new_stats_password, pkey):
    ssh = psi_ssh.make_ssh_session(ip_address, digitalocean_account.base_ssh_port, 'root', digitalocean_account.base_host_public_key, None, pkey)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (digitalocean_account.base_stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')


def launch_new_server(digitalocean_account, params=None, use_public_image=False):
    
    image_params = {'name': None,
                    'size_id': None,
                    'image_id': None,
                    'region_id': None, 
                    'ssh_key_ids': [],
                    }
    
    try:
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        do_api = digitalocean.DigitalOceanAPI.DigitalOceanAPI(digitalocean_account.client_id,
                                                              digitalocean_account.api_key)
        
        if params:
            image = dict(image_params.items() + params.items())
        else:
            image = dict(image_params.items() + _DEFAULT_IMAGE_PARAMS.items())
        
        if use_public_image:
            result = check_default_image(do_api, _PUBLIC_IMAGE)
            if not result:
                raise 'Could not find default public image\n'
            else:
                image['image_id'] = _PUBLIC_IMAGE['id']
        else:
            image['image_id'] = digitalocean_account.base_id
        
        regions = do_api.get_all_regions()
        if image['region_id']:
            # Check region availability
            if image['region_id'] not in [region['id'] for region in regions]:
                raise('Region not available')
        else:
            image['reigon_id'] = random.choice([region['id'] for region in regions])

        for r in regions:
            if image['region_id'] == r['id']:
                print 'Using region: %s' % (r['name'])
                break
        
        if not image['size_id']:
            image['size_id'] = _DEFAULT_IMAGE_PARAMS['size_id']
        
        # get a list of image sizes and see if the size is available (maybe some checks)
        droplet_sizes = do_api.get_all_droplet_sizes()
        if image['size_id'] not in [size['id'] for size in droplet_sizes]:
            raise('Droplet size not available')
                    
        if not image['name']:
            # Hostname generator
            image['name'] = generate_random_string(prefix=('do-' + str(image['region_id']) + str(image['size_id']) + '-'))
    
        if not image['ssh_key_ids']:
            image['ssh_key_ids'] = digitalocean_account.ssh_key_template_id
        
        print 'Launching %s, using image %s' % (image['name'], str(image['image_id']))
        resp = do_api.create_new_droplet(image)
        wait_on_event_completion(do_api, resp['droplet']['event_id'])
        print 'Waiting for the droplet to power on and get an IP address'
        time.sleep(30)
        # get more details about droplet
        droplet = do_api.droplet_show(resp['droplet']['id'])['droplet']

        start_droplet(droplet['id'])
        
        provider_id = 'do-' + str(droplet['id'])
        region = get_datacenter_region(droplet['region_id'])
        datacenter_name = next((r for r in regions if r['id'] == droplet['region_id']), None)['name']
        
        new_host_publickey = refresh_credentials(digitalocean_account, droplet['ip_address'], 
                                                new_root_password, new_stats_password, image['ssh_key_ids'])
        
    except Exception as e:
        print 'Exception %s' % (str(e))
        remove_droplet(digitalocean_account, droplet['id'])

    
    return (image['name'], None, provider_id, droplet['ip_address'],
            digitalocean_account.base_ssh_port, 'root', 
            new_root_password, ' '.join(new_host_public_key.split(' ')[:2]),
            digitalocean_account.base_stats_username, new_stats_password, 
            datacenter_name, region)

def remove_droplet(digitalocean_account, droplet_id):
    do_api = digitalocean.DigitalOceanAPI.DigitalOceanAPI(digitalocean_account.client_id, digitalocean_account.api_key)
    try:
        do_api.droplet_destroy(droplet_id)
    except Exception as e:
        raise e

if __name__ == "__main__":
    print launch_new_server(digitalocean_account)
    
