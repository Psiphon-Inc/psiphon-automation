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
import random
import sys
import textwrap
import tempfile
import binascii
import psi_ssh
import posixpath
import time
import M2Crypto
import datetime
import base64
import random

import psi_ops_deploy

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Server')))
try:
    # For Legacy servers
    import psi_config
except ImportError as error:
    print "Missing Legacy Server support: " + str(error)


#==== Configuration ============================================================

WEB_SERVER_SECRET_BYTE_LENGTH = 32
SERVER_ID_WORD_LENGTH = 3

SSL_CERTIFICATE_RSA_EXPONENT = 3
SSL_CERTIFICATE_RSA_KEY_LENGTH_BITS = 2048
SSL_CERTIFICATE_DIGEST_TYPE = 'sha1'
SSL_CERTIFICATE_VALIDITY_SECONDS = (60*60*24*365*10) # 10 years

SSH_RANDOM_USERNAME_SUFFIX_BYTE_LENGTH = 8
SSH_PASSWORD_BYTE_LENGTH = 32
SSH_OBFUSCATED_KEY_BYTE_LENGTH = 32


TCS_SSH_RSA_KEY_LENGTH_BITS = 2048
TCS_SSH_RSA_KEY_EXPONENT = 65537

#==== Helpers ==================================================================

# We use an echo command over ssh to generate this file on the remote server
# to avoid leaving IP Addresses on disk
def make_xl2tpd_config_file_command(server_index, ip_address):
    file_contents = textwrap.dedent('''
        [global]
        listen-addr = %s

        [lns default]
        ip range = 10.%d.0.2-10.%d.255.254
        local ip = 10.%d.0.1
        require chap = yes
        refuse pap = yes
        require authentication = yes
        name = PsiphonV
        pppoptfile = /etc/ppp/options.xl2tpd
        length bit = yes
        ''' % (ip_address, server_index, server_index, server_index))

    return 'echo "%s" > /etc/xl2tpd/xl2tpd%d.conf' % (
        file_contents, server_index)


def make_xl2tpd_options_file_command():
    file_contents = textwrap.dedent('''
        ipcp-accept-local
        ipcp-accept-remote
        ms-dns 8.8.8.8
        ms-dns 8.8.4.4
        noccp
        auth
        crtscts
        idle 1800
        mtu 1410
        mru 1410
        nodefaultroute
        debug
        lock
        proxyarp
        connect-delay 5000
        ''')

    return 'echo "%s" > /etc/ppp/options.xl2tpd' % (
        file_contents,)


def make_xl2tpd_chap_secrets_file_command():
    file_contents = '*   *   password    *'
    return 'echo "%s" > /etc/ppp/chap-secrets' % (
        file_contents,)


# This file is written to disk then copied to the remote server.  We had
# problems echoing it out to a file in an ssh command, probably because of all
# the special characters.  It's OK to write this to disk locally, because there
# isn't any secret info (like IP Addresses) here.
def make_xl2tpd_initd_file_contents(server_count):
    # TODO: use textwrap.dedent and try initial_indent to line up the
    # repeated segments
    file_contents = '''
#! /bin/sh

### BEGIN INIT INFO
# Provides:          xl2tpd l2tpd
# Required-Start:    $network $syslog $remote_fs
# Required-Stop:     $network $syslog $remote_fs
# Should-Start:      ipsec
# Should-Stop:       ipsec
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: layer 2 tunelling protocol daemon
# Description:       xl2tpd is usually used in conjunction with an ipsec
#                    daemon (such as openswan).
### END INIT INFO

PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
DAEMON=/usr/sbin/xl2tpd
NAME=xl2tpd
DESC=xl2tpd

test -x $DAEMON || exit 0

# Include xl2tpd defaults if available
if [ -f /etc/default/xl2tpd ] ; then
        . /etc/default/xl2tpd
fi

PIDFILE=/var/run/$NAME.pid

set -e

case "$1" in
    start)
        echo -n "Starting $DESC: "
''' + ''.join(['''
        test -d /var/run/xl2tpd%d || mkdir -p /var/run/xl2tpd%d
        start-stop-daemon --start --quiet --pidfile $PIDFILE.%d --exec $DAEMON -- -c /etc/xl2tpd/xl2tpd%d.conf -p $PIDFILE.%d -C /var/run/xl2tpd%d/l2tp-control $DAEMON_OPTS
        echo "$NAME.%d."
''' % (i,i,i,i,i,i,i) for i in range(server_count)]) + '''
        ;;
    stop)
        echo -n "Stopping $DESC: "
''' + ''.join(['''
        start-stop-daemon --oknodo --stop --quiet --pidfile $PIDFILE.%d --exec $DAEMON
        echo "$NAME.%d."
''' % (i,i) for i in range(server_count)]) + '''
        ;;
    restart)
        $0 stop
        sleep 1
        $0 start
        ;;
    *)
        N=/etc/init.d/$NAME
        echo "Usage: $N {start|stop|restart}" >&2
        exit 1
        ;;
esac

exit 0
'''

    return file_contents


def make_ipsec_config_file_base_contents(server_count):
    file_contents = '''
# /etc/ipsec.conf - Openswan IPsec configuration file

version 2.0     # conforms to second version of ipsec.conf specification

# basic configuration
config setup
    interfaces="''' + ' '.join(['ipsec%d=eth%s' % (i, i if i == 0 else '0:%d' % (i,)) for i in range(server_count)]) + '''"
    # NAT-TRAVERSAL support, see README.NAT-Traversal
    nat_traversal=yes
    # exclude networks used on server side by adding %v4:!a.b.c.0/24
    virtual_private=%v4:10.0.0.0/8,%v4:192.168.0.0/16,%v4:172.16.0.0/12
    # OE is now off by default. Uncomment and change to on, to enable.
    oe=off
    # Which IPsec stack to use. auto will try netkey, then klips then mast
    protostack=klips
    plutostderrlog=/dev/null
'''

    return file_contents


def make_ipsec_config_file_connection_command(server_index, ip_address):
    file_contents = textwrap.dedent('''
        conn L2TP-PSK-%d-NAT
            rightsubnet=vhost:%%priv
            also=L2TP-PSK-%d-noNAT

        conn L2TP-PSK-%d-noNAT
            left=%s
            leftprotoport=17/1701
            right=%%any
            rightprotoport=17/0
            authby=secret
            pfs=no
            auto=add
            keyingtries=3
            rekey=no
            ikelifetime=8h
            keylife=1h
            type=transport
        ''' % (server_index, server_index, server_index, ip_address))
    return 'echo "%s" >> /etc/ipsec.conf' % (file_contents,)


def make_ipsec_secrets_file_command():
    return 'echo "" > /etc/ipsec.secrets && chmod 666 /etc/ipsec.secrets'


def make_sshd_config_file_command(ip_address, ssh_user):
    file_contents = textwrap.dedent('''
        AllowUsers %s
        HostKey /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s
        LoginGraceTime 20
        PrintLastLog no
        PrintMotd no
        UseDNS no
        UsePAM yes
        LogLevel ERROR
        ''' % (ssh_user, ip_address))

    return 'echo "%s" > /etc/ssh/sshd_config.psiphon_ssh_%s' % (
        file_contents, ip_address)


def make_obfuscated_sshd_config_file_command(ip_address, ssh_user, ssh_obfuscated_port, ssh_obfuscated_key):
    file_contents = textwrap.dedent('''
        AllowUsers %s
        HostKey /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s
        LoginGraceTime 20
        PrintLastLog no
        PrintMotd no
        UseDNS no
        UsePAM yes
        LogLevel ERROR
        ObfuscatedPort %s
        ObfuscateKeyword %s
        ''' % (ssh_user, ip_address, ssh_obfuscated_port, ssh_obfuscated_key))

    return 'echo "%s" > /etc/ssh/sshd_config.obfuscated.psiphon_ssh_%s' % (
        file_contents, ip_address)


def make_xinetd_config_file_command(servers):

    defaults_section = textwrap.dedent('''
        defaults
        {
            cps             = 1000 30
        }
        ''')

    ssh_service_section_template = textwrap.dedent('''
        service psiphon_ssh.%s
        {
            type            = UNLISTED
            bind            = %s
            port            = %s
            socket_type     = stream
            protocol        = tcp
            wait            = no
            user            = root
            group           = nogroup
            server          = /usr/sbin/sshd
            server_args     = -i -4 -f /etc/ssh/sshd_config.psiphon_ssh_%s
        }
        ''')

    obfuscated_ssh_service_section_template = textwrap.dedent('''
        service psiphon_ssh.obfuscated.%s
        {
            type            = UNLISTED
            bind            = %s
            port            = %s
            socket_type     = stream
            protocol        = tcp
            wait            = no
            user            = root
            group           = nogroup
            server          = /usr/local/sbin/sshd
            server_args     = -i -4 -f /etc/ssh/sshd_config.obfuscated.psiphon_ssh_%s
        }
        ''')

    service_sections = []
    for server in servers:
        if server.ssh_port is not None:
            service_sections.append(ssh_service_section_template %
                                (server.internal_ip_address, server.internal_ip_address, server.ssh_port, server.internal_ip_address))
        if server.ssh_obfuscated_port is not None:
            service_sections.append(obfuscated_ssh_service_section_template %
                                (server.internal_ip_address, server.internal_ip_address, server.ssh_obfuscated_port, server.internal_ip_address))

    file_contents = defaults_section + '\n'.join(service_sections)
    return 'echo "%s" > /etc/xinetd.conf' % (file_contents,)


