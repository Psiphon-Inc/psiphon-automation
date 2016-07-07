#!/usr/bin/python
#
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
#

import re
import tempfile
import os
import posixpath
import sys
import textwrap
import json
import psi_ssh
import psi_routes
import psi_ops_install
from multiprocessing.pool import ThreadPool
from functools import wraps

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Server')))
import psi_config


#==== Legacy Deploy File Locations  ===========================================

BUILDS_ROOT = os.path.join('.', 'Builds')

SOURCE_FILES = [
    (('Automation',),
     ['psi_ops.py',
      'psi_ops_discovery.py',
      'psi_ops_cms.py',
      'psi_utils.py'
     ]),

    (('Server',),
     ['psi_config.py',
      'psi_psk.py',
      'psi_web.py',
      'psi_auth.py',
      'psi_geoip.py',
      'pam.py',
      'psi-check-services',
      'psi_web_patch.py'
     ]),

    (('go',  'meek-server'),
     ['meek-server.go'
     ]),

    (('go', 'utils', 'crypto'),
     ['crypto.go'
     ])
]

#==== TCS Configuration =======================================================

TCS_PSIPHOND_CONFIG_FILE_NAME = '/opt/psiphond/psiphond.config'
TCS_PSIPHOND_LOG_FILE_NAME = '/opt/psiphond/psiphond.config'
TCS_TRAFFIC_RULES_FILE_NAME = '/opt/psiphond/traffic-rules.config'
TCS_PSINET_FILE_NAME = '/opt/psiphond/psinet.json'
# TODO-TCS: finalize GeoIP filename
TCS_GEOIP_DATABASE_FILE_NAME = '/usr/local/share/GeoIP/...'

TCS_DOCKER_WEB_SERVER_PORT = 3000
TCS_SSH_DOCKER_PORT = 3001
TCS_OSSH_DOCKER_PORT = 3002
TCS_FRONTED_MEEK_DOCKER_PORT = 3003
TCS_UNFRONTED_MEEK_DOCKER_PORT = 3004
TCS_FRONTED_MEEK_HTTP_DOCKER_PORT = 3005
TCS_UNFRONTED_MEEK_HTTPS_DOCKER_PORT = 3006


#==============================================================================


def retry_decorator_returning_exception(function):
    @wraps(function)
    def wrapper(*args, **kwds):
        for i in range(5):
            try:
                function(*args, **kwds)
                return None
            except Exception as e:
                print str(e)
        return e
    return wrapper


def run_in_parallel(thread_pool_size, function, arguments):
    pool = ThreadPool(thread_pool_size)
    results = pool.map(function, arguments)
    for result in results:
        if result:
            raise result


def deploy_implementation(host, servers, discovery_strategy_value_hmac_key, plugins, TCS_psiphond_config_values):

    print 'deploy implementation to host %s%s...' % (host.id, " (TCS) " if host.is_TCS else "", )

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    if host.is_TCS:
        deploy_TCS_implementation(ssh, host, servers, TCS_psiphond_config_values)
    else:
        deploy_legacy_implementation(ssh, host, discovery_strategy_value_hmac_key, plugins)

    ssh.close()


