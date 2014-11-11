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

from digitalocean_v1.DigitalOceanAPI import DigitalOceanAPI

def check_default_image(do_api, default_image):
    images = do_api.get_all_images()
    return (default_image in images)

def get_image_by_id(do_api, droplet_id):
    return do_api.droplet_show(droplet_id)

def show_running_droplets(do_api):
        
        resp = do_api.get_running_droplets()
        print 'Running Droplets: %s' % (len(resp))
        print '%s' % ([l for l in resp])

def check_response(resp):
    if resp['status'] != 'OK':
        print 'Invalid Response: %s ' % (resp['status'])
    return resp

def wait_on_event_completion(do_api, event_id, interval=10):
    for attempt in range(10):
        resp = check_response(do_api.get_event(event_id))
        if resp['event']['action_status'] == 'done':
            return True
        print '%s. %s status: %s - trying again in %ss' % (str(attempt), str(event_id), resp['event']['action_status'], interval)
        time.sleep(int(interval))
    print 'Event %s did not complete in time' % (str(event_id))
    return False

def stop_droplet(do_api, droplet_id):
    print 'Powering down droplet: %s' % (droplet_id)
    droplet_off = check_response(do_api.droplet_power_off(droplet_id))
    if not wait_on_event_completion(do_api, droplet_off['event_id'], interval=60):
        droplet_state = check_response(do_api.droplet_show(droplet_id))['droplet']['status']
        if droplet_state == 'off':
            return True
        else:
            print 'Problem powering droplet off, droplet state: %s' % (str(droplet_state))
            raise Exception
    return True

def start_droplet(do_api, droplet_id):
    print 'Powering on droplet: %s' % (droplet_id)
    droplet_state = check_response(do_api.droplet_power_on(str(droplet_id)))
    if not wait_on_event_completion(do_api, droplet_state['event_id'], interval=60):
        droplet_state = check_response(do_api.droplet_show(droplet_id))['droplet']['status']
        if droplet_state == 'active':
            return True
        else:
            print 'Problem powering droplet on, droplet state: %s' (str(droplet_state))
            raise Exception
    return True

def update_image(digitalocean_account, droplet_id, droplet_name):
    try:
        do_api = DigitalOceanAPI(digitalocean_account.client_id, digitalocean_account.api_key)
        
        result = take_snapshot(do_api, droplet_id, {'name': droplet_name})
        if 'OK' in result['status']:
            images = do_api.get_all_images()
            new_image = [i for i in images if droplet_name in i['name']][0]
            
            regions = do_api.get_all_regions()
            results = []
            for r in regions:
                results.append(do_api.image_transfer(new_image['id'], {'region_id': r['id']}))
            #wait a while for the image to be transferred across regions
            success_ids = [r['event_id'] for r in results if 'OK' in r['status']]
            for id in success_ids:
                if not wait_on_event_completion(do_api, id, interval=120):
                    raise Exception('Could not update image')
            
            images = do_api.get_all_images()
            image = [i for i in images if droplet_name in i['name']][0]
            if image['regions'] == [r['id'] for r in regions]:
                print 'Image creation and transfer complete. Remove the outdated image'
                return image
            else:
                print 'Image was not transferred successfully'
                raise
    except Exception as e:
        print '%s' % (e)

def take_snapshot(do_api, droplet_id, snapshot_name={'name': None}):
    resp = check_response(do_api.droplet_show(droplet_id))
    droplet_state = resp['droplet']['status']
    droplet_id = resp['droplet']['id']
    try:
        if droplet_state == 'active': # droplet is on
            print 'Powering down droplet: %s' % (droplet_id)
            stop_droplet(do_api, droplet_id)
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
            stop_droplet(do_api, droplet_id)
        return resp
    except Exception as e:
        print '%s' % (e)


