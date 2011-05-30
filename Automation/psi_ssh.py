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

import paramiko
import base64
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db


SSH_PORT = 22


class SSH(object):

    def __init__(self, ip_address, ssh_username, ssh_password, ssh_host_key):
        self.ssh = paramiko.SSHClient()
        self.ip_address = ip_address
        key_type, key_data = ssh_host_key.split(' ')
        self.ssh.get_host_keys().add(self.ip_address, key_type, paramiko.RSAKey(data=base64.b64decode(key_data)))
        self.ssh.connect(ip_address, SSH_PORT, ssh_username, ssh_password)

    def exec_command(self, command_line):
        (_, output, _) = self.ssh.exec_command(command_line)
        out = output.read()
        print 'SSH %s: %s %s' % (self.ip_address, command_line, out)
        return out

    def put_file(self, local_path, remote_path):
        print 'SSH %s: put %s %s' % (self.ip_address, local_path, remote_path)
        sftp = self.ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def get_file(self, remote_path, local_path):
        print 'SSH %s: get %s %s' % (self.ip_address, local_path, remote_path)
        sftp = self.ssh.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()


if __name__ == "__main__":

    # test

    hosts = psi_db.get_hosts()
    for host in hosts:
        ssh = SSH(
                host.IP_Address, host.SSH_Username,
                host.SSH_Password, host.SSH_Host_Key)
        print ssh.exec_command('ls /')
