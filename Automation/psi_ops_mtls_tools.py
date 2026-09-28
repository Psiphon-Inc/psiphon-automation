#!/usr/bin/python
#
# Copyright (c) 2026, Psiphon Inc.
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

These routines manage the Psiphon host mTLS PKI.

There are two operations:

- generate_ca(): create the automation CA (a private key + self-signed CA
  certificate). This is a one-time operation; the CA private key is the trust
  root and must be kept secret. Its certificate is the trust anchor distributed
  to hosts (and to whatever service terminates the mTLS connection).

- generate_host_client_credentials(): for a given host, generate an RSA key
  pair and a client certificate signed by the CA. The certificate carries the
  host identity in the Common Name and (optionally) the host addresses in the
  Subject Alternative Name extension, and is marked for TLS client
  authentication.

Everything is returned as PEM-encoded strings so it can be stored in psinet
alongside the rest of a host's provisioning data.

Algorithms / parameters:

- CA key:   RSA 4096-bit, self-signed, 10-year validity, key-cert-sign usage.
- Host key: RSA 2048-bit, 2-year validity, digital-signature +
            key-encipherment usage, client-auth extended key usage.
- Signature hash: SHA-256.

"""

import datetime
import ipaddress

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


# Defaults
CA_RSA_KEY_LENGTH_BITS = 4096
HOST_RSA_KEY_LENGTH_BITS = 2048
RSA_PUBLIC_EXPONENT = 65537

CA_VALIDITY_DAYS = 3650   # ~10 years
HOST_VALIDITY_DAYS = 3650  # ~10 years

# Small backdating of NotBefore to tolerate modest clock skew between the
# automation host and the hosts/services validating the certificate.
CLOCK_SKEW_ALLOWANCE = datetime.timedelta(minutes=5)

DEFAULT_ORGANIZATION = "Psiphon Inc."
DEFAULT_CA_COMMON_NAME = "Psiphon Automation CA"
DEFAULT_CA_ORGANIZATIONAL_UNIT = "Network Operations"
DEFAULT_HOST_ORGANIZATIONAL_UNIT = "Psiphon Automation"


def _pem_private_key(private_key, password=None):
    if password:
        encryption = serialization.BestAvailableEncryption(
            password.encode("utf-8") if isinstance(password, str) else password)
    else:
        encryption = serialization.NoEncryption()
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=encryption).decode()


def _pem_certificate(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


def _load_private_key(private_key_pem, password=None):
    if password is not None and isinstance(password, str):
        password = password.encode("utf-8")
    return serialization.load_pem_private_key(
        private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem,
        password=password)


def _load_certificate(certificate_pem):
    return x509.load_pem_x509_certificate(
        certificate_pem.encode() if isinstance(certificate_pem, str) else certificate_pem)


def _subject_alternative_names(dns_names, ip_addresses):
    general_names = []
    for name in (dns_names or []):
        general_names.append(x509.DNSName(name))
    for address in (ip_addresses or []):
        # Accept plain strings or ipaddress objects.
        if isinstance(address, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            general_names.append(x509.IPAddress(address))
        else:
            general_names.append(x509.IPAddress(ipaddress.ip_address(address)))
    return general_names


def generate_ca(common_name=DEFAULT_CA_COMMON_NAME,
                organization=DEFAULT_ORGANIZATION,
                organizational_unit=DEFAULT_CA_ORGANIZATIONAL_UNIT,
                validity_days=CA_VALIDITY_DAYS,
                key_size=CA_RSA_KEY_LENGTH_BITS,
                private_key_password=None):
    """Generate the Psiphon automation CA.

    Returns a (ca_private_key_pem, ca_certificate_pem) tuple. The private key is
    the trust root and must be stored securely (optionally encrypted by passing
    private_key_password). The certificate is the trust anchor distributed to
    hosts.
    """

    private_key = rsa.generate_private_key(
        public_exponent=RSA_PUBLIC_EXPONENT, key_size=key_size)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organizational_unit),
    ])

    now = datetime.datetime.utcnow()
    public_key = private_key.public_key()

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        # Self-signed: issuer == subject.
        .issuer_name(subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - CLOCK_SKEW_ALLOWANCE)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        # path_length=0: this CA may only sign end-entity (host) certs, not
        # further intermediate CAs.
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False),
            critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    )

    certificate = builder.sign(private_key, hashes.SHA256())

    return (_pem_private_key(private_key, private_key_password),
            _pem_certificate(certificate))


def generate_host_client_credentials(ca_private_key_pem,
                                     ca_certificate_pem,
                                     host_id,
                                     ip_addresses=None,
                                     dns_names=None,
                                     organization=DEFAULT_ORGANIZATION,
                                     organizational_unit=DEFAULT_HOST_ORGANIZATIONAL_UNIT,
                                     validity_days=HOST_VALIDITY_DAYS,
                                     key_size=HOST_RSA_KEY_LENGTH_BITS,
                                     ca_private_key_password=None):
    """Generate an mTLS client key/certificate pair for a single host.

    The certificate is signed by the automation CA (ca_private_key_pem /
    ca_certificate_pem) and is marked for TLS client authentication. host_id is
    placed in the Common Name; ip_addresses and dns_names, if supplied, are
    placed in the Subject Alternative Name extension.

    Returns a (host_private_key_pem, host_certificate_pem) tuple. The private
    key is unencrypted (the host needs to read it to establish mTLS); protect it
    at rest and in transit.
    """

    if not host_id:
        raise ValueError("host_id is required (used as the certificate Common Name)")

    ca_private_key = _load_private_key(ca_private_key_pem, ca_private_key_password)
    ca_certificate = _load_certificate(ca_certificate_pem)

    host_private_key = rsa.generate_private_key(
        public_exponent=RSA_PUBLIC_EXPONENT, key_size=key_size)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, str(host_id)),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, organizational_unit),
    ])

    now = datetime.datetime.utcnow()
    host_public_key = host_private_key.public_key()

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(host_public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - CLOCK_SKEW_ALLOWANCE)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False),
            critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(host_public_key), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_certificate.public_key()),
            critical=False)
    )

    general_names = _subject_alternative_names(dns_names, ip_addresses)
    if general_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(general_names), critical=False)

    certificate = builder.sign(ca_private_key, hashes.SHA256())

    return (_pem_private_key(host_private_key),
            _pem_certificate(certificate))


def verify_host_certificate(ca_certificate_pem, host_certificate_pem):
    """Sanity-check that host_certificate_pem was issued by the CA and is
    currently within its validity window. Returns True on success; raises on a
    bad signature and returns False if the certificate is expired / not yet
    valid. Intended as a lightweight self-check after issuance, not a full
    path/revocation validation.
    """

    ca_certificate = _load_certificate(ca_certificate_pem)
    host_certificate = _load_certificate(host_certificate_pem)

    # Raises cryptography.exceptions.InvalidSignature on mismatch.
    ca_public_key = ca_certificate.public_key()
    ca_public_key.verify(
        host_certificate.signature,
        host_certificate.tbs_certificate_bytes,
        _pkcs1v15_padding(),
        host_certificate.signature_hash_algorithm)

    now = datetime.datetime.utcnow()
    return host_certificate.not_valid_before <= now <= host_certificate.not_valid_after


def _pkcs1v15_padding():
    # Imported lazily to keep the module's top-level imports minimal.
    from cryptography.hazmat.primitives.asymmetric import padding
    return padding.PKCS1v15()


