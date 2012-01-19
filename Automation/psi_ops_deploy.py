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

import re
import tempfile
import os
import posixpath
import sys
import psi_ssh
import psi_routes

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Server')))
import psi_config


#==== Deploy File Locations  ==================================================

BUILDS_ROOT = os.path.join('.', 'Builds')

SOURCE_FILES = [
    ('Automation', ['psi_ops.py', 'psi_ops_cms.py', 'psi_utils.py']),
    ('Server', ['psi_config.py', 'psi_psk.py', 'psi_web.py'])
]

#==============================================================================


def deploy_implementation(host):

    print 'deploy implementation to host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    # Copy server source code

    for (dir, filenames) in SOURCE_FILES:
        ssh.exec_command('mkdir -p %s' % (
                posixpath.join(psi_config.HOST_SOURCE_ROOT, dir),))
        for filename in filenames:
            ssh.put_file(os.path.join(os.path.abspath('..'), dir, filename),
                         posixpath.join(psi_config.HOST_SOURCE_ROOT, dir, filename))

    ssh.exec_command('chmod +x %s' % (
            posixpath.join(psi_config.HOST_SOURCE_ROOT, 'Server', 'psi_web.py'),))

    remote_ip_down_file_path = posixpath.join(psi_config.HOST_IP_DOWN_DIR, 'psi-ip-down')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-ip-down'),
                 remote_ip_down_file_path)
    ssh.exec_command('chmod +x %s' % (remote_ip_down_file_path,))

    remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'psiphonv')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-init'),
                 remote_init_file_path)
    ssh.exec_command('chmod +x %s' % (remote_init_file_path,))
    ssh.exec_command('update-rc.d %s defaults' % ('psiphonv',))

    # Restart server after source code updated

    ssh.exec_command('%s restart' % (remote_init_file_path,))

    # Copy DNS capture init script and restart it

    remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'psi-dns-capture')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-dns-capture'),
                 remote_init_file_path)
    ssh.exec_command('chmod +x %s' % (remote_init_file_path,))
    ssh.exec_command('update-rc.d %s defaults' % ('psi-dns-capture',))

    ssh.exec_command('%s restart' % (remote_init_file_path,))

    # Copy the rate-limiting scripts

    remote_rate_limit_start_file_path = posixpath.join(psi_config.HOST_IP_UP_DIR, 'rate-limit')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'rate-limit-start'),
                 remote_rate_limit_start_file_path)
    ssh.exec_command('chmod +x %s' % (remote_rate_limit_start_file_path,))
    remote_rate_limit_end_file_path = posixpath.join(psi_config.HOST_IP_DOWN_DIR, 'rate-limit')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'rate-limit-end'),
                 remote_rate_limit_end_file_path)
    ssh.exec_command('chmod +x %s' % (remote_rate_limit_end_file_path,))

    ssh.close()
    

def deploy_data(host, host_data):

    print 'deploy data to host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    # Stop server, if running, before replacing data file (command may fail)

    remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'psiphonv')

    ssh.exec_command('%s stop' % (remote_init_file_path,))

    # Copy data file
    # We upload a compartmentalized version of the master file
    # containing only the propagation channel IDs and confidential server
    # information required by each host.

    file = tempfile.NamedTemporaryFile(delete=False)
    try:
        file.write(host_data)
        file.close()
        ssh.exec_command('mkdir -p %s' % (
                posixpath.split(psi_config.DATA_FILE_NAME)[0],))
        ssh.put_file(file.name, psi_config.DATA_FILE_NAME)
    finally:
        try:
            os.remove(file.name)
        except:
            pass

    # Restart server after data file updated

    ssh.exec_command('%s restart' % (remote_init_file_path,))

    ssh.close()
    

def deploy_build(host, build_filename):

    print 'deploy %s build to host %s...' % (build_filename, host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    ssh.exec_command('mkdir -p %s' % (psi_config.UPGRADE_DOWNLOAD_PATH,))

    ssh.put_file(
        build_filename,
        posixpath.join(psi_config.UPGRADE_DOWNLOAD_PATH,
                       os.path.split(build_filename)[1]))

    ssh.close()
    

def deploy_routes(host):

    print 'deploy routes to host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    ssh.exec_command('mkdir -p %s' % (psi_config.ROUTES_PATH,))

    target_filename = posixpath.join(
                            psi_config.ROUTES_PATH,
                            os.path.split(psi_routes.GEO_ROUTES_ARCHIVE_PATH)[1])

    ssh.put_file(
        psi_routes.GEO_ROUTES_ARCHIVE_PATH,
        target_filename)

    ssh.exec_command('tar xfz %s' % (target_filename,))

    ssh.close()