def get_datacenter_region(location):
    #[{u'slug': u'nyc1', u'id': 1, u'name': u'New York 1'}, 
    # {u'slug': u'ams1', u'id': 2, u'name': u'Amsterdam 1'}, 
    # {u'slug': u'sfo1', u'id': 3, u'name': u'San Francisco 1'}, 
    # {u'slug': u'nyc2', u'id': 4, u'name': u'New York 2'},
    # {u'slug': u'ams2', u'id': 5, u'name': u'Amsterdam 2'},
    # {u'slug': u'sgp1', u'id': 6, u'name': u'Singapore 1'},
    # {u'slug': u'lon1', u'id': 7, u'name': u'London 1'}]
    if location in [1, 3, 4]:
        return 'US'
    if location in [2, 5]:
        return 'NL'
    if location in [6]:
        return 'SG'
    if location in [7]:
        return 'GB'
    return ''

def generate_random_string(prefix=None, size=8):
    if not prefix:
        prefix=''
    return '%s%s' % (prefix, ''.join(random.choice(string.ascii_lowercase) for x in range(size)))

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


def launch_new_server(digitalocean_account, _):
    
    image = {}
    droplet = None
    try:
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        do_api = DigitalOceanAPI(digitalocean_account.client_id, digitalocean_account.api_key)
        
        image['image_id'] = digitalocean_account.base_id
        
        regions = do_api.get_all_regions()
        image['region_id'] = random.choice([region['id'] for region in regions if region['id'] in [1,2,3,4,5,6,7]])

        for r in regions:
            if image['region_id'] == r['id']:
                print 'Using region: %s' % (r['name'])
                break

        image['size_id'] = digitalocean_account.base_size_id

        # get a list of image sizes and see if the size is available (maybe some checks)
        droplet_sizes = do_api.get_all_droplet_sizes()
        if image['size_id'] not in [size['id'] for size in droplet_sizes]:
            raise Exception('Droplet size not available')
                    
        # Hostname generator
        image['name'] = generate_random_string(prefix=('do-' + str(image['region_id']) + str(image['size_id']) + '-'))
        image['ssh_key_ids'] = digitalocean_account.ssh_key_template_id

        print 'Launching %s, using image %s' % (image['name'], str(image['image_id']))
        resp = do_api.create_new_droplet(image)

        if resp['status'] != 'OK':
            raise Exception(resp['message'] + ': ' + resp['error_message'])
        
        droplet = resp['droplet']
        if not wait_on_event_completion(do_api, resp['droplet']['event_id'], interval=30):
            raise Exception('Event did not complete in time')
        
        print 'Waiting for the droplet to power on and get an IP address'
        time.sleep(30)

        # get more details about droplet
        resp = do_api.droplet_show(resp['droplet']['id'])
        droplet = resp['droplet']
        if resp['status'] != 'OK':
            raise Exception(resp['message'] + ': ' + resp['error_message'])

        if droplet['status'] != 'active':
            start_droplet(do_api, droplet['id'])

        provider_id = str(droplet['id'])
        region = get_datacenter_region(droplet['region_id'])
        datacenter_name = 'Digital Ocean ' + next((r for r in regions if r['id'] == droplet['region_id']), None)['name']

        new_host_public_key = refresh_credentials(digitalocean_account, droplet['ip_address'], 
                                                  new_root_password, new_stats_password)
        assert(new_host_public_key)

    except Exception as e:
        print type(e), str(e)
        if droplet != None:
            if 'id' in droplet:
                remove_droplet(do_api, droplet['id'])
            else:
                print type(e), "No droplet to be deleted: ", str(droplet)
        raise

    
    return (image['name'], None, provider_id, droplet['ip_address'],
            digitalocean_account.base_ssh_port, 'root', 
            new_root_password, ' '.join(new_host_public_key.split(' ')[:2]),
            digitalocean_account.base_stats_username, new_stats_password, 
            datacenter_name, region, None, None, None, None)

def remove_droplet(do_api, droplet_id):
    try:
        do_api.droplet_destroy(droplet_id, {'scrub_data': 1})
    except Exception as e:
        raise e

def remove_server(digitalocean_account, droplet_id):
    do_api = DigitalOceanAPI(digitalocean_account.client_id, digitalocean_account.api_key)
    remove_droplet(do_api, droplet_id)

if __name__ == "__main__":
    print launch_new_server(digitalocean_account)
    
