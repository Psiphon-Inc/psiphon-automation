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
import M2Crypto

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
        _private_key_pem = open(config['privateKeyPemFile'], 'r').read()

    ciphertext = b64decode(data['contentCiphertext'])
    iv = b64decode(data['iv'])

    # Ready our private key, with which we'll unwrap the encryption and MAC
    # keys.
    # We need to explicitly call `str()` on the password, because if it has
    # been extracted from a JSON config file it will be of type `unicode`
    # which will cause a key unwrap error ("bad password read").
    rsaPrivKey = M2Crypto.RSA.load_key_string(_private_key_pem,
                                              lambda _: str(config['privateKeyPassword']))

    # Unwrap the MAC key
    try:
        macKey = rsaPrivKey.private_decrypt(b64decode(data['wrappedMacKey']),
                                            M2Crypto.RSA.pkcs1_oaep_padding)
    except:
        raise DecryptorException("can't unwrap MAC key")

    # Calculate and verify the MAC.
    mac = M2Crypto.EVP.HMAC(macKey, algo='sha256')
    # Include the IV in the MAC'd data, as per http://tools.ietf.org/html/draft-mcgrew-aead-aes-cbc-hmac-sha2-01
    mac.update(iv)
    mac.update(ciphertext)
    if mac.final() != b64decode(data['contentMac']):
        raise DecryptorException('MAC verification failed')

    # Unwrap the encryption key.
    try:
        aesKey = rsaPrivKey.private_decrypt(b64decode(data['wrappedEncryptionKey']),
                                            M2Crypto.RSA.pkcs1_oaep_padding)
    except:
        raise DecryptorException("can't unwrap encryption key")

    # Decrypt the content.

    aesCipher = M2Crypto.EVP.Cipher(alg='aes_128_cbc',
                                    key=aesKey,
                                    iv=iv,
                                    op=0)

    plaintext = aesCipher.update(ciphertext)
    plaintext += aesCipher.final()

    return plaintext
