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

# TODO: script to deploy latest configuration to all servers

# for each server in db:
#   if missing cert, generate and write to db
#   subset_db = db subset with only info required by server
#   ssh to server and put sub_db
#   also copy all required client builds

import paramiko
import base64
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db


SSH_PORT = 22


def connect_to_host(ip_address, ssh_username, ssh_password, ssh_host_key):
    ssh = paramiko.SSHClient()
    key_type, key_data = ssh_host_key.split(' ')
    ssh.get_host_keys().add(ip_address, key_type, paramiko.RSAKey(data=base64.b64decode(key_data)))
    ssh.connect(ip_address, SSH_PORT, ssh_username, ssh_password)
    (_, output, _) = ssh.exec_command('ls')
    print output.read()


if __name__ == "__main__":
    hosts = psi_db.get_hosts()
    for host in hosts:
        connect_to_host(
            host.IP_Address,
            host.SSH_Username,
            host.SSH_Password,
            host.SSH_Host_Key)
