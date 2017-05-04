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
        v247_api.create_vm(hostname, region_id, package_id)
              
        print 'Waiting for the droplet to power on and get an IP address'
        time.sleep(30)

    except Exception as e:
        print type(e), str(e)
        raise