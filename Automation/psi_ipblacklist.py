#!/usr/bin/python
#
# Copyright (c) 2018, Psiphon Inc.
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
import re
import subprocess
import sys

try:
    if sys.version_info < (3, 0):
        import urllib
        import urllib2
    else:
        import urllib.request as urllib
        import urllib.request as urllib2
except ImportError as error:
    print(error)

EXECUTABLE = 0o744
BASE_PATH = '/usr/local/share/PsiphonV'
BLACKLIST_DIR = 'malware_blacklist'
IPSET_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'ipset'))
LIST_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'lists'))

LISTS_URL = 'https://s3.amazonaws.com/p3_malware_lists/'


def build_malware_dictionary(url):
    """Build a dict containing malware lists."""
    urllib2.Request(url)
    malware_dicts = {}
    try:
        resp = urllib2.urlopen(url).read()
        malware_lists = re.findall('\w+\.list', resp)
        for item in malware_lists:
            name = item.split('.')
            malware_dicts[name[0]] = {'url': ''.join([url, item]),
                                     'rawlist': item,
                                     'ipset_file': ''.join([name[0], '.ipset']),
                                     'ip_list': '',
                                     'set_name': name[0],
                                    }
        
    except urllib2.URLError as er:
        if hasattr(er, 'reason'):
            print('Failed: ', er.reason)
        elif hasattr(er, 'code'):
            print('Error code: ', er.code)
    finally:
        return malware_dicts


def update_list(tracker):
    """Download the published list and store for processing."""
    print(tracker['url'])
    # get the file and save it to the outfile location
    try:
        subprocess.call(['mkdir', '-p', LIST_DIR])
        urllib.urlretrieve(tracker['url'], os.path.join(LIST_DIR, tracker['rawlist']))
    except:
        print('Had an issue creating updating the lists')
        sys.exit()


def parse_ip_list(raw_list_filename, read_mode):
    """Iterate through each list item to create an ipset file."""
    blackhole_list = []
    with open(os.path.join(LIST_DIR, raw_list_filename), read_mode) as f:
        for line in f:
            if re.search(r"(^#)", line):  # find comments
                next
            elif not line.strip():  # remove blank lines
                next
            else:
                blackhole_list.append(line.strip())
    return list(set(blackhole_list))


# Create the ipset script which includes creating the set name and blocklist
# which is stored in a file for execution
def create_ipset_commands(tracker):
    """Create the ipset name and add elements of the list."""
    ipset_base = ["ipset -N %s iphash" % str(tracker['set_name'])]
    tracker['ipset_rules'] = ipset_base + \
        ["ipset -q -A %s %s" % (str(tracker['set_name']), str(ip)) for ip in tracker['ip_list']]


def write_ipset_list_file(tracker):
    """Create an .ipset file for loading the list into iptables."""
    script = os.path.join(IPSET_DIR, tracker['ipset_file'])
    subprocess.call(['mkdir', '-p', IPSET_DIR])
    with open(script, 'w') as f:
        for rule in tracker['ipset_rules']:
            f.write('%s\n' % rule)
    os.chmod(script, EXECUTABLE)  # Make the file world readable.


def apply_ipset_list(tracker):
    """Run the .ipset file which creates the list to be used by iptables."""
    script = os.path.join(IPSET_DIR, tracker['ipset_file'])
    subprocess.call(script, shell=True)


def get_iptables_chain(chain):
    cmd = "iptables -L %s" % (chain)
    proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    
    return stdout


def modify_iptables_insert_tracker(tracker, chain, rules):
    """
        Check if the tracker already exists in the iptables rules.  Don't add
        if it already exists as it creates duplicate entries
    """
    add_tracker = True
    for line in rules.split('\n'):
        if tracker['set_name'] in line:       # return if we see the tracker
            add_tracker = False
            break
    
    if add_tracker:
        modify_iptables(tracker, '-I', chain)


def modify_iptables(tracker, opt, chain, flags="dst", job='-j DROP'):
    """Modify iptables to include the ipset list."""
    # iptables command:
    # iptables -D <chain> -m set --set $setname dst -j DROP
    # iptables -I <chain> -m set --set $setname dst -j DROP
    cmd = "iptables %s %s -m set --match-set %s %s %s" % (opt, chain, tracker['set_name'], flags, job)
    subprocess.call(cmd, shell=True)

if __name__ == "__main__":
    # Build a dict containing each malware list.
    mal_lists = build_malware_dictionary(LISTS_URL)
    
    iptables_chains = {'OUTPUT': None,
                       'FORWARD': None}
    
    for chain in iptables_chains:
        iptables_chains[chain] = get_iptables_chain(chain)
    
    if mal_lists:
        # lists to use:
        for item in mal_lists:
            update_list(mal_lists[item])
            mal_lists[item]['ip_list'] = parse_ip_list(mal_lists[item]['rawlist'], 'r')
            create_ipset_commands(mal_lists[item])
            write_ipset_list_file(mal_lists[item])
            apply_ipset_list(mal_lists[item])
            
            for chain in iptables_chains:
                modify_iptables_insert_tracker(mal_lists[item], chain, iptables_chains[chain])
            
    else:
        print('Malware list is empty, exiting')
        sys.exit()
        
