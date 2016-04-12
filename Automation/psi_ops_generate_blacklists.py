#!/usr/bin/python
#
# Copyright (c) 2015, Psiphon Inc.
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


import os

import boto.s3.connection
import boto.s3.key

from cifsdk.client import Client

import psi_ops_config
import psi_ops
import psi_ops_s3

PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops.dat')
BLOCKLISTS_BUCKET = 'p3_malware_lists'

BASE_PATH = '/usr/local/share/PsiphonV'
BLACKLIST_DIR = 'malware_blacklist'
IPSET_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'ipset'))
LIST_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'lists'))


CIF_DEFAULT_MALWARE_TAGS = ['zeus', 'feodo']    # set the tags we want to use.

###############################################################################


def make_cifs_connection():
    """Connect to CIFS instance."""
    cif_client = Client(token=psi_ops_config.CIF_TOKEN,
                        remote=psi_ops_config.CIF_REMOTE,
                        no_verify_ssl=psi_ops_config.CIF_NO_VERIFY_SSL,
                        )
    return cif_client


def search_cif(decode=True, limit=5000, nolog=None, filters={}, sort=None):
    """Performs a CIF cli_search.  Uses cifsdk.client."""
    if not sort:
        sort = 'lasttime'
    
    cif_client = make_cifs_connection()
    results = cif_client.search(decode=decode, limit=limit, nolog=nolog,
                                sort=sort, filters=filters)
    
    return results


def generate_ipset_list(psinet, cif_tag, cif_otype, confidence_threshold):
    """Generate an ipset list to with updated IPs."""
    
    listed_hosts = list()    # psiphon hosts that are listed on a malware list.
    
    cif_results = search_cif(filters={'tags': cif_tag,
                                      'confidence': confidence_threshold,
                                      'otype': cif_otype},
                             limit=10000)
    
    # TODO: Check the list to see if any of our IPs are listed
    for host in psinet.get_hosts():
        for cif_host in cif_results:
            if host.ip_address is cif_host['observable']:
                print 'Found host: %s, %s' % (host.id, host.ip_address)
                listed_hosts.append(host)
                cif_results.remove(cif_host)
    
    output_file = ''.join((cif_tag, '.list'))
    with open(output_file, 'w') as f:
        for result in cif_results:
            f.write(result['observable'] + '\n')
    
    upload_ipset_list(aws_account=psinet._PsiphonNetwork__aws_account,
                      key_name=output_file, content_file=output_file)
    
    return listed_hosts


def update_malware_lists(psinet):
    """Update malware lists and send to a bucket."""
    for cif_tag in CIF_DEFAULT_MALWARE_TAGS:
        print 'Updating List: %s' % cif_tag
        listed_hosts = generate_ipset_list(psinet, cif_tag=cif_tag,
                                           cif_otype='ipv4',
                                           confidence_threshold='65')
        if len(listed_hosts) > 0:
            print 'Found %s listed hosts:' % len(listed_hosts)
            print listed_hosts


def upload_ipset_list(aws_account, key_name, content_file):
    """Upload the generated ipset list to a s3 bucket."""
    
    # Make a s3 connection 
    s3_conn = boto.connect_s3(
            aws_account.access_id,
            aws_account.secret_key)
    
    bucket = s3_conn.get_bucket(BLOCKLISTS_BUCKET)
    psi_ops_s3.put_file_to_key(bucket, key_name, None, content_file, is_public=True)


def main():
    """Start here."""
    psinet = psi_ops.PsiphonNetwork.load_from_file(PSI_OPS_DB_FILENAME)

    update_malware_lists(psinet)


if __name__ == "__main__":
    main()
    
