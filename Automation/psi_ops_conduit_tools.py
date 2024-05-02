#!/usr/bin/python
#
# Copyright (c) 2024, Psiphon Inc.
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

"""

These routines are used to generate keys for Conduit components.

"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
import os
import unpaddedbase64


def generate_conduit_key_pair():
    private_key = Ed25519PrivateKey.generate()
    session_private_key = unpaddedbase64.encode_base64(private_key.private_bytes_raw() + private_key.public_key().public_bytes_raw())
    public_key = unpaddedbase64.encode_base64(private_key.public_key().public_bytes_raw())
    return (session_private_key, public_key)

def generate_conduit_obfuscation_root_secret():
    return unpaddedbase64.encode_base64(os.urandom(32))

