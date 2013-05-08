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

import string
import random
import time
import json

from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
from libcloud.compute.base import NodeImage
from libcloud.compute.drivers.elasticstack import ElasticStackNodeSize
import libcloud.security

import psi_ssh
import psi_utils

SSHInfo = psi_utils.recordtype('SSHInfo', 
                               'ip_address port username password public_key', 
                               logs=False)

class ElasticHosts(object):
    '''
    Interface for interacting with ElasticHosts resources.
    '''
    
    def __init__(self, verbose=True):
        self._verbose = verbose

        # Libcloud needs to be told where the CA certs can be found.
        # It's possible to disable this check, but that's a bad idea. 
        # The cacerts.pem file should be updated something like weekly.
        # For more info, see: 
        # http://wiki.apache.org/incubator/LibcloudSSL
        libcloud.security.CA_CERTS_PATH.append('./linode/cloud-cacerts.pem')
        
    def _print(self, string, newline=True):
        if not self._verbose: return
        if newline:
            print string
        else:
            print string,
        
    def _create_connection(self):
        Driver = get_driver(getattr(Provider, self._account.zone))
        self._driver = Driver(self._account.uuid, self._account.api_key)

    def launch_new_server(self, account, plugins):
        # Note that we're using the libcloud API in a fairly bastardized way.
        # We're not using the real API at all (we've found that it doesn't work),
        # but we're using the connection object, because it makes our code a lot
        # cleaner.

        self._account = account
        self._create_connection()
        
        self._print('Creating new ElasticHosts server in zone: %s...' % self._account.zone)
        
        # Determine the base drive size. We can then use this as the size for 
        # the new drive.
        self._print('Determining drive size...')
        resp = self._driver.connection.request(action='/drives/%s/info' 
                                                        % self._account.base_drive_id)
        drive_size = resp.object['size']
        self._print('Drive size: %dGB' % (drive_size/1024/1024/1024))
        
        random_name = ''.join([random.choice(string.letters + string.digits) for i in range(16)])
        self._print('Server/drive name: %s' % random_name)
        
        # Create a blank new drive of the appropriate size
        self._print('Creating blank drive...')
        resp = self._driver.connection.request(action='/drives/create', 
                                               method='POST', 
                                               data=json.dumps({'name': random_name,
                                                                'size': drive_size}))
        drive_id = resp.object['drive']
        
        # Start imaging the new drive with the base drive 
        self._print('Drive imaging start...')
        self._driver.connection.request(action='/drives/%s/image/%s' 
                                                % (drive_id, self._account.base_drive_id), 
                                        method='POST')
        
        # Imaging takes up to about 20 minutes, so we'll check and wait and repeat.
        # HACK: We have seen the imaging key be absent even though the imaging 
        # isn't finished. So we'll add a bit of a hack to check a few more times
        # before we accept it as finished. We're also going to make sure that 
        # the last % we saw was in the 90s. 
        done_check = 3
        last_imaging_value = ''
        while done_check > 0:
            resp = self._driver.connection.request(action='/drives/%s/info' % drive_id)
            if not resp.object.has_key('imaging'):
                if last_imaging_value.startswith('9') and len(last_imaging_value) == 3: # '99%'
                    done_check -= 1
                    self._print('Imaging might be done; checking again (%d)...' % done_check)
                else:
                    self._print('Imaging probably not done, but returning no progress; checking again...')
                continue
            self._print(resp.object['imaging'], newline=False)
            last_imaging_value = resp.object['imaging']
            time.sleep(5)
        self._print('Drive imaging complete')
        
        # If we don't use a static IP, the server will get a fresh IP every time
        # it reboots (which is bad).
        self._print('Creating IP address...')
        resp = self._driver.connection.request(action='/resources/ip/create', 
                                               method='POST', 
                                               data=json.dumps({'name': random_name}))
        ip_address = resp.object['resource']
        self._print('IP address: %s' % ip_address)
        
        # The drive is ready, now create the server that uses it.
        self._print('Creating server...')
        resp = self._driver.connection.request(action='/servers/create/stopped', 
                                               method='POST',
                                               data=json.dumps({'ide:0:0':drive_id,
                                                                'name': random_name,
                                                                'cpu': self._account.cpu,
                                                                'mem': self._account.mem,
                                                                'nic:0:dhcp': ip_address,
                                                                # The rest of these settings are basically the defaults.
                                                                # ...But the create won't work without them.
                                                                'persistent': True,
                                                                'smp': 'auto',
                                                                'boot': 'ide:0:0',
                                                                'nic:0:model': 'e1000',
                                                                }))
        server_id = resp.object['server']

        # Start the new server
        self._print('Starting server...')
        resp = self._driver.connection.request(action='/servers/%s/start' % server_id, 
                                               method='POST')

        ssh_info = SSHInfo(ip_address, self._account.base_ssh_port, 
                           self._account.root_username, self._account.base_root_password,
                           self._account.base_host_public_key)
        
        # Change hostname
        self._print('Changing hostname...')
        self._change_hostname(ssh_info, random_name, reboot=False)
        
        # Change credentials
        self._print('Refreshing credentials...')
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        new_pub_key = self._refresh_credentials(ssh_info, new_root_password, new_stats_password)
        new_pub_key = ' '.join(new_pub_key.split(' ')[:2])
        
        ssh_info.password = new_root_password
        ssh_info.public_key = new_pub_key
        
        # Reboot
        self._print('Rebooting server...')
        self._reboot(ssh_info)
        
        self._print('Complete')
        
        return (random_name, None, str(server_id), ip_address,
                ssh_info.port, ssh_info.username, new_root_password,
                ' '.join(new_pub_key.split(' ')[:2]),
                self._account.stats_username, new_stats_password,
                account.zone)
    

    def _refresh_credentials(self, ssh_info, new_root_password, new_stats_password):
        ssh = psi_ssh.make_ssh_session(*ssh_info, verbose=self._verbose)
        ssh.exec_command('echo "%s:%s" | chpasswd' % (self._account.root_username, new_root_password,))
        ssh.exec_command('echo "%s:%s" | chpasswd' % (self._account.stats_username, new_stats_password))
        ssh.exec_command('rm /etc/ssh/ssh_host_*')
        ssh.exec_command('rm -rf /root/.ssh')
        ssh.exec_command('dpkg-reconfigure openssh-server')
        return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')

    
    def _change_hostname(self, ssh_info, random_name, reboot):
        '''
        Changes the hostname of the host (ElasticHosts "server") at ip_address.
        Note that the name change won't actually take place until the server is 
        rebooted.
        '''
        # Note: using base image credentials; call before changing credentials
        ssh = psi_ssh.make_ssh_session(*ssh_info, verbose=self._verbose)
        ssh.exec_command('echo "%s" > /etc/hostname' % random_name).strip()
        
        if reboot: self._reboot(ssh_info)
    
    
    def _reboot(self, ssh_info):
        '''
        Reboots the server and waits until it is available again.
        This function SSHes into the server and issues a reboot command.
        Alternatively, we could use the ElasticHosts API to do an ACPI reboot.
        '''
        ssh = psi_ssh.make_ssh_session(*ssh_info, verbose=self._verbose) 
        ssh.exec_command('reboot')
        ssh.close()
        
        # Try to connect again, retrying. When it succeeds, the reboot will be done.
        
        # Wait a little to make sure we're not connecting *before* the reboot.
        time.sleep(5)
        
        ssh = psi_ssh.make_ssh_session(*ssh_info, verbose=self._verbose) 
        ssh.close()
        
