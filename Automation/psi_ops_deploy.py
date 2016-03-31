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


#==== Deploy File Locations  ==================================================

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


def deploy_implementation(host, discovery_strategy_value_hmac_key, plugins):

    print 'deploy implementation to host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

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
            
    ssh.close()
    

def deploy_implementation_to_hosts(hosts, discovery_strategy_value_hmac_key, plugins):
    
    @retry_decorator_returning_exception
    def do_deploy_implementation(host):
        try:
            deploy_implementation(host, discovery_strategy_value_hmac_key, plugins)
        except:
            print 'Error deploying implementation to host %s' % (host.id,)
            raise
        host.log('deploy implementation')

    run_in_parallel(20, do_deploy_implementation, hosts)


def deploy_data(host, host_data):

    print 'deploy data to host %s...' % (host.id,)

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

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

    ssh.close()
    

def deploy_data_to_hosts(hosts, data_generator):

    @retry_decorator_returning_exception
    def do_deploy_data(host_and_data_generator):
        host = host_and_data_generator[0]
        host_data = host_and_data_generator[1](host.id)
        try:
            deploy_data(host, host_data)
        except:
            print 'Error deploying data to host %s' % (host.id,)
            raise
       
    run_in_parallel(40, do_deploy_data, [(host, data_generator) for host in hosts])

            
def deploy_build(host, build_filename):

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
