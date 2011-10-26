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


class SSH(object):

    def __init__(self, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key):
        self.ssh = paramiko.SSHClient()
        self.ip_address = ip_address
        ssh_port = int(ssh_port)
        if ssh_host_key == None:
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            key_type, key_data = ssh_host_key.split(' ')
            if int(ssh_port) == 22: 
                key_host_name = '%s' % (ip_address,)
            else:
                key_host_name = '[%s]:%d' % (ip_address, ssh_port)
            if key_type == 'ssh-dss':
                self.ssh.get_host_keys().add(key_host_name, key_type, paramiko.DSSKey(data=base64.b64decode(key_data)))
            else: # 'ssh-rsa'
                self.ssh.get_host_keys().add(key_host_name, key_type, paramiko.RSAKey(data=base64.b64decode(key_data)))
        self.ssh.connect(ip_address, ssh_port, ssh_username, ssh_password)

    def close(self):
        self.ssh.close()

    def exec_command(self, command_line):
        (_, output, _) = self.ssh.exec_command(command_line)
        out = output.read()
        print 'SSH %s: %s %s' % (self.ip_address, command_line[0:20]+'...', out)
        return out

    def list_dir(self, remote_path):
        print 'SSH %s: list dir %s' % (self.ip_address, remote_path)
        sftp = self.ssh.open_sftp()
        list = sftp.listdir(remote_path)
        sftp.close()
        return list

    def list_dir_attributes(self, remote_path):
        print 'SSH %s: list dir %s' % (self.ip_address, remote_path)
        sftp = self.ssh.open_sftp()
        list = sftp.listdir_attr(remote_path)
        sftp.close()
        return list

    def stat_file(self, remote_path):
        print 'SSH %s: stat file %s' % (self.ip_address, remote_path)
        sftp = self.ssh.open_sftp()
        attributes = sftp.lstat(remote_path)
        sftp.close()
        return attributes

    def put_file(self, local_path, remote_path):
        print 'SSH %s: put file %s %s' % (self.ip_address, local_path, remote_path)
        sftp = self.ssh.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def get_file(self, remote_path, local_path):
        print 'SSH %s: get file %s %s' % (self.ip_address, local_path, remote_path)
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
