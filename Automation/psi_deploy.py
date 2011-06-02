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
import tempfile
import posixpath
import sys

import psi_ssh

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Server')))
import psi_config


#==== Deploy File Locations  ==================================================

HOST_SOURCE_ROOT = '/opt/PsiphonV'
HOST_IP_DOWN_DIR = '/etc/ppp/ip-down.d'
HOST_INIT_DIR = '/etc/init.d'

BUILDS_ROOT = os.path.join('.', 'Builds')

SOURCE_FILES = [
    ('Data', ['psi_db.py']),
    ('Server', ['psi_config.py', 'psi_psk.py', 'psi_web.py'])
]

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    psi_db.set_db_root(psi_data_config.DATA_ROOT)

#==============================================================================


if __name__ == "__main__":

    # Deploy to each host

    hosts = psi_db.get_hosts()
    for host in hosts:
        ssh = psi_ssh.SSH(
                host.IP_Address, host.SSH_Username,
                host.SSH_Password, host.SSH_Host_Key)


        # Copy server source code
        
        for (dir, filenames) in SOURCE_FILES:
            ssh.exec_command('mkdir -p %s' % (posixpath.join(HOST_SOURCE_ROOT, dir),))
            for filename in filenames:        
                ssh.put_file(os.path.join(os.path.abspath('..'), dir, filename),
                             posixpath.join(HOST_SOURCE_ROOT, dir, filename))

        ssh.exec_command('chmod +x %s' % (posixpath.join(HOST_SOURCE_ROOT, 'Server', 'psi_web.py'),))

        remote_ip_down_file_path = posixpath.join(HOST_IP_DOWN_DIR, 'psi-ip-down')
        ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-ip-down'),
                     remote_ip_down_file_path)
        ssh.exec_command('chmod +x %s' % (remote_ip_down_file_path,))

        remote_init_file_path = posixpath.join(HOST_INIT_DIR, 'psiphonv')
        ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-init'),
                     remote_init_file_path)
        ssh.exec_command('chmod +x %s' % (remote_init_file_path,))
        ssh.exec_command('update-rc.d %s defaults' % ('psiphonv',))

        # Stop server, if running, before replacing data file (command may fail)

        ssh.exec_command('%s stop' % (remote_init_file_path,))

        # Copy data file

        # TODO: to minimize impact of host compromise, only send subset of servers
        # that host must know about for discovery

        file = tempfile.NamedTemporaryFile(delete=False)
        try:
            psi_db.make_file_for_host(host.Host_ID, file.name)
            file.close()
            ssh.put_file(file.name,
                         posixpath.join(HOST_SOURCE_ROOT, 'Data', psi_db.DB_FILENAME))
        finally:
            os.remove(file.name)

        # Restart  server after both source code and data file updated

        ssh.exec_command('%s restart' % (remote_init_file_path,))

        # Copy client builds

        ssh.exec_command('mkdir -p %s' % (psi_config.UPGRADE_DOWNLOAD_PATH,))

        for filename in os.listdir(BUILDS_ROOT):
            ssh.put_file(os.path.join(BUILDS_ROOT, filename),
                         posixpath.join(psi_config.UPGRADE_DOWNLOAD_PATH, filename))
