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
import posixpath
import sys
import stat

import psi_ssh
sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db


#==== Netflow Files Configuration  ============================================

HOST_NETFLOW_DIR = '/var/cache/nfdump'

NETFLOWS_ROOT = os.path.abspath(os.path.join('..', 'Data', 'Netflows'))

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir
# TODO: Support an alternate path in psi_data_config.py for netflows?

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    psi_db.set_db_root(psi_data_config.DATA_ROOT)
    NETFLOWS_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'Netflows')


#==============================================================================

# Our approach to efficiently maintaining a copy of the remote netflow
# directory is to copy only files that we don't already have, or that
# are larger than the version that we already have.
# We assume that files in the netflow directory are appended to only and
# that new data doesn't overwrite old data and leave the file size unchanged.

def pull_dir(ssh, remote_path, local_path):

    # Recursively copy the contents of remote_path to local_path
    try:
        remote_entries = ssh.list_dir_attributes(remote_path)
    except IOError:
        # Possible the directory doesn't exist.  Can't do anything
        # about it anyways.
        # TODO: log/report error?
        return

    for entry in remote_entries:

        # Our size-based test of whether we already have this file
        # won't be valid since this file always changes.  We don't
        # need this file anyways since we collect netflows regularly
        # and we'll get it the next time around.
        if entry.filename == 'nfcapd.current':
            continue

        remote_entry_path = posixpath.join(remote_path, entry.filename)
        local_entry_path = os.path.join(local_path, entry.filename)
        local_entry_stat = None
        if os.path.exists(local_entry_path):
            local_entry_stat = os.stat(local_entry_path)
 
        if stat.S_ISDIR(entry.st_mode):
            # Create the directory locally if it does not already exist
            if not os.path.exists(local_entry_path):
                os.mkdir(local_entry_path)

            # Recurse
            pull_dir(ssh, remote_entry_path, local_entry_path)
        else:
            # Copy the file if we don't have a local copy
            # or if the remote version is bigger than the local copy
            if not local_entry_stat or local_entry_stat.st_size < entry.st_size:
                ssh.get_file(remote_entry_path, local_entry_path)


def pull_netflows(host):

    print 'pull netflows from host %s...' % (host.Host_ID,)

    host_netflows_root = os.path.join(NETFLOWS_ROOT, host.Host_ID)
    if not os.path.exists(host_netflows_root):
        os.makedirs(host_netflows_root)

    ssh = psi_ssh.SSH(host.IP_Address, host.SSH_Port,
                      host.SSH_Username, host.SSH_Password, host.SSH_Host_Key)

    pull_dir(ssh, HOST_NETFLOW_DIR, host_netflows_root)

    ssh.close()

    output_csv_path = host_netflows_root + '.csv'
    os.system('TZ=GMT nfdump -q -R %s -o csv > %s' % (host_netflows_root, output_csv_path))
    return output_csv_path


if __name__ == "__main__":

    # test

    hosts = psi_db.get_hosts()
    for host in hosts:
        pull_netflows(host)

