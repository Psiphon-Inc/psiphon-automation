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

import sys
import random
import string
import time

import psi_utils

import digitalocean.DigitalOceanAPI
import digitalocean_credentials

# A default public image
_PUBLIC_IMAGE = {'distribution': 'Debian', 'slug': None, 'public': True, 'id': 12573, 'name': 'Debian 6.0 x64'}
# Our preferred image settings
# Region : Amsterdam, Image: Debian 6 x64, Size: 1GB
_DEFAULT_IMAGE_PARAMS = {'region_id': 2, 'image_id': 12573, 'size_id': 63}

_DO_ACCOUNT = digitalocean_credentials.account


def check_default_image(do_api, default_image):
    images = do_api.get_all_images()
    return (default_image in images)

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
        print 'Event %s status: %s - trying again in %ss' % (str(event_id), resp['event']['action_status'], interval)
        time.sleep(int(interval))
    print 'Event %s could not complete in 100s, exiting..' % (str(event_id))
    return False
    

def take_snapshot(droplet_id, snapshot_name={'name': None}):
    do_api = digitalocean.DigitalOceanAPI.DigitalOceanAPI(_DO_ACCOUNT['client_id'], _DO_ACCOUNT['api_key'])
    resp = check_response(do_api.droplet_show(droplet_id))
    droplet_state = resp['droplet']['status']
    if droplet_state == 'active': # droplet is on
        print 'Powering down droplet: %s' % (resp['droplet']['id'])
        droplet_off = check_response(do_api.droplet_power_off(droplet_id))
        if not wait_on_event_completion(do_api, droplet_off['event_id'], interval=30):
            print 'Could not complete task'
            raise
        resp = check_response(do_api.droplet_show(droplet_id))
    print 'Beginning snapshot'
    resp = check_response(do_api.droplet_snapshot(droplet_id, snapshot_name, interval=60))
    if not wait_on_event_completion(do_api, resp['event_id']):
        print 'Could not take snapshot'
        raise
    # We are not sure what state the droplet will be returned in. (one would assume the state it was previously in
    print 'Snapshot complete, restoring droplet to previous state'
    if droplet_state == 'active':
        if not wait_on_event_completion(do_api, check_response(do_api.droplet_power_on(droplet_id))['event_id'], interval=10):
            raise
    else:
        do_api.droplet_power_off(droplet_id)
    return resp

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

def launch_new_server(do_account, default_params=True, public_image=True):
    new_root_password = psi_utils.generate_password()
    new_stats_password = psi_utils.generate_password()
    do_api = digitalocean.DigitalOceanAPI.DigitalOceanAPI(do_account['client_id'],
                                                          do_account['api_key'])
    image = {'name': None,
             'size_id': None,
             'image_id': None,
             'region_id': None, 
             'ssh_key_ids': [],
            }
    
    if default_params:
        image = dict(image.items() + _DEFAULT_IMAGE_PARAMS.items())
    
    if public_image:
        result = check_default_image(do_api, _PUBLIC_IMAGE)
        if not result:
            print 'Could not find default public image\n'
            sys.exit()
        else:
            image['image_id'] = _PUBLIC_IMAGE['id']
    
    # Check region availability
    # TODO: weighted choice
    regions = do_api.get_all_regions()
    for r in regions:
        if not image['region_id']:
            print 'No region defined'
            #sys.exit()
        if image['region_id'] == r['id']:
            print 'Using region: %s' % (r['name'])
            break
    
    # Check the size of the image to be launched
    # get a list of image sizes and see if the size is available (maybe some checks)
    droplet_sizes = do_api.get_all_droplet_sizes()
    for r in droplet_sizes:
        if not image['size_id']:
            print 'no size defined, setting default'
            sys.exit()
        if image['size_id'] == r['id']:
            print 'Droplet Image size found'
            print 'Using size:\nID:\t%s\nName:\t%s\nCPU:\t%s\tMemory:\t%s\tDisk:\t%s\nCost Per Month:\t%s\t(%s)hourly' % (r['id'], r['name'], r['cpu'], r['memory'], r['disk'], r['cost_per_month'], r['cost_per_hour'])
            break

    # Hostname generator
    image['name'] = generate_random_string(prefix=('do-' + str(image['region_id']) + str(image['size_id'])))
    resp = do_api.create_new_droplet(image) # {u'status': u'OK', u'droplet': {u'event_id': 8547644, u'image_id': 12573, u'size_id': 63, u'id': 634684, u'name': u'do-263xruboaph'}}
    #TODO: verify droplet is powered on.  Wait a minute for IP and check
    # get more details about droplet
    droplet = do_api.droplet_show(resp['droplet']['id'])['droplet']
    provider_id = 'do-' + str(droplet['id'])
    region = get_datacenter_region(droplet['region_id'])
    datacenter_name = next((r for r in regions if r['id'] == droplet['region_id']), None)['name']
    base_ssh_port = 2222
    base_stats_username = generate_random_string(prefix='stats-')
    
    return (image['name'], None, provider_id, droplet['ip_address'],
            base_ssh_port, 'root', new_root_password, base_stats_username,
            new_stats_password, datacenter_name, region)


