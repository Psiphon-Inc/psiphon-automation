#!/usr/bin/python
#
# Copyright (c) 2023, Psiphon Inc.
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
import sys
import nacl.secret
import nacl.utils

def encode_additional_parameters(data):

    assert(isinstance(data, bytes))

    assert(nacl.secret.SecretBox.KEY_SIZE == 32)
    key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
    assert (len(key) == 32)
    box = nacl.secret.SecretBox(key)

    assert(nacl.secret.SecretBox.NONCE_SIZE == 24)
    if sys.version_info[0] == 2:
        # Python 2
        zero_bytes = [chr(0) for _ in range(nacl.secret.SecretBox.NONCE_SIZE)]
        nonce = ''.join(zero_bytes)
    else:
        # Python 3
        nonce = bytes([0] * nacl.secret.SecretBox.NONCE_SIZE)
    assert(len(nonce) == 24)

    encrypted = box.encrypt(data, nonce)
    ctext = encrypted.ciphertext
    assert len(ctext) == len(data) + box.MACBYTES

    payload = key + encrypted.ciphertext
    encoded = base64.b64encode(payload)

    if sys.version_info[0] == 2:
        # Python 2
        encoded_str = encoded
    else:
        # Python 3
        encoded_str = encoded.decode()
    assert(isinstance(encoded_str, str))

    return encoded_str