def deploy_legacy_implementation(ssh, host, discovery_strategy_value_hmac_key, plugins):

    # Copy server source code

    for (dir, filenames) in SOURCE_FILES:
        ssh.exec_command('mkdir -p %s' % (
                posixpath.join(psi_config.HOST_SOURCE_ROOT, *dir),))
        for filename in filenames:
            ssh.put_file(os.path.join(os.path.abspath('..'), *(dir + (filename,))),
                         posixpath.join(psi_config.HOST_SOURCE_ROOT, *(dir + (filename,))))
        ssh.exec_command('rm %s' % (posixpath.join(psi_config.HOST_SOURCE_ROOT, *(dir + ('*.pyc',))),))

    ssh.exec_command('chmod +x %s' % (
            posixpath.join(psi_config.HOST_SOURCE_ROOT, 'Server', 'psi_web.py'),))

    ssh.exec_command('chmod +x %s' % (
            posixpath.join(psi_config.HOST_SOURCE_ROOT, 'Server', 'psi_auth.py'),))

    ssh.exec_command('chmod +x %s' % (
            posixpath.join(psi_config.HOST_SOURCE_ROOT, 'Server', 'psi-check-services'),))

    remote_ip_down_file_path = posixpath.join(psi_config.HOST_IP_DOWN_DIR, 'psi-ip-down')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-ip-down'),
                 remote_ip_down_file_path)
    ssh.exec_command('chmod +x %s' % (remote_ip_down_file_path,))

    remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'psiphonv')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'psi-init'),
                 remote_init_file_path)
    ssh.exec_command('chmod +x %s' % (remote_init_file_path,))
    ssh.exec_command('update-rc.d %s defaults' % ('psiphonv',))

    # Patch PAM config to use psi_auth.py
    ssh.exec_command('grep psi_auth.py /etc/pam.d/sshd || sed -i \'s/@include common-auth/auth       sufficient   pam_exec.so expose_authtok seteuid quiet \\/opt\\/PsiphonV\\/Server\\/psi_auth.py\\n@include common-auth/\' /etc/pam.d/sshd')

    # Restart server after source code updated

    ssh.exec_command('%s restart' % (remote_init_file_path,))

    # Set up meek-server if enabled for this host

    if host.meek_server_port:
        ssh.exec_command('mkdir -p /opt/gocode/src/bitbucket.org/psiphon/psiphon-circumvention-system/')
        ssh.exec_command('ln -s %s /opt/gocode/src/bitbucket.org/psiphon/psiphon-circumvention-system/' % (
                posixpath.join(psi_config.HOST_SOURCE_ROOT, 'go'),))
        ssh.exec_command('cd %s && GOBIN=. GOPATH=/opt/gocode/ go get' % (
                posixpath.join(psi_config.HOST_SOURCE_ROOT, 'go', 'meek-server'),))

        meek_remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'meek-server')
        ssh.put_file(os.path.join(os.path.abspath('..'), 'go', 'meek-server', 'meek-server-init'),
                meek_remote_init_file_path)
        ssh.exec_command('chmod +x %s' % (meek_remote_init_file_path,))
        ssh.exec_command('update-rc.d %s defaults' % ('meek-server',))

        ssh.exec_command('echo \'%s\' > /etc/meek-server.json' % (
                json.dumps({'Port': int(host.meek_server_port),
                            'ListenTLS': True if int(host.meek_server_port) == 443 else False,
                            'Fronted': True if host.meek_server_fronting_domain else False,
                            'CookiePrivateKeyBase64': host.meek_cookie_encryption_private_key,
                            'ObfuscatedKeyword': host.meek_server_obfuscated_key,
                            'GeoIpServicePort': psi_config.GEOIP_SERVICE_PORT,
                            'ClientIpAddressStrategyValueHmacKey': discovery_strategy_value_hmac_key}),))

        ssh.exec_command('%s restart' % (meek_remote_init_file_path,))

    # Install the cron job that calls psi-check-services

    cron_file = '/etc/cron.d/psi-check-services'
    ssh.exec_command('echo "SHELL=/bin/sh" > %s;' % (cron_file,) +
                     'echo "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin" >> %s;' % (cron_file,) +
                     'echo "*/5 * * * * root %s" >> %s' % (
            posixpath.join(psi_config.HOST_SOURCE_ROOT, 'Server', 'psi-check-services'), cron_file))

    # Copy the rate-limiting scripts

    remote_rate_limit_start_file_path = posixpath.join(psi_config.HOST_IP_UP_DIR, 'rate-limit')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'rate-limit-start'),
                 remote_rate_limit_start_file_path)
    ssh.exec_command('chmod +x %s' % (remote_rate_limit_start_file_path,))
    remote_rate_limit_end_file_path = posixpath.join(psi_config.HOST_IP_DOWN_DIR, 'rate-limit')
    ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'rate-limit-end'),
                 remote_rate_limit_end_file_path)
    ssh.exec_command('chmod +x %s' % (remote_rate_limit_end_file_path,))

    for plugin in plugins:
        if hasattr(plugin, 'deploy_implementation'):
            plugin.deploy_implementation(ssh)


def deploy_TCS_implementation(ssh, host, servers, TCS_psiphond_config_values):

    # Limitation: only one server per host currently implemented
    assert(len(servers) == 1)
    server = servers[0]

    # Upload psiphond.config

    put_file_with_content(
        ssh,
        make_psiphond_config(host, server, TCS_psiphond_config_values),
        psi_config.TCS_PSIPHOND_CONFIG_FILE_NAME)

    # TODO-TCS: pave systemd unit environment file(s), enable unit


