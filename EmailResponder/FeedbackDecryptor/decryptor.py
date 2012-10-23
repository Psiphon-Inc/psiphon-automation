# Copyright (c) 2012, Psiphon Inc.
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


from base64 import b64decode
from Crypto.PublicKey import RSA
from Crypto.Cipher import AES
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Hash import HMAC, SHA256


'''
Note that the algorithms, key lengths, etc., are dictated by what the client is
sending.
'''


class DecryptorException(Exception):
    pass


def decrypt(data):
    '''
    `data` is a dict containing the object given in the diagnostic feedback
    attachment. The decrypted content string is returned. A DecryptorException
    is thrown in case of error.
    '''

    ciphertext = b64decode(data['contentCiphertext'])

    # Ready our private key, with which we'll unwrap the encryption and MAC
    # keys.
    rsaPrivKey = RSA.importKey(open('newpriv.pem').read())
    rsaCipher = PKCS1_v1_5.new(rsaPrivKey)

    # Unwrap the MAC key
    macKey = rsaCipher.decrypt(b64decode(data['wrappedMacKey']), 'fail')
    if macKey == 'fail':
        raise DecryptorException("can't unwrap MAC key")

    # Calculate and verify the MAC.
    mac = HMAC.new(macKey, digestmod=SHA256.new())
    mac.update(ciphertext)
    if mac.digest() != b64decode(data['contentMac']):
        raise DecryptorException('MAC verifiication failed')

    # Unwrap the encryption key.
    aesKey = rsaCipher.decrypt(b64decode(data['wrappedEncryptionKey']), 'fail')
    if aesKey == 'fail':
        raise DecryptorException("can't unwrap encryption key")

    # Decrypt the content.
    aesCipher = AES.new(aesKey, IV=b64decode(data['iv']), mode=AES.MODE_CBC)
    rsaCipher = PKCS1_v1_5.new(rsaPrivKey)
    cleartext = aesCipher.decrypt(ciphertext)

    # Remove the padding
    cleartext = _pkcs5_unpad(cleartext)

    return cleartext


def _pkcs5_unpad(padded):
    return padded[0:-ord(padded[-1])]
