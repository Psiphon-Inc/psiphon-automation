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

import base64
import os
import sys
import StringIO
import socket
import time

try:
    import paramiko as ssh
except ImportError as error:
    print error
    import ssh

# SSH sessions are attempted soon after linodes are started.  We don't know when the ssh service
# will be available so we can try every few seconds for up to a minute.
# This is basically a retrying SSH factory.
def make_ssh_session(ip_address, ssh_port, username, password, host_public_key, host_auth_key=None, verbose=True):
    for attempt in range(12):
        try:
            ssh = SSH(ip_address, ssh_port, username, password, host_public_key, host_auth_key)
            return ssh
        except socket.error:
            if verbose: print('Waiting for ssh...')
            time.sleep(5)
    raise Exception('Took too long to establish an ssh session')


class SSH(object):

    def __init__(self,
                 ip_address,
                 ssh_port,
                 ssh_username,
                 ssh_password,
                 ssh_host_key,
                 ssh_pkey=None):
        '''
        If used, ssh_pkey must be a string with the complete PEM file contents.
        '''

        self.ssh = ssh.SSHClient()
        self.ip_address = ip_address
        ssh_port = int(ssh_port)
        if ssh_host_key == None:
            self.ssh.set_missing_host_key_policy(ssh.AutoAddPolicy())
        else:
            split_key = ssh_host_key.split(' ')
            key_type = split_key[0]
            key_data = split_key[1]

            # Host keys are looked up by IP if the port is 22, but [IP]:port if
            # the port is anything else.
            if int(ssh_port) == 22:
                key_host_name = '%s' % (ip_address,)
            else:
                key_host_name = '[%s]:%d' % (ip_address, ssh_port)

            if key_type == 'ssh-dss':
                self.ssh.get_host_keys().add(key_host_name,
                                             key_type,
                                             ssh.DSSKey(data=base64.b64decode(key_data)))
            else: # 'ssh-rsa'
                self.ssh.get_host_keys().add(key_host_name,
                                             key_type,
                                             ssh.RSAKey(data=base64.b64decode(key_data)))

        if ssh_pkey is not None:
            ssh_pkey = ssh.RSAKey.from_private_key(StringIO.StringIO(ssh_pkey))

        self.ssh.connect(ip_address, ssh_port, ssh_username, ssh_password, pkey=ssh_pkey, timeout=60)

    def close(self):
        self.ssh.close()

    def exec_command(self, command_line):
        (_, output, _) = self.ssh.exec_command(command_line)
        out = output.read()
        out = out.decode('utf-8')
        print 'SSH %s: %s %s' % (self.ip_address, command_line[0:20]+'...', out[:100])
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
