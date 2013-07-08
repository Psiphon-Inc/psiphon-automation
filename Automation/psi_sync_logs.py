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

import os
import sys
import time
import re
import multiprocessing
import collections
import json
import pexpect
import base64
import hashlib
import posixpath

import psi_ssh


HOST_LOG_DIR = '/var/log'
HOST_LOG_FILENAME_PATTERN = 'psiphonv.log*'
LOCAL_LOG_ROOT = os.path.join(os.path.abspath('.'), 'logs')
PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops_stats.dat')


# Use this function on platforms with no rsync; it's much less efficient
def pull_log_files(host):
    start_time = time.time()

    print 'pull log files from host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.stats_ssh_username, host.stats_ssh_password,
            host.ssh_host_key)

    dirlist = ssh.list_dir(HOST_LOG_DIR)
    for filename in dirlist:
        if re.match(HOST_LOG_FILENAME_PATTERN, filename):
            try:
                os.makedirs(os.path.join(LOCAL_LOG_ROOT, host.id))
            except OSError:
                pass
            ssh.get_file(
                posixpath.join(HOST_LOG_DIR, filename),
                os.path.join(LOCAL_LOG_ROOT, host.id, filename))
    ssh.close()

    print 'completed host %s' % (host.id,)

    return time.time()-start_time


def sync_log_files(host):

    start_time = time.time()

    print 'sync log files from host %s...' % (host.id,)

    dest = os.path.join(LOCAL_LOG_ROOT, host.id)
    if not os.path.exists(dest):
        os.makedirs(dest)

    # Get the RSA key fingerprint from the host's SSH_Host_Key
    # Based on:
    # http://stackoverflow.com/questions/6682815/deriving-an-ssh-fingerprint-from-a-public-key-in-python

    base64_key = base64.b64decode(host.ssh_host_key.split(' ')[1])
    md5_hash = hashlib.md5(base64_key).hexdigest()
    fingerprint = ':'.join(a + b for a, b in zip(md5_hash[::2], md5_hash[1::2]))
    command = 'rsync -ae "ssh -p %s -l %s" --include="%s" --exclude=* %s:%s/ %s' % (
                 host.ssh_port,
                 host.stats_ssh_username,
                 HOST_LOG_FILENAME_PATTERN,
                 host.ip_address,
                 HOST_LOG_DIR,
                 dest)
    rsync = pexpect.spawn(command)
    try:
        prompt = rsync.expect([fingerprint, 'password:'])
        if prompt == 0:
            rsync.sendline('yes')
            rsync.expect('password:')
            rsync.sendline(host.stats_ssh_password)
        else:
            rsync.sendline(host.stats_ssh_password)
        rsync.wait()
        print 'completed host %s' % (host.id,)
    except pexpect.ExceptionPexpect as e:
        print 'failed host %s: %s' % (host.id, str(e))

    sys.stdout.flush()
    return time.time()-start_time


if __name__ == "__main__":

    start_time = time.time()

    with open(PSI_OPS_DB_FILENAME) as file:
        psinet = json.loads(file.read())

    Host = collections.namedtuple(
        'Host',
        'id, provider_id, ip_address, ssh_port, ssh_host_key, stats_ssh_username, stats_ssh_password')

    hosts = [Host(host['id'],
                  host['provider_id'],
                  host['ip_address'],
                  host['ssh_port'],
                  host['ssh_host_key'],
                  host['stats_ssh_username'],
                  host['stats_ssh_password'])
             for host in psinet['_PsiphonNetwork__hosts'].itervalues()]

    # Remove the known_hosts file entry for each host.  Since servers are destroyed
    # and recreated often, it is possible to have an old entry in the known_hosts file
    # that matches a current host's ip address and port
    for host in hosts:
        os.system('ssh-keygen -R [%s]:%s' % (host.ip_address, host.ssh_port))

    pool = multiprocessing.Pool(200)
    results = pool.map(sync_log_files, hosts)

    print 'Sync log files elapsed time: %fs' % (time.time()-start_time,)

    # TODO: check for failure
    print ['%fs' % (x,) for x in results]

