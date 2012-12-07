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

"""

These routines are used to prepare the digitally signed server entries that are
distributed to clients out-of-band. The signature validates that the entries are
authentic Psiphon data. The signing public key is embedded in the client. There
is no certificate or CRL mechanism -- a new signing key is established by
issuing an update with a new key.

Signed entry format:

- JSON: {"data" : "...", "signature" : "...", "signingPublicKeyDigest" : "..."}
- The "signature" field is a Base64-encoded RSASSA-PKCS1-v1_5 signature of the
  SHA-256 digest of the "data" field.
- The public key is embedded as a Base64/DER-encoded string in each client
  build.
- The "signingPublicKeyDigest" is a Base64-encoded SHA-256 digest of the
  DER-encoded RSA public key used to create the signature. The client uses this
  field to determine if the signed server entry is compatible with its embedded
  public key.

Algorithms:

- RSA digital signature (4096-bit)
- SHA-256 hash

"""

import M2Crypto
import base64
import json


RSA_KEY_LENGTH_BITS = 4096
RSA_EXPONENT = 3


def generate_key_pair(private_key_password):
    rsa_key = M2Crypto.RSA.gen_key(RSA_KEY_LENGTH_BITS, RSA_EXPONENT)
    buffer = M2Crypto.BIO.MemoryBuffer()
    assert(1 == rsa_key.save_key_bio(
                    buffer, callback=lambda _: str(private_key_password)))
    return buffer.read_all()


def get_base64_der_public_key(key_pair, private_key_password):
    rsa_key = M2Crypto.RSA.load_key_string(
                key_pair, callback=lambda _: str(private_key_password))
    buffer = M2Crypto.BIO.MemoryBuffer()
    assert(1 == rsa_key.save_pub_key_bio(buffer))
    pem = buffer.read_all()
    # convert to Base64/DER
    return ''.join(pem.split('\n')[1:-2])


def make_signed_data(key_pair, private_key_password, data):
    sha = M2Crypto.EVP.MessageDigest('sha256')
    assert(1 == sha.update(data))
    data_digest = sha.digest()

    sha = M2Crypto.EVP.MessageDigest('sha256')
    assert(1 == sha.update(get_base64_der_public_key(key_pair, private_key_password)))
    public_key_digest = sha.digest()

    rsa_key = M2Crypto.RSA.load_key_string(
                key_pair, callback=lambda _: str(private_key_password))
    signature = rsa_key.sign(data_digest, algo='sha256')

    return json.dumps(
        {"data": data,
         "signature": base64.b64encode(signature),
         "signingPublicKeyDigest": base64.b64encode(public_key_digest)})
