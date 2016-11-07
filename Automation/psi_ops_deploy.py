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
from time import sleep

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

TCS_PSIPHOND_DOCKER_ENVIRONMENT_FILE_NAME = '/opt/psiphon/psiphond/config/psiphond.env'
TCS_PSIPHOND_CONFIG_FILE_NAME = '/opt/psiphon/psiphond/config/psiphond.config'
TCS_PSIPHOND_LOG_FILE_NAME = '/var/log/psiphond/psiphond.log'
TCS_PSIPHOND_PROCESS_PROFILE_OUTPUT_DIRECTORY_NAME = '/var/log/psiphond'
TCS_TRAFFIC_RULES_FILE_NAME = '/opt/psiphon/psiphond/config/traffic-rules.config'
TCS_PSINET_FILE_NAME = '/opt/psiphon/psiphond/data/psinet.json'
TCS_GEOIP_CITY_DATABASE_FILE_NAME = '/usr/local/share/GeoIP/GeoIP2-City.mmdb'
TCS_GEOIP_ISP_DATABASE_FILE_NAME = '/usr/local/share/GeoIP/GeoIP2-ISP.mmdb'

TCS_DOCKER_WEB_SERVER_PORT = 1025
TCS_SSH_DOCKER_PORT = 1026
TCS_OSSH_DOCKER_PORT = 1027
TCS_FRONTED_MEEK_OSSH_DOCKER_PORT = 1028
TCS_UNFRONTED_MEEK_OSSH_DOCKER_PORT = 1029
TCS_FRONTED_MEEK_HTTP_OSSH_DOCKER_PORT = 1030
TCS_UNFRONTED_MEEK_HTTPS_OSSH_DOCKER_PORT = 1031

TCS_PSIPHOND_HOT_RELOAD_SIGNAL_COMMAND = 'systemctl kill --signal=USR1 psiphond'
TCS_PSIPHOND_STOP_ESTABLISHING_TUNNELS_SIGNAL_COMMAND = 'systemctl kill --signal=TSTP psiphond'
TCS_PSIPHOND_RESUME_ESTABLISHING_TUNNELS_SIGNAL_COMMAND = 'systemctl kill --signal=CONT psiphond'
TCS_PSIPHOND_START_COMMAND = '/opt/psiphon/psiphond_safe_start.sh'


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
        TCS_PSIPHOND_CONFIG_FILE_NAME)

    # Upload psiphond.env

    external_protocol_ports = get_supported_protocol_ports(host, server)
    docker_protocol_ports = get_supported_protocol_ports(host, server, external_ports=False)

    if server.capabilities['handshake']:
        external_protocol_ports['handshake'] = server.web_server_port
        docker_protocol_ports['handshake'] = TCS_DOCKER_WEB_SERVER_PORT

    port_mappings = ' '.join(
        ["-p %s:%s" % (external_port,docker_protocol_ports[protocol],) for (protocol, external_port) in external_protocol_ports.iteritems()])

    psiphond_env_content = '''
DOCKER_CONTENT_TRUST=1

CONTAINER_TAG=production
CONTAINER_PORT_STRING="%s"
CONTAINER_VOLUME_STRING="-v /opt/psiphon/psiphond/config:/opt/psiphon/psiphond/config -v /opt/psiphon/psiphond/data:/opt/psiphon/psiphond/data -v /var/log/psiphond:/var/log/psiphond -v /usr/local/share/GeoIP:/usr/local/share/GeoIP"
CONTAINER_ULIMIT_STRING="--ulimit nofile=1000000:1000000"
CONTAINER_SYSCTL_STRING="--sysctl 'net.ipv4.ip_local_port_range=1100 65535'"
''' % (port_mappings,)

    put_file_with_content(
        ssh,
        psiphond_env_content,
        TCS_PSIPHOND_DOCKER_ENVIRONMENT_FILE_NAME)

    # Note: not invoking TCS_PSIPHOND_ENABLE_COMMAND here as psiphond expects
    # the psinet and traffic rules data to exist when it starts. The enable
    # is delayed until deploy_TCS_data.


