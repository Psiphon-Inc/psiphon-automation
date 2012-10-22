from base64 import b64decode
from Crypto.PublicKey import RSA
from Crypto.Cipher import AES
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Hash import HMAC, SHA256


'''
Note that the algorithms, key lengths, etc., are dictated by what the client is
sending.
'''


ciphertext = b64decode(data['contentCiphertext'])

# Ready our private key, with which we'll unwrap the encryption and MAC keys.
rsaPrivKey = RSA.importKey(open('newpriv.pem').read())
rsaCipher = PKCS1_v1_5.new(rsaPrivKey)

# Unwrap the MAC key
macKey = rsaCipher.decrypt(b64decode(data['wrappedMacKey']), 'fail')
if macKey == 'fail':
    raise Exception("can't unwrap MAC key")

# Calculate and verify the MAC.
mac = HMAC.new(macKey, digestmod=SHA256.new())
mac.update(ciphertext)
if mac.digest() != b64decode(data['contentMac']):
    raise Exception('MAC verifiication failed')

# Unwrap the encryption key.
aesKey = rsaCipher.decrypt(b64decode(data['wrappedEncryptionKey']), 'fail')
if aesKey == 'fail':
    raise Exception("can't unwrap encryption key")

# Decrypt the content.
aesCipher = AES.new(aesKey, IV=b64decode(data['iv']), mode=AES.MODE_CBC)
cleartext = aesCipher.decrypt(ciphertext)
