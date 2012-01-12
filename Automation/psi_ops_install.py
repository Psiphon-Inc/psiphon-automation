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
from OpenSSL import crypto
import psi_ssh


#==== Configuration ============================================================

WEB_SERVER_SECRET_BYTE_LENGTH = 32
SERVER_ID_WORD_LENGTH = 3
SSL_CERTIFICATE_KEY_TYPE = crypto.TYPE_RSA
SSL_CERTIFICATE_KEY_SIZE = 2048
SSL_CERTIFICATE_DIGEST_TYPE = 'sha1'
SSL_CERTIFICATE_VALIDITY = (60*60*24*365*10) # 10 years


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

        }
        ''')

    ssh_service_section_template = textwrap.dedent('''
        service %s
        {
            id              = psiphon_ssh.%s
            bind            = %s
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
        service %s
        {
            id              = psiphon_ssh.obfuscated.%s
            bind            = %s
            socket_type     = stream
            protocol        = tcp
            wait            = no
            user            = root
            group           = nogroup
            server          = /usr/local/sbin/sshd
            server_args     = -i -4 -f /etc/ssh/sshd_config.obfuscated.psiphon_ssh_%s
        }
        ''')

    def service_name_for_port(port):
        if port == '22':
            return 'ssh'
        elif port == '80':
            return 'http'
        elif port == '465':
            return 'ssmtp'
        elif port == '587':
            return 'submission'
        elif port == '993':
            return 'imaps'
        elif port == '995':
            return 'pop3s'
        else:
            assert(False)
        
    service_sections = []
    for server in servers:
        if server.ssh_port is not None:
            service_sections.append(ssh_service_section_template %
                                (service_name_for_port(server.ssh_port), server.ip_address, server.ip_address, server.ip_address))
        if server.ssh_obfuscated_port is not None:
            service_sections.append(obfuscated_ssh_service_section_template %
                                (service_name_for_port(server.ssh_obfuscated_port), server.ip_address, server.ip_address, server.ip_address))
            
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
    key_pair = crypto.PKey()
    key_pair.generate_key(SSL_CERTIFICATE_KEY_TYPE, SSL_CERTIFICATE_KEY_SIZE)
    request = crypto.X509Req()
    #
    # TODO: generate a random, yet plausible DN
    #
    # subject = request.get_subject()
    # for (key, value) in subject_pairs.items():
    #    setattr(subject, key, value)
    #
    request.set_pubkey(key_pair)
    request.sign(key_pair, SSL_CERTIFICATE_DIGEST_TYPE)
    certificate = crypto.X509()
    certificate.set_version(2)
    certificate.set_serial_number(0)
    certificate.gmtime_adj_notBefore(0)
    certificate.gmtime_adj_notAfter(SSL_CERTIFICATE_VALIDITY)
    certificate.set_issuer(request.get_subject())
    certificate.set_subject(request.get_subject())
    certificate.set_pubkey(request.get_pubkey())
    certificate.sign(key_pair, SSL_CERTIFICATE_DIGEST_TYPE)
    return (crypto.dump_privatekey(crypto.FILETYPE_PEM, key_pair),
            crypto.dump_certificate(crypto.FILETYPE_PEM, certificate))


def install_host(host, servers, existing_server_ids):

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
            make_ipsec_config_file_connection_command(index, server.ip_address))

    ssh.exec_command(make_ipsec_secrets_file_command())

    #
    # Generate and upload xl2tpd config files and init script
    #

    # Stop the default instance first
    ssh.exec_command('/etc/init.d/xl2tpd stop')

    for index, server in enumerate(servers):
        ssh.exec_command(
            make_xl2tpd_config_file_command(index, server.ip_address))

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
    # Generate and upload sshd_config files and xinetd.conf
    #

    for server in servers:

        # Generate SSH credentials and SSH host key here because we need to create them
        # on the server and use them in the sshd_config files.
        # They will be updated in the database below.
        if (server.ssh_username is None
            or server.ssh_password is None):
            server.ssh_username = 'psiphon_ssh_%s' % (binascii.hexlify(os.urandom(8)),)
            server.ssh_password = binascii.hexlify(os.urandom(32))
        if server.ssh_host_key is None:
            ssh.exec_command('rm /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s' % (server.ip_address,))
            ssh.exec_command('ssh-keygen -t rsa -N \"\" -f /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s' % (server.ip_address,))
            try:
                # TODO: use temp dir?
                ssh.get_file('/etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s.pub' % (server.ip_address,), 'ssh_host_key')
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
        ssh.exec_command(make_sshd_config_file_command(server.ip_address, server.ssh_username))
        if server.ssh_obfuscated_port is not None:
            if server.ssh_obfuscated_key is None:
                server.ssh_obfuscated_key = binascii.hexlify(os.urandom(32))
            ssh.exec_command(make_obfuscated_sshd_config_file_command(server.ip_address, server.ssh_username,
                                                    server.ssh_obfuscated_port, server.ssh_obfuscated_key))
        # NOTE we do not write the ssh host key back to the server because it is generated
        #      on the server in the first place.

    ssh.exec_command(make_xinetd_config_file_command(servers))

    #
    # Restart the xinetd service
    #

    ssh.exec_command('/etc/init.d/xinetd restart')

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
            key_pem, cert_pem = generate_self_signed_certificate()
            server.web_server_private_key = ''.join(key_pem.split('\n')[1:-2])
            server.web_server_certificate = ''.join(cert_pem.split('\n')[1:-2])

    ## Deploy will upload web server source database data and client builds
    #psi_deploy.deploy(host)
    # NOTE: call psi_ops_deploy.deploy_host() to complete the install process

    
def install_firewall_rules(host):

    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    ssh.put_file('iptables.rules', '/etc/iptables.rules')
    ssh.exec_command('iptables-restore < /etc/iptables.rules')
    ssh.exec_command('/etc/init.d/fail2ban restart')
