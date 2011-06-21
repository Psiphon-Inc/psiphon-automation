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
import sys
import textwrap
import tempfile

import psi_ssh

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    psi_db.set_db_root(psi_data_config.DATA_ROOT)

    
#==============================================================================

# We use an echo command over ssh to generate this file on the remote server to avoid
# leaving IP Addresses on disk
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

    return 'echo "%s" > /etc/xl2tpd/xl2tpd%d.conf' % (file_contents.replace('\n', '\\\n'), server_index)

def make_xl2tpd_options_file_command():
    file_contents = textwrap.dedent('''
        ipcp-accept-local
        ipcp-accept-remote
        ms-dns 8.8.8.8
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
        
    return 'echo "%s" > /etc/ppp/options.xl2tpd' % (file_contents.replace('\n', '\\\n'),)
    
def make_xl2tpd_chap_secrets_file_command():
    file_contents = '*   *   password    *'
    return 'echo "%s" > /etc/ppp/chap-secrets' % (file_contents.replace('\n', '\\\n'),)
    
# This file is written to disk then copied to the remote server.  We had problems echoing it out
# to a file in an ssh command, probably because of all the special characters.  It's OK to write this
# to disk locally, because there isn't any secret info (like IP Addresses) here.
def make_xl2tpd_initd_file_contents(server_count):
    # TODO: use textwrap.dedent and try initial_indent to line up the repeated segments
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
        start-stop-daemon --start --quiet --pidfile $PIDFILE.%d --exec $DAEMON -- -c /etc/xl2tpd/xl2tpd%d.conf -p $PIDFILE.%d -C /var/run/xl2tpd1/l2tp-control $DAEMON_OPTS
        echo "$NAME.%d."
''' % (i,i,i,i,i,i) for i in range(server_count)]) + '''
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

    return 'echo "%s" >> /etc/ipsec.conf' % (file_contents.replace('\n', '\\\n'),)
    
def make_ipsec_secrets_file_command():
    return 'echo "" > /etc/ipsec.secrets'
    
    
#==============================================================================
    
if __name__ == "__main__":

    # Install each server that only has partially filled-in data.
    # We don't want to do anything on hosts that are fully configured, 
    # and for partially configured hosts we need to completely reconfigure
    # all files because we use a counter in the xl2tpd config files that is not
    # directly tied to the IP Address in the database.
    # So we find the hosts that have some unconfigured servers and then
    # install a complete configuration on those hosts.

    unconfigured_servers = [server for server in psi_db.get_servers()
                            if server.Web_Server_Secret is None or
                            server.Web_Server_Certificate is None or
                            server.Web_Server_Private_Key is None]
    
    unconfigured_host_ids = set([server.Host_ID for server in unconfigured_servers])

    unconfigured_hosts = [host for host in psi_db.get_hosts() if host.Host_ID in unconfigured_host_ids]
    
    for host in unconfigured_hosts:
        ssh = psi_ssh.SSH(
                host.IP_Address, host.SSH_Username,
                host.SSH_Password, host.SSH_Host_Key)
                
        host_servers = [server for server in psi_db.get_servers() if server.Host_ID == host.Host_ID]

        # Generate and upload ipsec config files
        file = tempfile.NamedTemporaryFile(delete=False)
        file.write(make_ipsec_config_file_base_contents(len(host_servers)))
        file.close()
        ssh.put_file(file.name, '/etc/ipsec.conf')
        os.unlink(file.name)

        for index, server in enumerate(host_servers):
            ssh.exec_command(make_ipsec_config_file_connection_command(index, server.IP_Address))
        
        ssh.exec_command(make_ipsec_secrets_file_command())
        
        # Generate and upload xl2tpd config files and init script
        for index, server in enumerate(host_servers):
            ssh.exec_command(make_xl2tpd_config_file_command(index, server.IP_Address))
        
        ssh.exec_command(make_xl2tpd_options_file_command())
        
        ssh.exec_command(make_xl2tpd_chap_secrets_file_command())
        
        file = tempfile.NamedTemporaryFile(delete=False)
        file.write(make_xl2tpd_initd_file_contents(len(host_servers)))
        file.close()
        ssh.put_file(file.name, '/etc/init.d/xl2tpd')
        os.unlink(file.name)
    
        # Restart the IPSec and xl2tpd services
        ssh.exec_command('/etc/init.d/ipsec restart')
        ssh.exec_command('/etc/init.d/xl2tpd restart')
        
        
        
        