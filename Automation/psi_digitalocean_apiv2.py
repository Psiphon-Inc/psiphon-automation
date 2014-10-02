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

import psi_utils

import digitalocean

def generate_random_string(prefix=None, size=8):
    if not prefix:
        prefix=''
    return '%s%s' % (prefix, ''.join(random.choice(string.ascii_lowercase) for x in range(size)))

def get_droplet_by_id(digitalocean_account, droplet_id=digitalocean_account.base_id):
    try:
        do_image = digitalocean.Image(token=digitalocean_account.oauth_apiv2, 
                                          id=droplet_id)
        base_droplet = do_image.load()
        
        return base_droplet
        
    except Exception as e:
        raise

def launch_new_server(digitalocean_account, _):
    image = {}
    
    try:
        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 'size', 'backups'])
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        
        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_apiv2)
        
        # Get the base image
        base_droplet = get_droplet_by_id(digitalocean_account, digitalocean_account.base_id)
        Droplet.image = base_droplet.id
        
        # Set the default size
        droplet_sizes = do_mgr.get_all_sizes()
        
        Droplet.size = digitalocean_account.base_size_slug
        
        droplet_regions = do_mgr.get_all_regions()
        available_regions = [base_droplet.regions, [r.slug for r in droplet_regions if r.available]]
        common_regions = reduce(set.intersection, available_regions, set(available_regions[0]))
        Droplet.region = random.choice(list(common_regions))
        
        Droplet.name = generate_random_string(prefix=('do-' + str(image['region_id']) + str(image['size_id']) + '-'))
        
        #### TODO: SSH KEY
        
    except Exception as e:
        print type(e), str(e)



'''
droplet = digitalocean.Droplet(token="secretspecialuniquesnowflake",
                               name='Example',
                               region='nyc2', # New York 2
                               image='ubuntu-14-04-x64', # Ubuntu 14.04 x64
                               size='512mb',  # 512MB
                               backups=True)
droplet.create()
'''