def make_psiphond_config(host, server, TCS_psiphond_config_values):

    # Missing TCS_psiphond_config_values items throw KeyError. This is intended. Don't forget to configure these values.

    config = {}

    config['LogLevel'] = 'info'

    config['LogFilename'] = TCS_PSIPHOND_LOG_FILE_NAME

    config['ProcessProfileOutputDirectory'] = TCS_PSIPHOND_PROCESS_PROFILE_OUTPUT_DIRECTORY_NAME

    config['ProcessBlockProfileDurationSeconds'] = 30

    config['ProcessCPUProfileDurationSeconds'] = 30

    config['DiscoveryValueHMACKey'] = TCS_psiphond_config_values['DiscoveryValueHMACKey']

    config['GeoIPDatabaseFilenames'] = [TCS_GEOIP_CITY_DATABASE_FILE_NAME, TCS_GEOIP_ISP_DATABASE_FILE_NAME]

    config['PsinetDatabaseFilename'] = TCS_PSINET_FILE_NAME

    config['TrafficRulesFilename'] = TCS_TRAFFIC_RULES_FILE_NAME

    config['LoadMonitorPeriodSeconds'] = 60

    config['UDPInterceptUdpgwServerAddress'] = '127.0.0.1:7300'

    config['HostID'] = host.id

    config['ServerIPAddress'] = '0.0.0.0'

    config['WebServerPort'] = TCS_DOCKER_WEB_SERVER_PORT
    config['WebServerSecret'] = server.web_server_secret
    config['WebServerCertificate'] = server.web_server_certificate
    config['WebServerPrivateKey'] = server.web_server_private_key

    # Redirect tunneled web server requests to the containerized web server address
    config['WebServerPortForwardAddress'] = "%s:%d" % (server.ip_address, int(server.web_server_port))
    config['WebServerPortForwardRedirectAddress'] = "%s:%d" % ('127.0.0.1', TCS_DOCKER_WEB_SERVER_PORT)

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

    # gets the Docker ports
    config['TunnelProtocolPorts'] = get_supported_protocol_ports(host, server, external_ports=False)

    return json.dumps(config)


# get_supported_protocol_ports returns a map of protocol name to protocol
# port with entries for each protocol supported on the host/server.
# Optional keyword args:
# - external_ports=True (the default) to get public ports,
#   or external_ports=False to get Docker ports.
# - meek_ports=True (the default) to include meek protocols,
#   or meek_ports=False to exclude meek protocols.
def get_supported_protocol_ports(host, server, **kwargs):

    external_ports = kwargs['external_ports'] if 'external_ports' in kwargs else True
    meek_ports = kwargs['meek_ports'] if 'meek_ports' in kwargs else True

    TCS_protocols = [
        ('SSH', TCS_SSH_DOCKER_PORT),
        ('OSSH', TCS_OSSH_DOCKER_PORT)
    ]

    if meek_ports:
        TCS_protocols += [
            ('FRONTED-MEEK-OSSH', TCS_FRONTED_MEEK_OSSH_DOCKER_PORT),
            ('UNFRONTED-MEEK-OSSH', TCS_UNFRONTED_MEEK_OSSH_DOCKER_PORT),
            ('FRONTED-MEEK-HTTP-OSSH', TCS_FRONTED_MEEK_HTTP_OSSH_DOCKER_PORT),
            ('UNFRONTED-MEEK-HTTPS-OSSH', TCS_UNFRONTED_MEEK_HTTPS_OSSH_DOCKER_PORT)
        ]

    supported_protocol_ports = {}

    # The support logic encodes special case rules. Some protocols
    # don't have corresponding server record capabilities or ports,
    # for example.

    for (protocol, docker_port) in TCS_protocols:
        if protocol == 'SSH' and server.capabilities['SSH']:
                supported_protocol_ports[protocol] = int(server.ssh_port) if external_ports else docker_port

        if protocol == 'OSSH' and server.capabilities['OSSH']:
                supported_protocol_ports[protocol] = int(server.ssh_obfuscated_port) if external_ports else docker_port

        if protocol == 'FRONTED-MEEK-OSSH' and server.capabilities['FRONTED-MEEK']:
                supported_protocol_ports[protocol] = 443 if external_ports else docker_port

        if protocol == 'UNFRONTED-MEEK-OSSH' and server.capabilities['UNFRONTED-MEEK'] and not int(host.meek_server_port) == 443:
                supported_protocol_ports[protocol] = int(host.meek_server_port) if external_ports else docker_port

        if protocol == 'FRONTED-MEEK-HTTP-OSSH' and server.capabilities['FRONTED-MEEK'] and host.alternate_meek_server_fronting_hosts:
                supported_protocol_ports[protocol] = 80 if external_ports else docker_port

        if protocol == 'UNFRONTED-MEEK-HTTPS-OSSH' and server.capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 443:
                supported_protocol_ports[protocol] = int(host.meek_server_port) if external_ports else docker_port

    return supported_protocol_ports


