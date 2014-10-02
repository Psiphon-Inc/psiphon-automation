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

import psi_utils

import digitalocean

def get_droplet_by_id(digitalocean_account=None, droplet_id=None):
    try:
        do_image = digitalocean.Image(token=digitalocean_account.oauth_token, 
                                          id=droplet_id)
        base_droplet = do_image.load()
        
        return base_droplet
        
    except Exception as e:
        raise

def launch_new_server(digitalocean_account, _):
    image = {}
    
    try:
        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 
                                                     'size', 'backups'])
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()

        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)

        # Get the base image
        base_droplet = get_droplet_by_id(digitalocean_account, digitalocean_account.base_id)
        Droplet.image = base_droplet.id

        Droplet.name = str('do-' + 
                           ''.join(random.choice(string.ascii_lowercase) for x in range(8)))

        # Set the default size
        droplet_sizes = do_mgr.get_all_sizes()
        if not unicode(digitalocean_account.base_size_slug) in [unicode(s.slug) for s in droplet_sizes]:
            raise "Size slug not found"

        Droplet.size = digitalocean_account.base_size_slug

        droplet_regions = do_mgr.get_all_regions()
        common_regions = list(set([r.slug for r in droplet_regions if r.available])
                                 .intersection(base_droplet.regions))

        Droplet.region = random.choice(common_regions)
                
        #### TODO: SSH KEY
        sshkeys = do_mgr.get_all_sshkeys()
        # treat sshkey id as unique
        if not unicode(digitalocean_account.ssh_key_template_id) in [unicode(k.id) for k in sshkeys]:
            raise "No SSHKey found"

        droplet = digitalocean.Droplet(token=digitalocean_account.oauth_token,
                                       name=Droplet.name,
                                       region=Droplet.region,
                                       image=Droplet.image,
                                       size=Droplet.size,
                                       backups=False)

        droplet.create(ssh_keys=str(digitalocean_account.ssh_key_template_id))
    
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