def generate_web_server_secret():
    return binascii.hexlify(os.urandom(WEB_SERVER_SECRET_BYTE_LENGTH))


def generate_unique_server_id(existing_server_ids):
    WORDS = '''
multion            moding             addrer             hactrogram
emaging            keyboot            forsonic           trogram
reless             syster             hareware           accense
lickbash           randowser          reacy              trate
rany               typers             zinink             propree
acting             malet              equicess           datink
docasion           horer              tabyte             filer
mems               numerl             kers               actocumerl
inse               sectime            quican             documedia
electrows          mon-col            explicktion        rookie
pirtus             noteboad           date               pritop
sprine             uplore             typer              systers
filet              printu             disual             shat
prows              lican              adwall             nonink
nonal              serce              modia              vireacy
apams              datos              prive              keyboad
relent             ubunix             allocurce          files
redia              enity              reasing            instem
dowser             sharing            computem           sectrogram
kernet             hored              sectrojan          engual
haress             deboad             megramputem        mource
intu               explork            supg               docurch
opers              megram             inter              redinic
sourite            prothon            licent             sernet
morer              applory            pyte               mareshat
'''.split()
    while True:
        server_id = ' '.join([random.choice(WORDS) for _ in range(SERVER_ID_WORD_LENGTH)])
        if not server_id in existing_server_ids:
            return server_id


def generate_self_signed_certificate():

    # Based on http://svn.osafoundation.org/m2crypto/trunk/tests/test_x509.py

    private_key = M2Crypto.EVP.PKey()
    request = M2Crypto.X509.Request()
    rsa = M2Crypto.RSA.gen_key(
        SSL_CERTIFICATE_RSA_KEY_LENGTH_BITS, SSL_CERTIFICATE_RSA_EXPONENT, lambda _: None)
    private_key.assign_rsa(rsa)
    request.set_pubkey(private_key)
    request.sign(private_key, SSL_CERTIFICATE_DIGEST_TYPE)
    assert request.verify(private_key)
    public_key = request.get_pubkey()
    assert request.verify(public_key)

    #
    # TODO: generate a random, yet plausible DN
    #
    # subject = request.get_subject()
    # for (key, value) in subject_pairs.items():
    #    setattr(subject, key, value)
    #
    certificate = M2Crypto.X509.X509()

    certificate.set_serial_number(0)
    certificate.set_version(2)

    now = long(time.time())
    notBefore = M2Crypto.ASN1.ASN1_UTCTIME()
    notBefore.set_time(now)
    notAfter = M2Crypto.ASN1.ASN1_UTCTIME()
    notAfter.set_time(now + SSL_CERTIFICATE_VALIDITY_SECONDS)
    certificate.set_not_before(notBefore)
    certificate.set_not_after(notAfter)

    certificate.set_pubkey(public_key)
    certificate.sign(private_key, SSL_CERTIFICATE_DIGEST_TYPE)
    assert certificate.verify()
    assert certificate.verify(private_key)
    assert certificate.verify(public_key)

    return certificate.as_pem(), rsa.as_pem(cipher=None) # Use rsa for PKCS#1


def install_host(host, servers, existing_server_ids, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, plugins):

    if host.is_TCS:
        install_TCS_host(host, servers, existing_server_ids, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, plugins)
    else:
        install_legacy_host(host, servers, existing_server_ids, plugins)


def install_legacy_host(host, servers, existing_server_ids, plugins):

    install_firewall_rules(host, servers, None, None, plugins)

    install_psi_limit_load(host, servers)

    install_user_count_and_log(host, servers)

    # NOTE:
    # For partially configured hosts we need to completely reconfigure
    # all files because we use a counter in the xl2tpd config files that is not
    # directly tied to the IP Address in the database.

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    #
    # Generate and upload ipsec config files
    #

    file = tempfile.NamedTemporaryFile(delete=False)
    file.write(make_ipsec_config_file_base_contents(len(servers)))
    file.close()
    ssh.put_file(file.name, '/etc/ipsec.conf')
    os.remove(file.name)

    for index, server in enumerate(servers):
        ssh.exec_command(
            make_ipsec_config_file_connection_command(index, server.internal_ip_address))

    ssh.exec_command(make_ipsec_secrets_file_command())

    #
    # Generate and upload xl2tpd config files and init script
    #

    # Stop the default instance first
    ssh.exec_command('/etc/init.d/xl2tpd stop')

    for index, server in enumerate(servers):
        ssh.exec_command(
            make_xl2tpd_config_file_command(index, server.internal_ip_address))

    ssh.exec_command(make_xl2tpd_options_file_command())

    ssh.exec_command(make_xl2tpd_chap_secrets_file_command())

    file = tempfile.NamedTemporaryFile(delete=False)
    file.write(make_xl2tpd_initd_file_contents(len(servers)))
    file.close()
    ssh.put_file(file.name, '/etc/init.d/xl2tpd')
    os.remove(file.name)

    #
    # Restart the IPSec and xl2tpd services
    #

    ssh.exec_command('/etc/init.d/ipsec restart')
    ssh.exec_command('/etc/init.d/xl2tpd restart')

    #
    # Upload and install patched Open SSH
    #

    ssh.exec_command('rm -rf %(key)s; mkdir -p %(key)s' % {"key": psi_config.HOST_OSSH_SRC_DIR})
    remote_ossh_file_path = posixpath.join(psi_config.HOST_OSSH_SRC_DIR, 'ossh.tar.gz')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', '3rdParty', 'ossh.tar.gz'),
                 remote_ossh_file_path)
    ssh.exec_command('cd %s; tar xfz ossh.tar.gz; ./configure --with-pam > /dev/null; make > /dev/null && make install > /dev/null'
            %(psi_config.HOST_OSSH_SRC_DIR,))

    #
    # Upload and install badvpn-udpgw
    #

    ssh.exec_command('apt-get install -y cmake')
    ssh.exec_command('rm -rf %(key)s; mkdir -p %(key)s' % {"key": psi_config.HOST_BADVPN_SRC_DIR})
    remote_badvpn_file_path = posixpath.join(psi_config.HOST_BADVPN_SRC_DIR, 'badvpn.tar.gz')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', '3rdParty', 'badvpn.tar.gz'),
                 remote_badvpn_file_path)
    ssh.exec_command('cd %s; tar xfz badvpn.tar.gz; mkdir build; cd build; cmake ../badvpn -DCMAKE_INSTALL_PREFIX=/usr/local -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1 > /dev/null; make > /dev/null && make install > /dev/null'
            %(psi_config.HOST_BADVPN_SRC_DIR,))

    remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'badvpn-udpgw')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'udpgw-init'),
                 remote_init_file_path)
    ssh.exec_command('chmod +x %s' % (remote_init_file_path,))
    ssh.exec_command('update-rc.d %s defaults' % ('badvpn-udpgw',))
    ssh.exec_command('%s restart' % (remote_init_file_path,))

    #
    # Generate and upload sshd_config files and xinetd.conf
    #

    for server in servers:

        # Generate SSH credentials and SSH host key here because we need to create them
        # on the server and use them in the sshd_config files.
        # They will be updated in the database below.
        if (server.ssh_username is None
            or server.ssh_password is None):
            server.ssh_username = 'psiphon_ssh_%s' % (
                binascii.hexlify(os.urandom(SSH_RANDOM_USERNAME_SUFFIX_BYTE_LENGTH)),)
            server.ssh_password = binascii.hexlify(os.urandom(SSH_PASSWORD_BYTE_LENGTH))
        if server.ssh_host_key is None:
            ssh.exec_command('rm /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s' % (server.internal_ip_address,))
            ssh.exec_command('ssh-keygen -t rsa -N \"\" -f /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s' % (server.internal_ip_address,))
            try:
                # TODO: use temp dir?
                ssh.get_file('/etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s.pub' % (server.internal_ip_address,), 'ssh_host_key')
                with open('ssh_host_key') as file:
                    key = file.read()
            finally:
                os.remove('ssh_host_key')
            # expected format: ssh-rsa <base64> username@host
            # output format: ssh-rsa <base64>
            server.ssh_host_key = ' '.join(key.split(' ')[:2])

        # NOTE unconditionally attempt to create the user.  It's OK if it fails because
        #      the user already exists
        ssh.exec_command('useradd -d /dev/null -s /bin/false %s && echo \"%s:%s\"|chpasswd' % (
                            server.ssh_username, server.ssh_username, server.ssh_password))
        ssh.exec_command(make_sshd_config_file_command(server.internal_ip_address, server.ssh_username))
        if server.ssh_obfuscated_port is not None:
            if server.ssh_obfuscated_key is None:
                server.ssh_obfuscated_key = binascii.hexlify(os.urandom(SSH_OBFUSCATED_KEY_BYTE_LENGTH))
            ssh.exec_command(make_obfuscated_sshd_config_file_command(server.internal_ip_address, server.ssh_username,
                                                    server.ssh_obfuscated_port, server.ssh_obfuscated_key))
        # NOTE we do not write the ssh host key back to the server because it is generated
        #      on the server in the first place.

    ssh.exec_command(make_xinetd_config_file_command(servers))

    #
    # Restart the xinetd service
    #

    ssh.exec_command('/etc/init.d/xinetd restart')

    #
    # Restart some services regularly
    #

    cron_file = '/etc/cron.d/psi-restart-services'
    ssh.exec_command('echo "SHELL=/bin/sh" > %s;' % (cron_file,) +
                     'echo "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin" >> %s;' % (cron_file,) +
                     'echo "1 * * * * root killall -9 %s && %s restart" >> %s;' % ('xinetd', '/etc/init.d/xinetd', cron_file) +
                     'echo "2 * * * * root killall -9 %s && %s restart" >> %s' % ('badvpn-udpgw', '/etc/init.d/badvpn-udpgw', cron_file))

    #
    # Add required packages and Python modules
    #

    ssh.exec_command('apt-get install -y python-pip libffi-dev')
    ssh.exec_command('pip install pyOpenSSL')
    ssh.exec_command('pip install hiredis')
    ssh.exec_command('pip install redis')
    ssh.exec_command('pip install iso8601')
    ssh.exec_command('pip install --upgrade cffi')
    ssh.exec_command('apt-get install -y redis-server mercurial git')

    install_geoip_database(ssh, False)

    for plugin in plugins:
        if hasattr(plugin, 'install_host'):
            plugin.install_host(ssh)

    ssh.close()

    #
    # Generate unique server alias and web server credentials
    #

    for server in servers:

        if server.id is None:
            server.id = generate_unique_server_id(existing_server_ids)

        if server.web_server_secret is None:
            server.web_server_secret = generate_web_server_secret()

        # Generated output is PEM, e.g.,
        #
        # '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAvAmIPX5kzPz...
        #  EZ3bCbVPQNP6ZnC6EONGuGTDgTTU30\n-----END RSA PRIVATE KEY-----\n'
        #
        # We strip the BEGIN/END lines and remove newlines in the database
        # format.

        if (server.web_server_certificate is None
            or server.web_server_private_key is None):
            cert_pem, key_pem = generate_self_signed_certificate()
            server.web_server_private_key = ''.join(key_pem.split('\n')[1:-2])
            server.web_server_certificate = ''.join(cert_pem.split('\n')[1:-2])

    ## Deploy will upload web server source database data and client builds
    #psi_deploy.deploy(host)
    # NOTE: call psi_ops_deploy.deploy_host() to complete the install process