def make_psiphond_config(host, server, TCS_psiphond_config_values):

    # TODO-TCS: support multiple meek listeners

    config = {}

    config['LogLevel'] = 'info'

    config['LogFilename'] = TCS_PSIPHOND_LOG_FILE_NAME

    config['Fail2BanFormat'] = 'Authentication failure for psiphon-client from %s'

    config['DiscoveryValueHMACKey'] = TCS_psiphond_config_values['DiscoveryValueHMACKey']

    config['GeoIPDatabaseFilename'] = TCS_GEOIP_DATABASE_FILE_NAME

    config['PsinetDatabaseFilename'] = TCS_PSINET_FILE_NAME

    config['TrafficRulesFilename'] = TCS_TRAFFIC_RULES_FILE_NAME

    config['LoadMonitorPeriodSeconds'] = 300

    config['UDPInterceptUdpgwServerAddress'] = '127.0.0.1:7300'
    # TODO-TCS: remove this item once psiphond uses local host DNS server
    config['UDPForwardDNSServerAddress'] = '8.8.8.8:53'

    config['HostID'] = host.id

    config['ServerIPAddress'] = server.ip_address

    config['WebServerPort'] = TCS_DOCKER_WEB_SERVER_PORT
    config['WebServerSecret'] = server.web_server_secret
    config['WebServerCertificate'] = server.web_server_certificate
    config['WebServerPrivateKey'] = server.web_server_private_key

    config['SSHPrivateKey'] = server.TCS_ssh_private_key
    config['SSHServerVersion'] = TCS_psiphond_config_values['SSHServerVersion']
    config['SSHUserName'] = server.ssh_username
    config['SSHPassword'] = server.ssh_password

    if server.capabilities['OSSH'] or server.capabilities['FRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK']:
        config['ObfuscatedSSHKey'] = server.ssh_obfuscated_key

    if server.capabilities['FRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK']:
        config['MeekCookieEncryptionPrivateKey'] = host.meek_cookie_encryption_private_key
        config['MeekObfuscatedKey'] = host.meek_server_obfuscated_key
        config['MeekCertificateCommonName'] = TCS_psiphond_config_values['MeekCertificateCommonName']
        config['MeekProhibitedHeaders'] = TCS_psiphond_config_values['MeekProhibitedHeaders']
        config['MeekProxyForwardedForHeaders'] = TCS_psiphond_config_values['MeekProxyForwardedForHeaders']

    config['TunnelProtocolPorts'] = {}

    TCS_protocols = [
        ('SSH', TCS_SSH_DOCKER_PORT),
        ('OSSH', TCS_OSSH_DOCKER_PORT),
        ('FRONTED-MEEK', TCS_FRONTED_MEEK_DOCKER_PORT),
        ('UNFRONTED-MEEK', TCS_UNFRONTED_MEEK_DOCKER_PORT),
        ('FRONTED-MEEK-HTTP', TCS_FRONTED_MEEK_HTTP_DOCKER_PORT),
        ('UNFRONTED-MEEK-HTTPS', TCS_UNFRONTED_MEEK_HTTPS_DOCKER_PORT)
    ]

    # gets the Docker ports
    config['TunnelProtocolPorts'] = get_supported_protocol_ports(host, server, False)

    return json.dumps(config)


