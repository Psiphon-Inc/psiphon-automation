#!/usr/bin/python
#
# Copyright (c) 2012, Psiphon Inc.
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
import urllib
import urllib2

EXECUTABLE = 00744
BASE_PATH = '/usr/local/share/PsiphonV'
BLACKLIST_DIR = 'malware_blacklist'
IPSET_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'ipset'))
LIST_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'lists'))

SPYEYETRACKER = {'url': "https://s3.amazonaws.com/psiphon3_stats/spyeyetracker.list",
                 'rawlist': 'spyeyetracker.list',
                 'ipset_file': 'spyeyetracker.ipset',
                 'set_name': 'SPYEYETRACKER',
                 'ip_list': '',
                }

MDL = {'url': "https://s3.amazonaws.com/psiphon3_stats/mdlip.list",
       'rawlist': 'mdlip.list',
       'ipset_file': 'mdlip.ipset',
       'set_name': 'MDL',
       'ip_list': '',
      }

# Used to update each ip block list
def update_list(tracker):
    print tracker['url']
    # get the file and save it to the outfile location
    try:
        subprocess.call(['mkdir', '-p', LIST_DIR])
        urllib.urlretrieve(tracker['url'], os.path.join(LIST_DIR, tracker['rawlist']))
    except:
        print 'Could not find location'
        raise

def parse_ip_list(raw_list_filename, read_mode):
    blackhole_list = []
    with open(os.path.join(LIST_DIR, raw_list_filename), read_mode) as f:
        for line in f:
            if re.search(r"(^#)", line): #find comments
                next
            elif not line.strip(): #remove blank lines
                next
            else:
                blackhole_list.append(line.strip())
    return blackhole_list

# Create the ipset script which includes creating the set name and blocklist
# which is stored in a file for execution
def create_ipset_commands(tracker):
    ipset_base = ["ipset -N %s iphash" % str(tracker['set_name']), 
                  "ipset -F %s" % str(tracker['set_name'])]
    tracker['ipset_rules'] = ipset_base + \
        ["ipset -A %s %s" % (str(tracker['set_name']), str(ip)) for ip in tracker['ip_list']]

def write_ipset_script(tracker):
    script = os.path.join(IPSET_DIR, tracker['ipset_file'])
    subprocess.call(['mkdir', '-p', IPSET_DIR])
    with open(script, 'w') as f:
        for rule in tracker['ipset_rules']:
            f.write('%s\n' % rule)
    os.chmod(script, EXECUTABLE)

def run_ipset_script(tracker):
    script = os.path.join(IPSET_DIR, tracker['ipset_file'])
    subprocess.call(script, shell=True)

def modify_iptables(tracker, opt, chain):
    #iptables command:
    #iptables -D <chain> -m set --set $setname src -j DROP
    #iptables -I <chain> -m set --set $setname src -j DROP
    cmd = "iptables %s %s -m set --set %s src -j DROP" % (opt, chain, tracker['set_name'])
    subprocess.call(cmd, shell=True)

if __name__ == "__main__":
    
    #lists to use:
    mal_lists = [SPYEYETRACKER, MDL]
    for item in mal_lists:
        update_list(item)
        item['ip_list'] = parse_ip_list(item['rawlist'], 'r')
        create_ipset_commands(item)
        write_ipset_script(item)
        run_ipset_script(item)
        modify_iptables(item, '-D', 'OUTPUT')
        modify_iptables(item, '-I', 'OUTPUT')
        modify_iptables(item, '-D', 'FORWARD')
        modify_iptables(item, '-I', 'FORWARD')
        