def install_TCS_host(host, servers, existing_server_ids, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, plugins):

    # Limitation: only one server per host currently implemented

    install_TCS_firewall_rules(host, servers, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, True)

    install_TCS_psi_limit_load(host)

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    install_geoip_database(ssh, True)

    ssh.close()

    # Generate server ID, web server key material, SSH key material
    # See comments in install_legacy_host describing key formats.

    for server in servers:

        if server.id is None:
            server.id = generate_unique_server_id(existing_server_ids)

        if server.web_server_secret is None:
            server.web_server_secret = generate_web_server_secret()

        if (server.web_server_certificate is None
            or server.web_server_private_key is None):
            cert_pem, key_pem = generate_self_signed_certificate()
            server.web_server_private_key = key_pem
            server.web_server_certificate = cert_pem

        if (server.ssh_username is None
            or server.ssh_password is None):
            server.ssh_username = 'psiphon_ssh_%s' % (
                binascii.hexlify(os.urandom(SSH_RANDOM_USERNAME_SUFFIX_BYTE_LENGTH)),)
            server.ssh_password = binascii.hexlify(os.urandom(SSH_PASSWORD_BYTE_LENGTH))

        if server.ssh_host_key is None:
            # For TCS, generate SSH keys directly using M2Crypto.
            # Legacy servers use the host key generated by OpenSSH.
            # We attempt to generate keys with similar parameters.
            rsa_key = M2Crypto.RSA.gen_key(TCS_SSH_RSA_KEY_LENGTH_BITS, TCS_SSH_RSA_KEY_EXPONENT)

            # output format for the public key, which is saved in
            # psinet and included in server entries:
            # 'ssh-rsa <base64>', where the base64 portion is the public key encoded according to RFC 4253 section 6.6
            server.ssh_host_key = 'ssh-rsa ' + base64.b64encode('\x00\x00\x00\x07\x73\x73\x68\x2d\x72\x73\x61' + rsa_key.pub()[0] + rsa_key.pub()[1])

            # store private key in psinet (legacy doesn't do this).
            # Stored in psiphond.config format.
            buf = M2Crypto.BIO.MemoryBuffer()
            rsa_key.save_key_bio(buf, cipher=None)
            server.TCS_ssh_private_key = buf.read()

        if server.ssh_obfuscated_key is None:
            server.ssh_obfuscated_key = binascii.hexlify(os.urandom(SSH_OBFUSCATED_KEY_BYTE_LENGTH))

def install_firewall_rules(host, servers, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, plugins, do_blacklist=True):

    if host.is_TCS:
        install_TCS_firewall_rules(host, servers, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, do_blacklist)
    else:
        install_legacy_firewall_rules(host, servers, plugins, do_blacklist)


