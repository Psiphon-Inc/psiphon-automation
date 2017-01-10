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
