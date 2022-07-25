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
from cryptography.hazmat.primitives import serialization, hashes, hmac, padding
from cryptography.hazmat.primitives.asymmetric import padding as pk_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from config import config


'''
Note that the algorithms, key lengths, etc., are dictated by what the client is
sending.
'''


class DecryptorException(Exception):
    pass

_private_key_pem = None


def decrypt(data):
    '''
    `data` is a dict containing the object given in the diagnostic feedback
    attachment. The decrypted content string is returned. A DecryptorException
    is thrown in case of error.
    '''

    global _private_key_pem
    if not _private_key_pem:
        with open(config['privateKeyPemFile'], 'r') as f:
            _private_key_pem = f.read()

    ciphertext = b64decode(data['contentCiphertext'])
    iv = b64decode(data['iv'])

    # Ready our private key, with which we'll unwrap the encryption and MAC
    # keys.
    rsa_pk = serialization.load_pem_private_key(
        bytes(_private_key_pem, 'utf-8'), bytes(config['privateKeyPassword'], 'utf-8'))

    pk_padder = pk_padding.OAEP(
                    mgf=pk_padding.MGF1(algorithm=hashes.SHA1()),
                    algorithm=hashes.SHA1(),
                    label=None)

    # Unwrap the MAC key
    try:
        mac_key = rsa_pk.decrypt(
            b64decode(data['wrappedMacKey']),
            pk_padder)
    except:
        raise DecryptorException("can't unwrap MAC key")

    # Calculate and verify the MAC.
    mac = hmac.HMAC(mac_key, hashes.SHA256())
    # Include the IV in the MAC'd data, as per http://tools.ietf.org/html/draft-mcgrew-aead-aes-cbc-hmac-sha2-01
    mac.update(iv)
    mac.update(ciphertext)
    if mac.finalize() != b64decode(data['contentMac']):
        raise DecryptorException('MAC verification failed')

    # Unwrap the encryption key.
    try:
        aes_key = rsa_pk.decrypt(
            b64decode(data['wrappedEncryptionKey']),
            pk_padder)
    except:
        raise DecryptorException("can't unwrap encryption key")

    # Decrypt the content.
    aes_cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = aes_cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Strip the padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(plaintext) + unpadder.finalize()

    return plaintext.decode('utf-8')