# get_supported_protocol_ports returns a map of protocol name to protocol
# port with entries for each protocol supported on the host/server.
# Specify external_ports=True to get public ports, or external_ports=False
# to get Docker ports.
def get_supported_protocol_ports(host, server, external_ports=True):

    TCS_protocols = [
        ('SSH', TCS_SSH_DOCKER_PORT),
        ('OSSH', TCS_OSSH_DOCKER_PORT),
        ('FRONTED-MEEK', TCS_FRONTED_MEEK_DOCKER_PORT),
        ('UNFRONTED-MEEK', TCS_UNFRONTED_MEEK_DOCKER_PORT),
        ('FRONTED-MEEK-HTTP', TCS_FRONTED_MEEK_HTTP_DOCKER_PORT),
        ('UNFRONTED-MEEK-HTTPS', TCS_UNFRONTED_MEEK_HTTPS_DOCKER_PORT)
    ]

    supported_protocol_ports = {}

    # The support logic encodes special case rules. Some protocols
    # don't have corresponding server record capabilities or ports,
    # for example.

    for (protocol, docker_port) in TCS_protocols:
        if protocol == 'SSH' and server.capabilities[protocol]:
                supported_protocol_ports[protocol] = int(server.ssh_port) if external_ports else docker_port

        if protocol == 'OSSH' and server.capabilities[protocol]:
                supported_protocol_ports[protocol] = int(server.ssh_obfuscated_port) if external_ports else docker_port

        if protocol == 'FRONTED-MEEK' and server.capabilities[protocol]:
                supported_protocol_ports[protocol] = 443 if external_ports else docker_port

        if protocol == 'UNFRONTED-MEEK' and server.capabilities[protocol] and not int(host.meek_server_port) == 443:
                supported_protocol_ports[protocol] = int(host.meek_server_port) if external_ports else docker_port

        if protocol == 'FRONTED-MEEK-HTTP' and server.capabilities['FRONTED-MEEK'] and host.alternate_meek_server_fronting_hosts:
                supported_protocol_ports[protocol] = 80 if external_ports else docker_port

        if protocol == 'UNFRONTED-MEEK-HTTPS' and server.capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 443:
                supported_protocol_ports[protocol] = int(host.meek_server_port) if external_ports else docker_port

    return supported_protocol_ports


def deploy_implementation_to_hosts(hosts, discovery_strategy_value_hmac_key, plugins, TCS_psiphond_config_values):

    @retry_decorator_returning_exception
    def do_deploy_implementation(host):
        try:
            deploy_implementation(host, discovery_strategy_value_hmac_key, plugins, TCS_psiphond_config_values)
        except:
            print 'Error deploying implementation to host %s' % (host.id,)
            raise
        host.log('deploy implementation')

    run_in_parallel(20, do_deploy_implementation, hosts)


def deploy_data(host, host_data, TCS_traffic_rules_set):

    print 'deploy data to host %s%s...' % (host.id, " (TCS) " if host.is_TCS else "", )

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    if host.is_TCS:
        deploy_TCS_data(ssh, host, host_data, TCS_traffic_rules_set)
    else:
        deploy_legacy_data(ssh, host, host_data)

    ssh.close()


def deploy_legacy_data(ssh, host, host_data):

    # Stop server, if running, before replacing data file (command may fail)
    # Disable restarting the server through psi-check-services first

    ssh.exec_command('touch %s' % (psi_config.HOST_SERVER_STOPPED_LOCK_FILE,))
    remote_init_file_path = posixpath.join(psi_config.HOST_INIT_DIR, 'psiphonv')
    ssh.exec_command('%s stop' % (remote_init_file_path,))

    # Copy data file
    # We upload a compartmentalized version of the master file
    # containing only the propagation channel IDs and confidential server
    # information required by each host.

    file = tempfile.NamedTemporaryFile(delete=False)
    try:
        file.write(host_data)
        file.close()
        ssh.exec_command('mkdir -p %s' % (
                posixpath.split(psi_config.DATA_FILE_NAME)[0],))
        ssh.put_file(file.name, psi_config.DATA_FILE_NAME)
    finally:
        try:
            os.remove(file.name)
        except:
            pass

    # Restart server after data file updated

    ssh.exec_command('%s restart' % (remote_init_file_path,))

    # Allow psi-check-services to restart the server now that data has been successfully copied
    # and the server is running again

    ssh.exec_command('rm %s' % (psi_config.HOST_SERVER_STOPPED_LOCK_FILE,))


def deploy_TCS_data(ssh, host, host_data, TCS_traffic_rules_set):

    # Upload psinet file
    # We upload a compartmentalized version of the master file

    put_file_with_content(ssh, host_data, TCS_PSINET_FILE_NAME)

    # Upload traffic rules file

    put_file_with_content(ssh, TCS_traffic_rules_set, TCS_TRAFFIC_RULES_FILE_NAME)

    ssh.exec_command('systemctl kill --signal=USR1 psiphond')