def deploy_implementation_to_hosts(hosts, discovery_strategy_value_hmac_key, plugins, TCS_psiphond_config_values):

    # TODO-TCS: stagger psiphond restarts. 15s delay in each batch has been OK for legacy meek updates.

    @retry_decorator_returning_exception
    def do_deploy_implementation(host):
        try:
            deploy_implementation(host, discovery_strategy_value_hmac_key, plugins, TCS_psiphond_config_values)
        except:
            print 'Error deploying implementation to host %s' % (host.id,)
            raise
        host.log('deploy implementation')

    run_in_parallel(20, do_deploy_implementation, hosts)
    restart_psiphond_service_on_hosts([host for host in hosts if host.is_TCS])


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

    ssh.exec_command(TCS_PSIPHOND_HOT_RELOAD_SIGNAL_COMMAND)

    # Enable and start psiphond service. It's disabled in the base image.
    # This is a one-time operation and otherwise has no effect on
    # subsequent invocations. Enable and start is done here and not
    # deploy_TCS_implementation since psiphond expects the psinet
    # and traffic rules to exist when it starts up.

    ssh.exec_command(TCS_PSIPHOND_START_COMMAND)


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

    # TCS data is not unique per host, so only generate it once
    TCS_data = None
    TCS_hosts = [host for host in hosts if host.is_TCS]
    if TCS_hosts:
        TCS_data = data_generator(TCS_hosts[0].id, True)

    @retry_decorator_returning_exception
    def do_deploy_data(host_and_data_generator):
        host = host_and_data_generator[0]
        host_data = TCS_data if host.is_TCS and TCS_data else host_and_data_generator[1](host.id, host.is_TCS)
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


def restart_psiphond_service_on_hosts(hosts):

  @retry_decorator_returning_exception
  def do_service_restart(host):
    sleep(30)

    if not host.is_TCS:
      return

    try:
      print("restarting 'psiphond.service' on host: %s" % host.id)

      ssh = psi_ssh.SSH(
                      host.ip_address, host.ssh_port,
                      host.ssh_username, host.ssh_password,
                      host.ssh_host_key)
      ssh.exec_command("systemctl restart psiphond.service")

    except Exception as e:
      print("Error restarting 'psiphond.service' on host %s: %r" % (host.id, e))
      raise
    host.log("restarted psiphond.service")

  run_in_parallel(
      min(len(hosts)/10, 30) if len(hosts) > 10 else 1,
      do_service_restart,
      hosts)


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

        cron_file_contents = None

        # For TCS, use hot reload and don't restart service
        if host.is_TCS:

            cron_file_contents = textwrap.dedent('''#!/bin/sh

                /usr/local/bin/geoipupdate
                %s''' % (TCS_PSIPHOND_HOT_RELOAD_SIGNAL_COMMAND,))

        else:

            cron_file_contents = textwrap.dedent('''#!/bin/sh

                    /usr/local/bin/geoipupdate
                    %s restart''' % (posixpath.join(psi_config.HOST_INIT_DIR, 'psiphonv'),))

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