def install_legacy_firewall_rules(host, servers, plugins, do_blacklist):

    iptables_rules_path = '/etc/iptables.rules'
    iptables_rules_contents = '''
*filter
    -A INPUT -i lo -p tcp -m tcp --dport 7300 -j ACCEPT
    -A INPUT -i lo -p tcp -m tcp --dport 6379 -j ACCEPT
    -A INPUT -i lo -p tcp -m tcp --dport 6000 -j ACCEPT''' + ''.join(
    # tunneled OSSH
    ['''
    -A INPUT -i lo -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -j ACCEPT'''.format(
            str(s.internal_ip_address), str(s.ssh_obfuscated_port)) for s in servers
                if (s.capabilities['FRONTED-MEEK'] or s.capabilities['UNFRONTED-MEEK']) and s.ssh_obfuscated_port]) + ''.join(
    # tunneled web requests
    ['''
    -A INPUT -i lo -d %s -p tcp -m state --state NEW -m tcp --dport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.web_server_port)) for s in servers]) + '''
    -A INPUT -d 127.0.0.0/8 ! -i lo -j DROP
    -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
    -A INPUT -p tcp -m state --state NEW -m tcp --dport %s -j ACCEPT''' % (host.ssh_port,) + ''.join(
    # meek server
    ['''
    -A INPUT -d %s -p tcp -m state --state NEW -m tcp --dport %s -m limit --limit 1000/sec -j ACCEPT'''
            % (str(s.internal_ip_address), str(host.meek_server_port)) for s in servers
                if (s.capabilities['FRONTED-MEEK'] or s.capabilities['UNFRONTED-MEEK']) and host.meek_server_port]) + ''.join(
    # web servers
    ['''
    -A INPUT -d %s -p tcp -m state --state NEW -m tcp --dport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.web_server_port)) for s in servers
                if s.capabilities['handshake']]) + ''.join(
    # SSH
    ['''
    -A INPUT -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -m recent --set --name {2}
    -A INPUT -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -m recent --update --name {2} --seconds 60 --hitcount 3 -j DROP
    -A INPUT -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -j ACCEPT'''.format(
            str(s.internal_ip_address), str(s.ssh_port),
            'LIMIT-' + str(s.internal_ip_address).replace('.', '-') + '-' + str(s.ssh_port)) for s in servers
                if s.capabilities['SSH']]) + ''.join(
    # OSSH
    ['''
    -A INPUT -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -m recent --set --name {2}
    -A INPUT -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -m recent --update --name {2} --seconds 60 --hitcount 3 -j DROP
    -A INPUT -d {0} -p tcp -m state --state NEW -m tcp --dport {1} -j ACCEPT'''.format(
            str(s.internal_ip_address), str(s.ssh_obfuscated_port),
            'LIMIT-' + str(s.internal_ip_address).replace('.', '-') + '-' + str(s.ssh_obfuscated_port)) for s in servers
                if s.capabilities['OSSH']]) + ''.join(
    # VPN
    ['''
    -A INPUT -d {0} -p esp -j ACCEPT
    -A INPUT -d {0} -p ah -j ACCEPT
    -A INPUT -d {0} -p udp --dport 500 -j ACCEPT
    -A INPUT -d {0} -p udp --dport 4500 -j ACCEPT
    -A INPUT -d {0} -i ipsec+ -p udp -m udp --dport l2tp -j ACCEPT'''.format(
            str(s.internal_ip_address)) for s in servers
                if s.capabilities['VPN']]) + '''
    -A INPUT -p tcp -j REJECT --reject-with tcp-reset
    -A INPUT -j DROP
    -A FORWARD -s 10.0.0.0/8 -p tcp -m multiport --dports 80,443,465,554,587,993,995,1935,5190,7070,8000,8001 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p udp -m multiport --dports 80,443,465,554,587,993,995,1935,5190,7070,8000,8001 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p tcp -m multiport --dports 3478,5242,4244,9339 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p udp -m multiport --dports 3478,5243,7985,9785 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p tcp -m multiport --dports 8443,4433,31337 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p udp -m multiport --dports 8443,4433,31337 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p tcp -m multiport --dports 110,143,2560,8080,5060,5061,5062,9180,11000,12000,25565 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p udp -m multiport --dports 110,143,2560,8080,5060,5061,5062,9180,11000,12000,25565 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p tcp -m multiport --dports 6695:6699,27015:27037 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -p udp -m multiport --dports 4379,4380,4950,4955,27000:27037 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 31.13.64.0/18 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 179.60.192.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 91.108.4.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 91.108.8.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 91.108.12.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 91.108.16.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 91.108.56.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 149.154.164.0/22 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 8.8.8.8 -p tcp --dport 53 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 8.8.8.8 -p udp --dport 53 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 8.8.4.4 -p tcp --dport 53 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 8.8.4.4 -p udp --dport 53 -j ACCEPT
    -A FORWARD -s 10.0.0.0/8 -d 10.0.0.0/8 -j DROP
    -A FORWARD -s 10.0.0.0/8 -j REJECT''' + ''.join(
    # tunneled ossh requests
    ['''
    -A OUTPUT -d {0} -o lo -p tcp -m tcp --dport {1} -j ACCEPT
    -A OUTPUT -s {0} -o lo -p tcp -m tcp --sport {1} -j ACCEPT'''.format(
            str(s.internal_ip_address), str(s.ssh_obfuscated_port)) for s in servers
                if s.ssh_obfuscated_port]) + ''.join(
    # tunneled web requests (always provided, regardless of capabilities)
    ['''
    -A OUTPUT -d {0} -o lo -p tcp -m tcp --dport {1} -j ACCEPT
    -A OUTPUT -s {0} -o lo -p tcp -m tcp --sport {1} -j ACCEPT'''.format(
            str(s.internal_ip_address), str(s.web_server_port)) for s in servers]) + '''
    -A OUTPUT -o lo -p tcp -m tcp --dport 7300 -j ACCEPT
    -A OUTPUT -o lo -p tcp -m tcp --dport 6379 -m owner --uid-owner root -j ACCEPT
    -A OUTPUT -o lo -p tcp -m tcp --dport 6000 -m owner --uid-owner root -j ACCEPT
    -A OUTPUT -o lo -p tcp -m tcp --dport 6379 -m owner --uid-owner www-data -j ACCEPT
    -A OUTPUT -o lo -p tcp -m tcp --sport 7300 -j ACCEPT
    -A OUTPUT -o lo -p tcp -m tcp --sport 6379 -j ACCEPT
    -A OUTPUT -o lo -p tcp -m tcp --sport 6000 -j ACCEPT
    -A OUTPUT -o lo -j REJECT
    -A OUTPUT -p tcp -m multiport --dports 53,80,443,465,554,587,993,995,1935,5190,7070,8000,8001 -j ACCEPT
    -A OUTPUT -p udp -m multiport --dports 53,80,443,465,554,587,993,995,1935,5190,7070,8000,8001 -j ACCEPT
    -A OUTPUT -p tcp -m multiport --dports 5222,5223,5224,5228,5229,5230,5269,14259 -j ACCEPT
    -A OUTPUT -p udp -m multiport --dports 5222,5223,5224,5228,5229,5230,5269,14259 -j ACCEPT
    -A OUTPUT -p tcp -m multiport --dports 3478,5242,4244,9339 -j ACCEPT
    -A OUTPUT -p udp -m multiport --dports 3478,5243,7985,9785 -j ACCEPT
    -A OUTPUT -p tcp -m multiport --dports 8443,4433,31337 -j ACCEPT
    -A OUTPUT -p udp -m multiport --dports 8443,4433,31337 -j ACCEPT
    -A OUTPUT -p tcp -m multiport --dports 110,143,2560,8080,5060,5061,5062,9180,11000,12000,25565 -j ACCEPT
    -A OUTPUT -p udp -m multiport --dports 110,143,2560,8080,5060,5061,5062,9180,11000,12000,25565 -j ACCEPT
    -A OUTPUT -p tcp -m multiport --dports 6695:6699,27015:27037 -j ACCEPT
    -A OUTPUT -p udp -m multiport --dports 4379,4380,4950,4955,27000:27037 -j ACCEPT
    -A OUTPUT -d 31.13.64.0/18 -j ACCEPT
    -A OUTPUT -d 179.60.192.0/22 -j ACCEPT
    -A OUTPUT -d 91.108.4.0/22 -j ACCEPT
    -A OUTPUT -d 91.108.8.0/22 -j ACCEPT
    -A OUTPUT -d 91.108.12.0/22 -j ACCEPT
    -A OUTPUT -d 91.108.16.0/22 -j ACCEPT
    -A OUTPUT -d 91.108.56.0/22 -j ACCEPT
    -A OUTPUT -d 149.154.164.0/22 -j ACCEPT
    -A OUTPUT -p udp -m udp --dport 123 -j ACCEPT
    -A OUTPUT -p tcp -m tcp --sport %s -j ACCEPT''' % (host.ssh_port,) + ''.join(
    # tunneled ossh requests on NATed servers
    ['''
    -A OUTPUT -d %s -p tcp -m tcp --dport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.ssh_obfuscated_port)) for s in servers
                if s.ssh_obfuscated_port and (s.ip_address != s.internal_ip_address)]) + ''.join(
    # tunneled web requests on NATed servers don't go out lo
    ['''
    -A OUTPUT -d %s -p tcp -m tcp --dport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.web_server_port)) for s in servers
                if s.ip_address != s.internal_ip_address]) + ''.join(
    # meek server
    ['''
    -A OUTPUT -s %s -p tcp -m tcp --sport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(host.meek_server_port)) for s in servers
                if host.meek_server_port]) + ''.join(
    # web servers
    ['''
    -A OUTPUT -s %s -p tcp -m tcp --sport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.web_server_port)) for s in servers
                if s.web_server_port]) + ''.join(
    # SSH
    ['''
    -A OUTPUT -s %s -p tcp -m tcp --sport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.ssh_port)) for s in servers
                if s.ssh_port]) + ''.join(
    # OSSH
    ['''
    -A OUTPUT -s %s -p tcp -m tcp --sport %s -j ACCEPT'''
            % (str(s.internal_ip_address), str(s.ssh_obfuscated_port)) for s in servers
                if s.ssh_obfuscated_port]) + ''.join(
    # VPN
    ['''
    -A OUTPUT -s {0} -p esp -j ACCEPT
    -A OUTPUT -s {0} -p ah -j ACCEPT
    -A OUTPUT -s {0} -p udp --sport 500 -j ACCEPT
    -A OUTPUT -s {0} -p udp --sport 4500 -j ACCEPT
    -A OUTPUT -s {0} -o ipsec+ -p udp -m udp --dport l2tp -j ACCEPT'''.format(
            str(s.internal_ip_address)) for s in servers
                if s.capabilities['VPN']]) + ''.join(
    ['''
    -A OUTPUT -s %s -p tcp -m tcp --tcp-flags ALL ACK,RST -j ACCEPT'''
            % (str(s.internal_ip_address), ) for s in servers]) + '''
    -A OUTPUT -j REJECT
COMMIT

*nat''' + ''.join(
    # Port forward from 443 to web servers
    # NOTE: exclude for servers with meek capability (or is fronted) and meek_server_port is 443
    #       or OSSH is running on 443
    ['''
    -A PREROUTING -i eth+ -p tcp -d %s --dport 443 -j DNAT --to-destination :%s'''
            % (str(s.internal_ip_address), str(s.web_server_port)) for s in servers
                if s.capabilities['handshake']
                and not (
                    ((s.capabilities['FRONTED-MEEK'] or s.capabilities['UNFRONTED-MEEK']) and int(host.meek_server_port) == 443) or
                    (s.capabilities['OSSH'] and int(s.ssh_obfuscated_port) == 443))]) + ''.join(
    # Port forward alternate ports
    ['''
    -A PREROUTING -i eth+ -p tcp -d %s --dport %s -j DNAT --to-destination :%s'''
            % (str(s.internal_ip_address), str(alternate), str(s.ssh_obfuscated_port))
                for s in servers if s.alternate_ssh_obfuscated_ports
                for alternate in s.alternate_ssh_obfuscated_ports]) + '''
    -A POSTROUTING -s 10.0.0.0/8 -o eth+ -j MASQUERADE''' + ''.join(
    # tunneled web requests on NATed servers need to be redirected to the servers' internal ip addresses
    ['''
    -A OUTPUT -p tcp -m tcp -d %s --dport %s -j DNAT --to-destination %s'''
            % (str(s.ip_address), str(s.web_server_port), str(s.internal_ip_address)) for s in servers
                if s.ip_address != s.internal_ip_address]) + '''
COMMIT
'''

    for plugin in plugins:
        if hasattr(plugin, 'iptables_rules_contents'):
            iptables_rules_contents = plugin.iptables_rules_contents(host, servers)

    # NOTE that we restart fail2ban after applying firewall rules because iptables-restore
    # flushes iptables which will remove any chains and rules that fail2ban creates on starting up
    if_up_script_path = '/etc/network/if-up.d/firewall'
    if_up_script_contents = '''#!/bin/sh

iptables-restore < %s
/etc/init.d/fail2ban restart
''' % (iptables_rules_path,)

    ssh_ports = set([str(host.ssh_port)])
    for server in servers:
        ssh_ports.add(str(server.ssh_port)) if server.capabilities['SSH'] else None
        ssh_ports.add(str(server.ssh_obfuscated_port)) if server.capabilities['OSSH'] else None

    fail2ban_local_path = '/etc/fail2ban/jail.local'
    fail2ban_local_contents = textwrap.dedent('''
        [ssh]
        port    = {0}

        [ssh-ddos]
        port    = {0}
        '''.format(','.join(ssh_ports)))

    meek_server_egress_ips = set([(str(s.egress_ip_address)) for s in servers
            if (s.capabilities['FRONTED-MEEK'] or s.capabilities['UNFRONTED-MEEK'])])
    if meek_server_egress_ips:
        fail2ban_local_contents = textwrap.dedent('''
        [DEFAULT]
        ignoreip = 127.0.0.1/8 {0}
        '''.format(' '.join(meek_server_egress_ips))) + fail2ban_local_contents

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    ssh.exec_command('echo "%s" > %s' % (iptables_rules_contents, iptables_rules_path))
    ssh.exec_command('echo "%s" > %s' % (if_up_script_contents, if_up_script_path))
    ssh.exec_command('chmod +x %s' % (if_up_script_path,))
    ssh.exec_command('echo "%s" > %s' % (fail2ban_local_contents, fail2ban_local_path))
    ssh.exec_command(if_up_script_path)
    ssh.close()

    if do_blacklist:
        install_malware_blacklist(host, False)


def install_TCS_firewall_rules(host, servers, TCS_psiphond_config_values, ssh_ip_address_whitelist, TCS_iptables_output_rules, do_blacklist):

    # TODO-TCS: security review

    # The TCS firewall rules are derived from the legacy rules with the following differences:
    # - fewer internal rules (e.g., no badvpn-udpgw, redis, or CherryPy)
    # - no VPN rules
    # - no egress port rules (these are enforced in psiphond)

    # Limitation: only one server per host currently implemented
    server = [server for server in servers if server.ip_address == host.ip_address][0]

    # Default posture for INPUT is reject. Allow connections to management ports
    # on INPUT.

    # For DOCKER:
    # Web/protocol ports are handled by psiphond inside a container.  Rate limiting
    # rules are applied to the FORWARD chain instead of INPUT since the system
    # forwards packets to the container.

    # Web ports are rate limited with "limit", which is appropriate when the remote address is
    # shared (CDN) and the protocol may feature many TCP connections (HTTPS) per session.
    # Other protocols are rate limited with "recent", which is more appropriate for individual
    # remote addresses.

    # AcceptUnfrontedRateLimitList/AcceptRecentRateLimit
    # should be Python lists of string values, with the strings conforming to iptables syntax:
    #
    # AcceptUnfrontedRateLimitList: "--limit <n>/sec"
    # AcceptRecentRateLimitList:    "--seconds <n> --hitcount <m>"

    accept_unfronted_rate_limit = "--limit 1000/sec"
    accept_unfronted_rate_limits = TCS_psiphond_config_values.get('AcceptUnfrontedRateLimitList', None)
    if accept_unfronted_rate_limits is not None:
        assert(isinstance(accept_unfronted_rate_limits, list))
        accept_unfronted_rate_limit = random.choice(accept_unfronted_rate_limits)

    accept_recent_rate_limit = "--seconds 60 --hitcount 3"
    accept_recent_rate_limits = TCS_psiphond_config_values.get('AcceptRecentRateLimitList', None)
    if accept_recent_rate_limits is not None:
        assert(isinstance(accept_recent_rate_limits, list))
        accept_recent_rate_limit = random.choice(accept_recent_rate_limits)

    # Create a new chain for rate limiting.
    new_rate_limit_chain = textwrap.dedent('''
        -N PSI_RATE_LIMITING''')

    accept_with_unfronted_limit_rate_template = textwrap.dedent('''
        -A PSI_RATE_LIMITING -p tcp -m state --state NEW -m tcp --dport {port} -m limit {accept_unfronted_rate_limit} -j ACCEPT''')

    accept_with_fronted_limit_rate_template = textwrap.dedent('''
        -A PSI_RATE_LIMITING -p tcp -m state --state NEW -m tcp --dport {port} -m limit --limit 1000/sec -j ACCEPT''')

    accept_with_recent_rate_template = textwrap.dedent('''
        -A PSI_RATE_LIMITING -p {proto} -m state --state NEW -m {proto} --dport {port} -m recent --set --name LIMIT-{proto}-{port}
        -A PSI_RATE_LIMITING -p {proto} -m state --state NEW -m {proto} --dport {port} -m recent --update --name LIMIT-{proto}-{port} {accept_recent_rate_limit} -j DROP
        -A PSI_RATE_LIMITING -p {proto} -m state --state NEW -m {proto} --dport {port} -j ACCEPT''')

    return_from_rate_limit_chain = textwrap.dedent('''
        -A PSI_RATE_LIMITING -j RETURN''')

    rate_limit_rules = [new_rate_limit_chain]

    if host.TCS_type == 'NATIVE':
        firewall_web_server_port = server.web_server_port
    elif host.TCS_type == 'DOCKER':
        firewall_web_server_port = psi_ops_deploy.TCS_DOCKER_WEB_SERVER_PORT
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    if server.capabilities['handshake']:
        web_server_port_rule = accept_with_recent_rate_template.format(
                accept_recent_rate_limit=accept_recent_rate_limit,
                proto="tcp",
                port=str(firewall_web_server_port))
        rate_limit_rules += [web_server_port_rule]

    if host.TCS_type == 'NATIVE':
        use_external_ports = True
    elif host.TCS_type == 'DOCKER':
        use_external_ports = False
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    for protocol, port in psi_ops_deploy.get_supported_protocol_ports(host, server, external_ports=use_external_ports).iteritems():
        protocol_port_rule = ''
        if 'UNFRONTED-MEEK' in protocol:
            protocol_port_rule = accept_with_unfronted_limit_rate_template.format(
                accept_unfronted_rate_limit=accept_unfronted_rate_limit,
                port=str(port))
        elif 'MEEK' in protocol:
            protocol_port_rule = accept_with_fronted_limit_rate_template.format(
                port=str(port))
        elif 'QUIC' in protocol:
            protocol_port_rule = accept_with_recent_rate_template.format(
                accept_recent_rate_limit=accept_recent_rate_limit,
                proto="udp",
                port=str(port))
        elif ('TAPDANCE' in protocol) or ('CONJURE' in protocol):
            protocol_port_rule = accept_with_fronted_limit_rate_template.format(
                port=str(port))
        else:
            protocol_port_rule = accept_with_recent_rate_template.format(
                accept_recent_rate_limit=accept_recent_rate_limit,
                proto="tcp",
                port=str(port))
        rate_limit_rules += [protocol_port_rule]

    rate_limit_rules += [return_from_rate_limit_chain]

    limit_rate_forward_rules = []

    iptables_rate_limit_rules_path = '/etc/iptables.rules.psi_rate_limit'
    iptables_rate_limit_rules_contents = textwrap.dedent('''
        *filter
        {filter_limit_rate}
        {filter_forward}
        COMMIT
        ''').format(
            filter_limit_rate='\n'.join(rate_limit_rules),
            filter_forward='\n'.join(limit_rate_forward_rules))

    if ssh_ip_address_whitelist:
        management_port_rule = ''.join([textwrap.dedent('''
        -A INPUT -s {whitelist_ip_address} -p tcp -m state --state NEW -m tcp --dport {management_port} -j ACCEPT''')
        .format(whitelist_ip_address=whitelist_ip, management_port=host.ssh_port)
        for whitelist_ip in ssh_ip_address_whitelist])
    else:
        management_port_rule = textwrap.dedent('''
        -A INPUT -p tcp -m state --state NEW -m tcp --dport {management_port} -j ACCEPT''').format(management_port=host.ssh_port)

    port_rules = [management_port_rule]

    if host.TCS_type == 'NATIVE':
        # tunneled web requests
        port_rules += [
            '-A INPUT -i lo -d {web_server_ip_address} -p tcp -m state --state NEW -m tcp --dport {web_server_port} -j ACCEPT'.format(
                web_server_ip_address=str(server.internal_ip_address), web_server_port=str(server.web_server_port))
        ]
    elif host.TCS_type == 'DOCKER':
        pass
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    # Common INPUT rules

    filter_input_rules = [

        '-A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT',

        # Standard anti-spoofing rules: block external packets with loopback address
        '-A INPUT -s 127.0.0.0/8 ! -i lo -j DROP',
        '-A INPUT -d 127.0.0.0/8 ! -i lo -j DROP',
        '-A OUTPUT -s 127.0.0.0/8 ! -o lo -j DROP',
        '-A OUTPUT -d 127.0.0.0/8 ! -o lo -j DROP'

    ] + port_rules

    if host.TCS_type == 'NATIVE':
        # Add PSI_RATE_LIMITING jump in the INPUT
        filter_input_rules += ['-A INPUT -j PSI_RATE_LIMITING']
    elif host.TCS_type == 'DOCKER':
        pass
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    filter_input_rules += [

        '-A INPUT -p tcp -j REJECT --reject-with tcp-reset',
        '-A INPUT -j DROP'

    ]

    filter_forward_rules = [

        '-A FORWARD -s 10.0.0.0/8 -d 10.0.0.0/8 -j DROP',
        '-A FORWARD -s 10.0.0.0/8 -o en+ -j ACCEPT',
        '-A FORWARD -s 10.0.0.0/8 -o eth+ -j ACCEPT',
        '-A FORWARD -d 10.0.0.0/8 -i en+ -j ACCEPT',
        '-A FORWARD -d 10.0.0.0/8 -i eth+ -j ACCEPT',
        '-A FORWARD -j DROP'

    ]

    # Default posture for OUTPUT is allow, as psiphond enforces port forward destination rules itself.

    filter_output_rules = TCS_iptables_output_rules[:] if TCS_iptables_output_rules else []
    filter_output_rules += [

        '-A OUTPUT -j ACCEPT'

    ]

    # NAT rules are used to implement service port forwarding.

    nat_prerouting_rules = []

    # Port forward from 443 to web servers
    # NOTE: exclude for servers with meek capability (or is fronted) and meek_server_port is 443 or OSSH is running on 443
    if server.capabilities['handshake'] and not (
            ((server.capabilities['FRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK-SESSION-TICKET']) and int(host.meek_server_port) == 443) or
            (server.capabilities['OSSH'] and int(server.ssh_obfuscated_port) == 443)):
        web_server_port_forward = textwrap.dedent('''

        -A PREROUTING -i en+ -p tcp -d {server_ip_address} --dport 443 -j DNAT --to-destination :{web_server_port}
        -A PREROUTING -i eth+ -p tcp -d {server_ip_address} --dport 443 -j DNAT --to-destination :{web_server_port}''').format(

            server_ip_address=str(server.internal_ip_address), web_server_port=str(server.web_server_port))
        nat_prerouting_rules += [web_server_port_forward]

    if server.alternate_ssh_obfuscated_ports:
        for alternate in server.alternate_ssh_obfuscated_ports:
            protocol_port_forward = textwrap.dedent('''

            -A PREROUTING -i en+ -p tcp -d {server_ip_address} --dport {alternate_port} -j DNAT --to-destination :{protocol_port}
            -A PREROUTING -i eth+ -p tcp -d {server_ip_address} --dport {alternate_port} -j DNAT --to-destination :{protocol_port}''').format(

                server_ip_address=str(server.internal_ip_address), alternate_port=str(alternate), protocol_port=str(server.ssh_obfuscated_port))
            nat_prerouting_rules += [protocol_port_forward]

    nat_postrouting_rules = [

        '-A POSTROUTING -s 10.0.0.0/8 -o en+ -j MASQUERADE',
        '-A POSTROUTING -s 10.0.0.0/8 -o eth+ -j MASQUERADE'

    ]

    iptables_rules_path = '/etc/iptables.rules'
    iptables_rules_contents = textwrap.dedent('''
        *filter
        {filter_input}
        {filter_output}
        {filter_forward}
        COMMIT
        *nat
        {nat_prerouting}
        {nat_postrouting}
        COMMIT
        ''').format(
            filter_input='\n'.join(filter_input_rules),
            filter_output='\n'.join(filter_output_rules),
            filter_forward='\n'.join(filter_forward_rules),
            nat_prerouting='\n'.join(nat_prerouting_rules),
            nat_postrouting='\n'.join(nat_postrouting_rules))


    (iptables_limit_load_rules_contents, iptables_limit_load_rules_path) = install_TCS_psi_limit_load_chain(host, server)

    # Note: restart fail2ban and docker after applying firewall rules because iptables-restore
    # flushes iptables which will remove any chains and rules that fail2ban creates on starting up
    if_up_script_path = '/etc/network/if-up.d/firewall'

    if host.TCS_type == 'NATIVE':
        if_up_script_contents = textwrap.dedent('''#!/bin/sh

            iptables-restore < {iptables_rate_limit_rules_path}
            iptables-restore --noflush < {iptables_limit_load_rules_path}
            iptables-restore --noflush < {iptables_rules_path}
            systemctl list-jobs | grep -q network.target || systemctl restart fail2ban.service
            ''').format(
                iptables_rules_path=iptables_rules_path,
                iptables_rate_limit_rules_path=iptables_rate_limit_rules_path,
                iptables_limit_load_rules_path=iptables_limit_load_rules_path)
    elif host.TCS_type == 'DOCKER':
        if_up_script_contents = textwrap.dedent('''#!/bin/sh

            iptables-restore < {iptables_rules_path}
            systemctl restart fail2ban.service
            systemctl restart docker.service
            iptables-restore --noflush < {iptables_rate_limit_rules_path}
            iptables-restore --noflush < {iptables_limit_load_rules_path}
            ''').format(
                iptables_rules_path=iptables_rules_path,
                iptables_rate_limit_rules_path=iptables_rate_limit_rules_path,
                iptables_limit_load_rules_path=iptables_limit_load_rules_path)
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    ssh.exec_command('echo "{iptables_rules_contents}" > {iptables_rules_path}'.format(
        iptables_rules_contents=iptables_rules_contents, iptables_rules_path=iptables_rules_path))
    ssh.exec_command('echo "{iptables_rate_limit_rules_contents}" > {iptables_rate_limit_rules_path}'.format(
        iptables_rate_limit_rules_contents=iptables_rate_limit_rules_contents,
        iptables_rate_limit_rules_path=iptables_rate_limit_rules_path))
    ssh.exec_command('echo "{iptables_limit_load_rules_contents}" > {iptables_limit_load_rules_path}'.format(
        iptables_limit_load_rules_contents=iptables_limit_load_rules_contents,
        iptables_limit_load_rules_path=iptables_limit_load_rules_path))
    ssh.exec_command('echo "{if_up_script_contents}" > {if_up_script_path}'.format(
        if_up_script_contents=if_up_script_contents, if_up_script_path=if_up_script_path))
    ssh.exec_command('chmod +x {if_up_script_path}'.format(
        if_up_script_path=if_up_script_path))
    ssh.exec_command(if_up_script_path)
    ssh.close()

    if do_blacklist:
        install_malware_blacklist(host, True)

def install_malware_blacklist(host, is_TCS):

    psi_ip_blacklist = 'psi_ipblacklist.py'
    psi_ip_blacklist_host_path = posixpath.join('/usr/local/bin', psi_ip_blacklist)
    if_up_script_path = '/etc/network/if-up.d/set_blocklist'
    cron_script_path = '/etc/cron.daily/set_blocklist'

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    if is_TCS:
        ssh.exec_command('apt-get install -y ipset')
    else:
        ssh.exec_command('apt-get install -y module-assistant xtables-addons-source')
        ssh.exec_command('module-assistant -i auto-install xtables-addons')

    ssh.put_file(os.path.join(os.path.abspath('.'), psi_ip_blacklist),
                 psi_ip_blacklist_host_path)
    ssh.exec_command('chmod +x %s' % (psi_ip_blacklist_host_path,))
    ssh.exec_command('ln -s %s %s' % (psi_ip_blacklist_host_path, if_up_script_path))
    ssh.exec_command('ln -s %s %s' % (psi_ip_blacklist_host_path, cron_script_path))
    ssh.exec_command(psi_ip_blacklist_host_path)
    ssh.close()


def install_geoip_database(ssh, is_TCS):

    #
    # Upload the local GeoIP databases (if they exist)
    #

    # legacy uses the v1 files; TCS uses the v2 files

    REMOTE_GEOIP_DIRECTORY = '/usr/local/share/GeoIP/'
    geo_ip_files = ['GeoIPCity.dat', 'GeoIPISP.dat']
    if is_TCS:
        geo_ip_files = ['GeoIP2-City.mmdb', 'GeoIP2-ISP.mmdb']

    for geo_ip_file in geo_ip_files:
        if os.path.isfile(geo_ip_file):
            ssh.put_file(os.path.join(os.path.abspath('.'), geo_ip_file),
                         posixpath.join(REMOTE_GEOIP_DIRECTORY, geo_ip_file))

def install_second_ip_address(host, new_ip_addresses_list):
    interfaces_path = '/etc/network/interfaces.d/multi_ip_interfaces'
    nat_routing_path = '/etc/network/if-up.d/nat_routing'
    interface_dev = 'eth0' #Default interface devicename

    if type(new_ip_addresses_list) != list:
        print("New IP Address has to be a list.")
        return

    ssh = psi_ssh.SSH(
        host.ip_address, host.ssh_port,
        host.ssh_username, host.ssh_password,
        host.ssh_host_key)

    interface_dev = ssh.exec_command("ip addr show | awk '/inet.*brd/{print $NF}'")[:-1]
    interface_up = ssh.exec_command('cat /sys/class/net/' + interface_dev + '/operstate')
    nat_routing_exist = ssh.exec_command('[ -f ' + nat_routing_path  + ' ] && echo "found" || echo "no"')

    if 'up' in interface_up:
        print("Checked {} is up, using it as default virtual interfaces".format(interface_dev))
    elif 'down' in interface_up:
        print("Checked {} is down, using eth1 as default virtual interfaces".format(interface_dev))
        interface_dev = 'eth1'

    interfaces_contents_list = []

    for i in range(0, len(new_ip_addresses_list)):
        new_ip_address = new_ip_addresses_list[i]
        interfaces_contents = textwrap.dedent('''auto {interface_dev}:{virtual_interface_number}
        allow-hotplug {interface_dev}:{virtual_interface_number}
        iface {interface_dev}:{virtual_interface_number} inet static
            address {ip_address}
            netmask 255.255.255.0
        ''').format(interface_dev=interface_dev, virtual_interface_number=i+1, ip_address=new_ip_address)
        interfaces_contents_list.append(interfaces_contents)
    new_interfaces_contents = '\n'.join(interfaces_contents_list)

    if 'no' in nat_routing_exist:
        print("Nat routing iptables rule not found, creating a new one with header.")
        new_nat_routing_header = textwrap.dedent('''#!/bin/sh''')
        ssh.exec_command('echo "{new_nat_routing_header}" > {nat_routing_path}'.format(
            new_nat_routing_header=new_nat_routing_header, nat_routing_path=nat_routing_path))

    new_nat_routing_contents = textwrap.dedent('''/sbin/iptables -t nat -I PREROUTING -j DNAT -d {new_ip_addresses} --to-destination {host_ip_address}
    ''').format(new_ip_addresses=','.join(new_ip_addresses_list), host_ip_address=host.ip_address)

    ssh.exec_command('echo "{second_interfaces_contents}" >> {interfaces_path}'.format(
        second_interfaces_contents=new_interfaces_contents, interfaces_path=interfaces_path))

    ssh.exec_command('echo "{new_nat_routing_contents}" >> {nat_routing_path}'.format(
        new_nat_routing_contents=new_nat_routing_contents, nat_routing_path=nat_routing_path))

    ssh.exec_command('chmod +x {nat_routing_path}'.format(nat_routing_path=nat_routing_path))

    ssh.close()

def install_psi_limit_load(host, servers):
    if host.is_TCS:
        install_TCS_psi_limit_load(host)
    else:
        install_legacy_psi_limit_load(host, servers)


def install_legacy_psi_limit_load(host, servers):

    # NOTE: only disabling SSH/OSSH/IKE since disabling the web server from external access
    #       would also prevent current VPN users from accessing the web server.

    rules = (
    # SSH
    [' INPUT -d %s -p tcp -m state --state NEW -m tcp --dport %s -j REJECT --reject-with tcp-reset'
            % (str(s.internal_ip_address), str(s.ssh_port)) for s in servers
                if s.capabilities['SSH']] +
    # OSSH
    # NOTE: that this also disables new tunneled OSSH connections ie through meek
    [' INPUT -d %s -p tcp -m state --state NEW -m tcp --dport %s -j REJECT --reject-with tcp-reset'
            % (str(s.internal_ip_address), str(s.ssh_obfuscated_port)) for s in servers
                if s.ssh_obfuscated_port] +

    # VPN
    [' INPUT -d %s -p udp --dport 500 -j DROP'
            % (str(s.internal_ip_address), ) for s in servers
                if s.capabilities['VPN']] )

    disable_services = '\n    '.join(['iptables -I' + rule for rule in rules])

    enable_services = '\n    '.join(['iptables -D' + rule for rule in rules])

    script = '''
#!/bin/bash

threshold_load_per_cpu=4
threshold_mem=20
threshold_swap=20

while true; do
    loaded_cpu=0
    num_cpu=`grep 'model name' /proc/cpuinfo | wc -l`
    threshold_cpu=$(($threshold_load_per_cpu * $num_cpu - 1))
    load_cpu=`uptime | cut -d , -f 4 | cut -d : -f 2 | awk -F \. '{print $1}'`
    if [ "$load_cpu" -ge "$threshold_cpu" ]; then
        loaded_cpu=1
        logger psi_limit_load: CPU load threshold reached.
        break
    fi

    free=$(free | grep "buffers/cache" | awk '{print $4/($3+$4) * 100.0}')
    if [ -z "$free" ]; then
        free=$(free | grep "Mem" | awk '{print $7/$2 * 100.0}')
    fi
    loaded_mem=$(echo "$free<$threshold_mem" | bc)
    if [ $loaded_mem -eq 1 ]; then
        logger psi_limit_load: Free memory load threshold reached.
    fi

    loaded_swap=0
    total_swap=$(free | grep "Swap" | awk '{print $2}')
    if [ $total_swap -ne 0 ]; then
        free_swap=$(free | grep "Swap" | awk '{print $4/$2 * 100.0}')
        loaded_swap=$(echo "$free_swap<$threshold_swap" | bc)
        if [ $loaded_swap -eq 1 ]; then
            logger psi_limit_load: Swap threshold reached.
        fi
    fi

    break
done

if [ $loaded_cpu -eq 1 ] || [ $loaded_mem -eq 1 ] || [ $loaded_swap -eq 1 ]; then
    %s
    %s
    service xinetd stop
else
    if [[ -z $(pgrep xinetd) ]]; then
        service xinetd restart
    fi
    %s
fi
exit 0
''' % (enable_services, disable_services, enable_services)

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    ssh.exec_command('apt-get install -y bc')

    psi_limit_load_host_path = '/usr/local/sbin/psi_limit_load'

    file = tempfile.NamedTemporaryFile(delete=False)
    file.write(script)
    file.close()
    ssh.put_file(file.name, psi_limit_load_host_path)
    os.remove(file.name)

    ssh.exec_command('chmod +x %s' % (psi_limit_load_host_path,))

    cron_file = '/etc/cron.d/psi-limit-load'
    ssh.exec_command('echo "SHELL=/bin/sh" > %s;' % (cron_file,) +
                     'echo "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin" >> %s;' % (cron_file,) +
                     'echo "* * * * * root %s" >> %s' % (psi_limit_load_host_path, cron_file))


def install_TCS_psi_limit_load(host, disable_permanently=False):

    # The TCS psi_limit_load is mostly the same as legacy except:
    # - no VPN case
    # - signals psihpond to stop/resume establishing new tunnels instead of using
    #   iptables to reject connections from meek to OSS (which is no longer possible)
    # - no equivilent to xinetd
    #
    # For TCS Native:
    # - INPUT instead of FORWARD -o docker0

    if host.TCS_type == 'NATIVE':
        psi_limit_load_chain_name = 'INPUT'
        syn_sent_check = 'netstat -tn | grep SYN_SENT | wc -l'
    elif host.TCS_type == 'DOCKER':
        psi_limit_load_chain_name = 'FORWARD -o docker0'
        syn_sent_check = 'docker exec psiphond-run netstat -tn | grep SYN_SENT | wc -l'
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    if disable_permanently:
        script = '''
#!/bin/bash

iptables -D %s -j PSI_LIMIT_LOAD
iptables -I %s -j PSI_LIMIT_LOAD
%s
exit 0
'''  % (psi_limit_load_chain_name, psi_limit_load_chain_name, psi_ops_deploy.TCS_PSIPHOND_STOP_ESTABLISHING_TUNNELS_SIGNAL_COMMAND)
    else:
        script = '''
#!/bin/bash

threshold_load_per_cpu=1
threshold_mem=25
threshold_syn_sent=1000

while true; do

    loaded_cpu=0
    num_cpu=`grep 'model name' /proc/cpuinfo | wc -l`
    threshold_cpu=$(($threshold_load_per_cpu * $num_cpu))
    load_cpu=`uptime | cut -d , -f 4 | cut -d : -f 2 | awk -F \. '{print $1}'`
    if [ "$load_cpu" -ge "$threshold_cpu" ]; then
        loaded_cpu=1
        logger psi_limit_load: CPU load threshold reached.
        break
    fi

    free=$(free | grep "buffers/cache" | awk '{print $4/($3+$4) * 100.0}')
    if [ -z "$free" ]; then
        free=$(free | grep "Mem" | awk '{print $7/$2 * 100.0}')
    fi
    loaded_mem=$(echo "$free<$threshold_mem" | bc)
    if [ $loaded_mem -eq 1 ]; then
        logger psi_limit_load: Free memory load threshold reached.
    fi

    loaded_net=0
    syn_sent=`%s`
    if [ $syn_sent -ge $threshold_syn_sent ]; then
        loaded_net=1
        logger psi_limit_load: SYN_SENT threshold reached.
    fi

    break
done

if [ $loaded_cpu -eq 1 ] || [ $loaded_mem -eq 1 ] || [ $loaded_net -eq 1 ]; then
    %s
else
    %s
fi
exit 0
''' % (syn_sent_check,
        psi_ops_deploy.TCS_PSIPHOND_STOP_ESTABLISHING_TUNNELS_SIGNAL_COMMAND,
        psi_ops_deploy.TCS_PSIPHOND_RESUME_ESTABLISHING_TUNNELS_SIGNAL_COMMAND)

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    ssh.exec_command('apt-get install -y bc')

    psi_limit_load_host_path = '/usr/local/sbin/psi_limit_load'

    file = tempfile.NamedTemporaryFile(delete=False)
    file.write(script)
    file.close()
    ssh.put_file(file.name, psi_limit_load_host_path)
    os.remove(file.name)

    ssh.exec_command('chmod +x %s' % (psi_limit_load_host_path,))

    cron_file = '/etc/cron.d/psi-limit-load'
    ssh.exec_command('echo "SHELL=/bin/sh" > %s;' % (cron_file,) +
                     'echo "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin" >> %s;' % (cron_file,) +
                     'echo "* * * * * root %s" >> %s' % (psi_limit_load_host_path, cron_file))

def install_TCS_psi_limit_load_chain(host, server):

    limit_load_new_chain = '-N PSI_LIMIT_LOAD'

    limit_load_template_tcp = '-A PSI_LIMIT_LOAD -p tcp -m state --state NEW -m tcp --dport {port} -j REJECT --reject-with tcp-reset'
    limit_load_template_udp = '-A PSI_LIMIT_LOAD -p udp -m state --state NEW -m udp --dport {port} -j REJECT --reject-with icmp-port-unreachable'

    limit_load_return = '-A PSI_LIMIT_LOAD -j RETURN'

    limit_load_rules = [limit_load_new_chain]

    # For TCS native (Docker less) use external ports instead of docker port.
    if host.TCS_type == 'NATIVE':
        use_external_ports = True
    elif host.TCS_type == 'DOCKER':
        use_external_ports = False
    else:
        raise 'Unhandled host.TCS_type: ' + host.TCS_type

    for protocol, port in psi_ops_deploy.get_supported_protocol_ports(host, server, external_ports=use_external_ports, meek_ports=False).iteritems():
        if 'QUIC' in protocol:
            limit_load_rules += [limit_load_template_udp.format(port=str(port))]
        else:
            limit_load_rules += [limit_load_template_tcp.format(port=str(port))]

    limit_load_rules += [limit_load_return]

    iptables_limit_load_rules_path = '/etc/iptables.rules.psi_limit_load'
    iptables_limit_load_rules_contents = textwrap.dedent('''
        *filter
        {filter_limit_load}
        COMMIT
        ''').format(filter_limit_load='\n'.join(limit_load_rules))

    return (iptables_limit_load_rules_contents, iptables_limit_load_rules_path)


def install_user_count_and_log(host, servers):

    if host.is_TCS:
        # This is obsolete
        return

    server_details = {}
    for server in servers:
        server_details[server.id] = {"commands": {}, "fronted": server.capabilities["FRONTED-MEEK"]}
        server_details[server.id]["commands"]["obfuscated_ssh_users_command"] = "netstat -tpn | grep \"%s:%d \" | grep sshd | grep ESTABLISHED | wc -l" % (server.ip_address, int(server.ssh_obfuscated_port))
        server_details[server.id]["commands"]["meek_users_command"] = "netstat -tpn | grep \"%s:%d *%s\" | grep sshd | grep ESTABLISHED | wc -l" % (server.ip_address, int(server.ssh_obfuscated_port), server.ip_address)
        server_details[server.id]["commands"]["ssh_users_command"] = "" if not server.capabilities["SSH"] else \
            "netstat -tpn | grep \"%s:%d \" | grep sshd | grep ESTABLISHED | wc -l" % (server.ip_address, int(server.ssh_port))

    vpn_users_command = "ifconfig | grep ppp | wc -l"

    script = '''
#!/usr/bin/env python

import json
from datetime import datetime
import os
import syslog
import time
import random
from collections import defaultdict

time.sleep(random.choice(range(0,50)))

log_record = {
                "event_name": "user_count",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "host_id": "%s",
                "region": "%s",
                "provider": "%s",
                "datacenter": "%s",
                "users": {
                    "obfuscated_ssh": {
                        "servers": defaultdict(dict),
                        "total": 0
                    },
                    "ssh": {
                        "servers": defaultdict(dict),
                        "total": 0
                    },
                    "vpn": 0,
                    "total": 0
                }
            }

server_details = %s
vpn_users_command = "%s"

for server_id in server_details:
    log_record["users"]["obfuscated_ssh"]["servers"][server_id]["total"] = int(os.popen(server_details[server_id]["commands"]["obfuscated_ssh_users_command"]).read().strip())
    log_record["users"]["obfuscated_ssh"]["total"] += log_record["users"]["obfuscated_ssh"]["servers"][server_id]["total"]

    log_record["users"]["obfuscated_ssh"]["servers"][server_id]["meek"] = int(os.popen(server_details[server_id]["commands"]["meek_users_command"]).read().strip())
    log_record["users"]["obfuscated_ssh"]["servers"][server_id]["direct"] = max(0,
        log_record["users"]["obfuscated_ssh"]["servers"][server_id]["total"] - log_record["users"]["obfuscated_ssh"]["servers"][server_id]["meek"])
    log_record["users"]["obfuscated_ssh"]["servers"][server_id]["fronted"] = server_details[server_id]["fronted"]

    ssh_users_command = server_details[server_id]["commands"]["ssh_users_command"]
    log_record["users"]["ssh"]["servers"][server_id]["total"] = 0 if len(ssh_users_command) == 0 else int(os.popen(ssh_users_command).read().strip())
    log_record["users"]["ssh"]["total"] += log_record["users"]["ssh"]["servers"][server_id]["total"]

log_record["users"]["vpn"] = int(os.popen(vpn_users_command).read().strip())
log_record["users"]["total"] = log_record["users"]["obfuscated_ssh"]["total"] + log_record["users"]["ssh"]["total"] + log_record["users"]["vpn"]

syslog.openlog('psiphon-user-count')
syslog.syslog(syslog.LOG_INFO, json.dumps(log_record))
''' % (host.id, host.region, host.provider, host.datacenter_name, server_details, vpn_users_command)

    ssh = psi_ssh.SSH(host.ip_address, host.ssh_port, host.ssh_username, host.ssh_password, host.ssh_host_key)

    psi_count_users_host_path = '/usr/local/sbin/psi_count_users'

    file = tempfile.NamedTemporaryFile(delete=False)
    file.write(script)
    file.close()
    ssh.put_file(file.name, psi_count_users_host_path)
    os.remove(file.name)

    ssh.exec_command('chmod +x %s' % (psi_count_users_host_path,))

    cron_file = '/etc/cron.d/psi-count-users'
    ssh.exec_command('echo "SHELL=/bin/sh" > %s;' % (cron_file,) +
                     'echo "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin" >> %s;' % (cron_file,) +
                     'echo "* * * * * root python %s" >> %s' % (psi_count_users_host_path, cron_file))

# Change the crontab file so that weekly jobs are not run on the same day across all servers
def change_weekly_crontab_runday(host, weekdaynum):
    if weekdaynum == None:
        weekdaynum = random.randint(1, 7)
    if 1 <= weekdaynum <= 7:
        cmd = "sed -i 's/^.*weekly.*$/47 6    * * " +str(weekdaynum)+ "\troot\ttest -x \/usr\/sbin\/anacron || ( cd \/ \&\& run-parts --report \/etc\/cron.weekly )/' /etc/crontab"
        ssh = psi_ssh.SSH(
                            host.ip_address, host.ssh_port,
                            host.ssh_username, host.ssh_password,
                            host.ssh_host_key)
        ssh.exec_command(cmd)
        ssh.close()
