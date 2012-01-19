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
REGISTRY_IGNORE_VPN_VALUE = 'UserSkipVPN'


def __test_web_server(ip_address, web_server_port, web_server_secret):
    print 'Testing web server at %s...' % (ip_address,)
    get_request = 'https://%s:%s/handshake?propagation_channel_id=0&sponsor_id=0&client_version=1&server_secret=%s' % (ip_address, web_server_port, web_server_secret)
    # Reset the proxy settings (see comment below)
    urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
    response = urllib2.urlopen(get_request).read()
    return ('SSHPort: ' in response and
            'SSHUsername: ' in response and
            'SSHPassword: ' in response and
            'SSHHostKey: ' in response and
            'SSHObfuscatedPort: ' in response and
            'SSHObfuscatedKey: ' in response and
            'PSK: ' in response)


def __test_server(executable_path, mode, expected_egress_ip_addresses):
    # test:
    # - spawn client process, which starts the VPN
    # - sleep 5 seconds, which allows time to establish connection
    # - determine egress IP address and assert it matches host IP address
    # - post WM_CLOSE to gracefully shut down the client and its connection
    print 'Testing egress IP addresses %s in %s mode...' % (
            ','.join(expected_egress_ip_addresses), mode)

    try:
        reg_key = _winreg.OpenKey(REGISTRY_ROOT_KEY, REGISTRY_PRODUCT_KEY, 0, _winreg.KEY_ALL_ACCESS)
        ignore_vpn_value, ignore_vpn_type = _winreg.QueryValueEx(reg_key, REGISTRY_IGNORE_VPN_VALUE)
        _winreg.SetValueEx(reg_key, REGISTRY_IGNORE_VPN_VALUE, None, _winreg.REG_DWORD, 1 if mode == 'ssh' else 0)

        proc = subprocess.Popen([executable_path])
        time.sleep(15)
    
        # In VPN mode, all traffic is routed through the proxy. In SSH mode, the
        # urlib2 ProxyHandler picks up the Windows Internet Settings and uses the
        # HTTP Proxy that is set by the client.
        urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
        egress_ip_address = urllib2.urlopen(psi_ops_build.CHECK_IP_ADDRESS_URL).read().split('\n')[0]

        if egress_ip_address not in expected_egress_ip_addresses:
            raise Exception('egress is %s and expected egresses are %s' % (
                                egress_ip_address, ','.join(expected_egress_ip_addresses)))
    finally:
        _winreg.SetValueEx(reg_key, REGISTRY_IGNORE_VPN_VALUE, None, ignore_vpn_type, ignore_vpn_value)
        win32ui.FindWindow(None, psi_ops_build.APPLICATION_TITLE).PostMessage(win32con.WM_CLOSE)
        proc.wait()
            

def test_server(ip_address, web_server_port, web_server_secret, encoded_server_list, version,
                expected_egress_ip_addresses, test_web_server, test_vpn, test_ssh):
    results = {}
    
    if test_web_server:
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

    if test_vpn or test_ssh:
        executable_path = psi_ops_build.build_client('0', '0', None, encoded_server_list, version, True)
        
    if test_vpn:
        try:
            __test_server(executable_path, 'vpn', expected_egress_ip_addresses)
            results['VPN'] = 'PASS'
        except Exception as ex:
            results['VPN'] = 'FAIL: ' + str(ex)

    if test_ssh:
        try:
            __test_server(executable_path, 'ssh', expected_egress_ip_addresses)
            results['SSH'] = 'PASS'
        except Exception as ex:
            results['SSH'] = 'FAIL: ' + str(ex)
    
    return results

