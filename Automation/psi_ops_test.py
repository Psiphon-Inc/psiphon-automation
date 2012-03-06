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

import urllib2
import subprocess
import time
from functools import wraps
try:
    import win32ui
    import win32con
    import _winreg
    REGISTRY_ROOT_KEY = _winreg.HKEY_CURRENT_USER
except ImportError as error:
    print error
    print 'NOTE: Running client tests will not be available.'

import psi_ops_build


REGISTRY_PRODUCT_KEY = 'SOFTWARE\\Psiphon3'
REGISTRY_TRANSPORT_VALUE = 'Transport'
REGISTRY_SPLIT_TUNNEL_VALUE = 'SplitTunnel'


def retry_on_exception_decorator(function):
    @wraps(function)
    def wrapper(*args, **kwds):
        for i in range(4):
            try:
                if i > 0:
                    time.sleep(20)
                return function(*args, **kwds)
            except Exception as e:
                print str(e)
                pass
        raise e
    return wrapper


@retry_on_exception_decorator
def __test_web_server(ip_address, web_server_port, web_server_secret):
    print 'Testing web server at %s...' % (ip_address,)
    get_request = 'https://%s:%s/handshake?propagation_channel_id=0&sponsor_id=0&client_version=1&server_secret=%s' % (ip_address, web_server_port, web_server_secret)
    # Reset the proxy settings (see comment below)
    urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
    response = urllib2.urlopen(get_request, timeout=10).read()
    return ('SSHPort: ' in response and
            'SSHUsername: ' in response and
            'SSHPassword: ' in response and
            'SSHHostKey: ' in response and
            'SSHObfuscatedPort: ' in response and
            'SSHObfuscatedKey: ' in response and
            'PSK: ' in response)


@retry_on_exception_decorator
def __test_server(executable_path, transport, expected_egress_ip_addresses):
    # test:
    # - spawn client process, which starts the VPN
    # - sleep 5 seconds, which allows time to establish connection
    # - determine egress IP address and assert it matches host IP address
    # - post WM_CLOSE to gracefully shut down the client and its connection
    print 'Testing egress IP addresses %s in %s mode...' % (
            ','.join(expected_egress_ip_addresses), transport)

    for split_tunnel_mode in [True, False]:

        # Split tunnelling is not implemented for VPN. No need to run the same test twice.
        if transport == 'VPN' and split_tunnel_mode:
            continue

        try:
            proc = None
            transport_value, transport_type = None, None
            split_tunnel_value, split_tunnel_type = None, None
            reg_key = _winreg.OpenKey(REGISTRY_ROOT_KEY, REGISTRY_PRODUCT_KEY, 0, _winreg.KEY_ALL_ACCESS)
            transport_value, transport_type = _winreg.QueryValueEx(reg_key, REGISTRY_TRANSPORT_VALUE)
            _winreg.SetValueEx(reg_key, REGISTRY_TRANSPORT_VALUE, None, _winreg.REG_SZ, transport)
            split_tunnel_value, split_tunnel_type = _winreg.QueryValueEx(reg_key, REGISTRY_SPLIT_TUNNEL_VALUE)
            # Enable split tunnel with registry setting
            _winreg.SetValueEx(reg_key, REGISTRY_SPLIT_TUNNEL_VALUE, None, _winreg.REG_DWORD, 1 if split_tunnel_mode else 0)
            
            proc = subprocess.Popen([executable_path])
            
            # VPN mode takes longer to establish a connection than other modes
            time.sleep(15 if transport == 'VPN' else 10)
        
            # In VPN mode, all traffic is routed through the proxy. In SSH mode, the
            # urlib2 ProxyHandler picks up the Windows Internet Settings and uses the
            # HTTP Proxy that is set by the client.
            urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
    
            # Get egress IP from web site in same GeoIP region; local split tunnel is not proxied
        
            egress_ip_address = urllib2.urlopen(psi_ops_build.CHECK_IP_ADDRESS_URL_LOCAL, timeout=30).read().split('\n')[0]
    
            is_proxied = (egress_ip_address in expected_egress_ip_addresses)
        
            if (transport == 'VPN' or not split_tunnel_mode) and not is_proxied:
                raise Exception('Local case/VPN/not split tunnel: egress is %s and expected egresses are %s' % (
                                    egress_ip_address, ','.join(expected_egress_ip_addresses)))
    
            if transport != 'VPN' and split_tunnel_mode and is_proxied:
                raise Exception('Local case/not VPN/split tunnel: egress is %s and expected egresses are %s' % (
                                    egress_ip_address, ','.join(expected_egress_ip_addresses)))
        
            # Get egress IP from web site in different GeoIP region; remote split tunnel is proxied
        
            egress_ip_address = urllib2.urlopen(psi_ops_build.CHECK_IP_ADDRESS_URL_REMOTE, timeout=30).read().split('\n')[0]
        
            is_proxied = (egress_ip_address in expected_egress_ip_addresses)
    
            if not is_proxied:
                raise Exception('Remote case: egress is %s and expected egresses are %s' % (
                                    egress_ip_address, ','.join(expected_egress_ip_addresses)))
            
        finally:
            if transport_type and transport_value:
                _winreg.SetValueEx(reg_key, REGISTRY_TRANSPORT_VALUE, None, transport_type, transport_value)
            if split_tunnel_value and split_tunnel_type:
                _winreg.SetValueEx(reg_key, REGISTRY_SPLIT_TUNNEL_VALUE, None, split_tunnel_type, split_tunnel_value)
            try:
                win32ui.FindWindow(None, psi_ops_build.APPLICATION_TITLE).PostMessage(win32con.WM_CLOSE)
            except Exception as e:
                print e
            if proc:
                proc.wait()
            

def test_server(ip_address, web_server_port, web_server_secret, encoded_server_list, version,
                expected_egress_ip_addresses, test_cases = None):

    if not test_cases:
        test_cases = ['handshake', 'VPN', 'SSH+', 'SSH']

    results = {}

    executable_path = None

    for test_case in test_cases:

        print 'test case %s...' % (test_case,)

        if test_case == 'handshake':
            try:
                result = __test_web_server(ip_address, web_server_port, web_server_secret)
                results['WEB'] = 'PASS' if result else 'FAIL'
            except Exception as ex:
                results['WEB'] = 'FAIL: ' + str(ex)
            try:
                result = __test_web_server(ip_address, '443', web_server_secret)
                results['443'] = 'PASS' if result else 'FAIL'
            except Exception as ex:
                results['443'] = 'FAIL: ' + str(ex)
        elif test_case in ['VPN', 'SSH+', 'SSH']:
            if not executable_path:
                executable_path = psi_ops_build.build_client('0', '0', None, encoded_server_list, version, True)
            try:
                __test_server(executable_path, test_case, expected_egress_ip_addresses)
                results[test_case] = 'PASS'
            except Exception as ex:
                results[test_case] = 'FAIL: ' + str(ex)
    
    return results