def put_file_with_content(ssh, content, destination_path):

    # TODO-TCS: more robust to write to remote temp file and
    # rename only after successfully uploaded?

    file = tempfile.NamedTemporaryFile(delete=False)
    try:
        file.write(content)
        file.close()
        ssh.put_file(file.name, destination_path)
    finally:
        try:
            os.remove(file.name)
        except:
            pass


def deploy_data_to_hosts(hosts, data_generator, TCS_traffic_rules_set):

    @retry_decorator_returning_exception
    def do_deploy_data(host_and_data_generator):
        host = host_and_data_generator[0]
        host_data = host_and_data_generator[1](host.id)
        try:
            deploy_data(host, host_data, TCS_traffic_rules_set)
        except:
            print 'Error deploying data to host %s' % (host.id,)
            raise

    run_in_parallel(40, do_deploy_data, [(host, data_generator) for host in hosts])


def deploy_build(host, build_filename):

    if host.is_TCS:
        # This is obsolete
        return

    print 'deploy %s build to host %s...' % (build_filename, host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    ssh.exec_command('mkdir -p %s' % (psi_config.UPGRADE_DOWNLOAD_PATH,))

    ssh.put_file(
        build_filename,
        posixpath.join(psi_config.UPGRADE_DOWNLOAD_PATH,
                       os.path.split(build_filename)[1]))

    ssh.close()


def deploy_build_to_hosts(hosts, build_filename):

    @retry_decorator_returning_exception
    def do_deploy_build(host):
        try:
            deploy_build(host, build_filename)
        except:
            print 'Error deploying build to host %s' % (host.id,)
            raise

    run_in_parallel(10, do_deploy_build, hosts)


def deploy_routes(host):

    if host.is_TCS:
        # This is obsolete
        return

    print 'deploy routes to host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)
    ssh.exec_command('mkdir -p %s' % (psi_config.ROUTES_PATH,))

    target_filename = posixpath.join(
                            psi_config.ROUTES_PATH,
                            os.path.split(psi_routes.GEO_ROUTES_ARCHIVE_PATH)[1])

    ssh.put_file(psi_routes.GEO_ROUTES_ARCHIVE_PATH, target_filename)
    ssh.exec_command('tar xz -C %s -f %s' % (psi_config.ROUTES_PATH, target_filename))
    ssh.close()

    host.log('deploy routes')


def deploy_routes_to_hosts(hosts):

    @retry_decorator_returning_exception
    def do_deploy_routes(host):
        try:
            deploy_routes(host)
        except:
            print 'Error deploying routes to host %s' % (host.id,)
            raise

    run_in_parallel(10, do_deploy_routes, hosts)


def deploy_geoip_database_autoupdates(host):

    geo_ip_config_file = 'GeoIP.conf'
    if os.path.isfile(geo_ip_config_file):

        print 'deploy geoip database autoupdates to host %s...' % (host.id)

        ssh = psi_ssh.SSH(
                host.ip_address, host.ssh_port,
                host.ssh_username, host.ssh_password,
                host.ssh_host_key)

        ssh.put_file(os.path.join(os.path.abspath('.'), geo_ip_config_file),
                     posixpath.join('/usr/local/etc/', geo_ip_config_file))

        # Set up weekly updates
        cron_filename = '/etc/cron.weekly/update-geoip-db'

        cron_file_contents = ''

        # For TCS, use hot reload and don't restart service
        if host.is_TCS:

            cron_file_contents = '''#!/bin/sh

/usr/local/bin/geoipupdate
systemctl kill --signal=USR1 psiphond'''

        else:

        cron_file_contents = '''#!/bin/sh

/usr/local/bin/geoipupdate
%s restart''' % (posixpath.join(psi_config.HOST_INIT_DIR, 'psiphonv'),)

        ssh.exec_command('echo "%s" > %s' % (cron_file_contents, cron_filename))
        ssh.exec_command('chmod +x %s' % (cron_filename,))

        # Run the first update
        ssh.exec_command(cron_filename)
        ssh.close()

        host.log('deploy geoip autoupdates')


def deploy_geoip_database_autoupdates_to_hosts(hosts):

    @retry_decorator_returning_exception
    def do_deploy_geoip_database_autoupdates(host):
        try:
            deploy_geoip_database_autoupdates(host)
        except:
            print 'Error deploying geoip database autoupdates to host %s' % (host.id,)
            raise

    run_in_parallel(10, do_deploy_geoip_database_autoupdates, hosts)
