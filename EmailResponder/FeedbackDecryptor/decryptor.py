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
import cStringIO
import M2Crypto


'''
Note that the algorithms, key lengths, etc., are dictated by what the client is
sending.
'''


class DecryptorException(Exception):
    pass


def decrypt(private_key_pem, key_password, data):
    '''
    `data` is a dict containing the object given in the diagnostic feedback
    attachment. The decrypted content string is returned. A DecryptorException
    is thrown in case of error.
    '''

    ciphertext = b64decode(data['contentCiphertext'])

    # Ready our private key, with which we'll unwrap the encryption and MAC
    # keys.
    # We need to explicitly call `str()` on the password, because if it has
    # been extracted from a JSON config file it will be of type `unicode`
    # which will cause a key unwrap error ("bad password read").
    rsaPrivKey = M2Crypto.RSA.load_key_string(private_key_pem, lambda _: str(key_password))

    # Unwrap the MAC key
    try:
        macKey = rsaPrivKey.private_decrypt(b64decode(data['wrappedMacKey']),
                                            M2Crypto.RSA.pkcs1_oaep_padding)
    except:
        raise DecryptorException("can't unwrap MAC key")

    # Calculate and verify the MAC.
    mac = M2Crypto.EVP.HMAC(macKey, algo='sha256')
    mac.update(ciphertext)
    if mac.final() != b64decode(data['contentMac']):
        raise DecryptorException('MAC verifiication failed')

    # Unwrap the encryption key.
    try:
        aesKey = rsaPrivKey.private_decrypt(b64decode(data['wrappedEncryptionKey']),
                                            M2Crypto.RSA.pkcs1_oaep_padding)
    except:
        raise DecryptorException("can't unwrap encryption key")

    # Decrypt the content.

    # From http://svn.osafoundation.org/m2crypto/trunk/tests/test_evp.py
    def cipher_filter(cipher, inf, outf):
        while 1:
            buf = inf.read()
            if not buf:
                break
            outf.write(cipher.update(buf))
        outf.write(cipher.final())
        return outf.getvalue()

    aesCipher = M2Crypto.EVP.Cipher(alg='aes_128_cbc',
                                    key=aesKey,
                                    iv=b64decode(data['iv']),
                                    op=M2Crypto.decrypt)

    pbuf = cStringIO.StringIO()
    cbuf = cStringIO.StringIO(ciphertext)

    plaintext = cipher_filter(aesCipher, cbuf, pbuf)

    pbuf.close()
    cbuf.close()

    return plaintext
