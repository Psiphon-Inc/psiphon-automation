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
import binascii
import portalocker
from subprocess import call
import psi_config


def set_psk(server_ip_address):
    psk = binascii.hexlify(os.urandom(psi_config.IPSEC_PSK_LENGTH))
    try:
        file = open(psi_config.IPSEC_SECRETS_FILENAME, 'r+')
        portalocker.lock(file, portalocker.LOCK_EX)
        lines = file.readlines()
        newline = '%s : PSK "%s"\n' % (server_ip_address, psk)
        newlines = []
        found = False
        for line in lines:
            if line.find(server_ip_address) == 0:
                newlines.append(newline)
                found = True
            else:
                newlines.append(line)
        if not found:
            newlines.append(newline)
        file.seek(0)
        file.truncate()
        file.writelines(newlines)
        file.flush()
        call (['sudo', 'ipsec', 'auto', '--rereadsecrets'])
    finally:
        file.close()
    return psk

