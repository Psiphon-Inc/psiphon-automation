#!/usr/bin/env python
#
# Copyright (c) 2017, Psiphon Inc.
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
import urllib3
import subprocess
import time
import copy
import json
import shlex

from functools import wraps

# Local service should be in same GeoIP region; local split tunnel will be in effect (not proxied)
# Remote service should be in different GeoIP region; remote split tunnel will be in effect (proxied)
CHECK_IP_ADDRESS_URL_LOCAL = ['http://ip.psitools.com', 'https://ip.psitools.com']
CHECK_IP_ADDRESS_URL_REMOTE = []

SOURCE_ROOT = os.path.join(os.path.abspath('.'), 'network-health', 'bin')
TUNNEL_CORE = os.path.join(SOURCE_ROOT, 'psiphon-tunnel-core')
CONFIG_FILE_NAME = os.path.join(SOURCE_ROOT, 'tunnel-core-config.config')



def load_default_tunnel_core():
    if not os.path.exists(TUNNEL_CORE):
        print "Psiphon tunnel core binary does not exist in path {0}, exiting".format(SOURCE_ROOT)
        sys.exit(1)
    return TUNNEL_CORE


def load_default_config():
    if not os.path.exists(CONFIG_FILE_NAME):
        print "Psiphon tunnel core config does not exist in path {0}, exiting".format(SOURCE_ROOT)
        sys.exit(1)
    return CONFIG_FILE_NAME


def load_server_config(server_id):
    return os.path.join(os.path.abspath('.'), 'network-health', 'conf', 
        'tunnel-core-config-{id}.config'.format(id=server_id.replace(' ', '_')))


def retry_on_exception_decorator(function):
    @wraps(function)
    def wrapper(*args, **kwds):
        for i in range(2):
            try:
                if i > 0:
                    time.sleep(20)
                return function(*args, **kwds)
            except Exception as e:
                print str(e)
                pass
        raise e
    return wrapper


class TunnelCoreConsoleRunner:
    def __init__(self, encoded_server_entry, propagation_channel_id = '0', sponsor_id = '0', client_platform = '', client_version = '0', split_tunnel_url_format = '', split_tunnel_signature_public_key = '', split_tunnel_dns_server = '', tunnel_core_binary = None, tunnel_core_config = None):
        self.proc = None
        self.http_proxy_port = 0
        self.socks_proxy_port = 0
        self.encoded_server_entry = encoded_server_entry
        self.propagation_channel_id = propagation_channel_id
        self.sponsor_id = sponsor_id
        self.client_platform = client_platform
        self.client_version = client_version
        self.split_tunnel_url_format = split_tunnel_url_format
        self.split_tunnel_signature_public_key = split_tunnel_signature_public_key
        self.split_tunnel_dns_server = split_tunnel_dns_server
        self.tunnel_core_binary = tunnel_core_binary
        self.tunnel_core_config = tunnel_core_config

    # Setup and create tunnel core config file.
    def _setup_tunnel_config(self, transport):
        config = {
            "TargetServerEntry": self.encoded_server_entry, # Single Test Server Parameter
            "TunnelProtocol": transport, # Single or group Test Protocol
            "PropagationChannelId" : self.propagation_channel_id, # Propagation Channel ID = "Testing"
            "SponsorId" : self.sponsor_id,
            "ClientPlatform" : self.client_platform,
            "ClientVersion" : self.client_version,
            "LocalHttpProxyPort" : self.http_proxy_port,
            "LocalSocksProxyPort" : self.socks_proxy_port,
            "UseIndistinguishableTLS": True,
            "TunnelPoolSize" : 1,
            "ConnectionWorkerPoolSize" : 1,
            "PortForwardFailureThreshold" : 5,
            "EmitDiagnosticNotices": True,
            "SplitTunnelRoutesUrlFormat" : self.split_tunnel_url_format,
            "SplitTunnelRoutesSignaturePublicKey" : self.split_tunnel_signature_public_key,
            "SplitTunnelDnsServer" : self.split_tunnel_dns_server
        }

        with open(self.tunnel_core_config, 'w+') as config_file:
            json.dump(config, config_file)

    # Use the config file and tunnel core it self to connect to server
    #TODO: Split Tunnel Mode need Change config file
    def connect_to_server(self, transport, split_tunnel_mode=False):

        if split_tunnel_mode == False:
            self.split_tunnel_url_format = ""
            self.split_tunnel_signature_public_key = ""
            self.split_tunnel_dns_server = ""

        self._setup_tunnel_config(transport)

        cmd = '"%s" --config "%s"' % (self.tunnel_core_binary, self.tunnel_core_config)

        self.proc = subprocess.Popen(shlex.split(cmd), stderr=subprocess.PIPE)

    def wait_for_connection(self):
        # If using tunnel-core
        # Read tunnel-core log file for connection message instead of sleep 25 second

        time.sleep(1)
        print 'Tunnel Core is connecting...'
        start_time = time.time()

        # Breaking this loop means the process sent EOF to stderr, or 'tunnels' tunnels were established
        while True:
            line = self.proc.stderr.readline()
            if not line:
                time.sleep(25)
                break

            line = json.loads(line)
            if line["data"].get("port"):
                if line.get("noticeType") == "ListeningSocksProxyPort":
                    self.socks_proxy_port = line["data"].get("port")
                elif line.get("noticeType") == "ListeningHttpProxyPort":
                    self.http_proxy_port = line["data"].get("port")
            if line["data"].get("count") != None:
                if line["noticeType"] == "Tunnels" and line["data"]["count"] == 1:
                    break

            if time.time() >= start_time + 25:
                # if the sleep time is 25 second, get out while loop and keep going
                print 'Not successfully connected after 25 second.'
                break

    def setup_proxy(self):
        return urllib3.ProxyManager("http://127.0.0.1:{http_port}".format(http_port=self.http_proxy_port))
        

    def stop_psiphon(self):
        try:
            self.proc.terminate()
            (stdin, stderr) = self.proc.communicate()
        except Exception as e:
            print e

        try:
            os.remove(self.tunnel_core_config)
            time.sleep(1)
        except Exception as e:
            print "Remove Config/Log File Failed" + str(e)


@retry_on_exception_decorator
def __test_server(runner, transport, expected_egress_ip_addresses, split_tunnel_mode):
    # test:
    # - spawn client process, which starts the VPN
    # - sleep 5 seconds, which allows time to establish connection
    # - determine egress IP address and assert it matches host IP address

    output = {}
    url = ''
    # Split tunnelling is not implemented for VPN.
    # Also, if there is no remote check, don't use split tunnel mode because we always want
    # to test at least one proxied case.

    print 'Testing egress IP addresses %s in %s mode (split tunnel %s)...' % (
            ','.join(expected_egress_ip_addresses), transport, 'ENABLED' if split_tunnel_mode else 'DISABLED')

    try:
        runner.connect_to_server(transport, split_tunnel_mode)
        
        runner.wait_for_connection()
        
        http_proxy = runner.setup_proxy()
        
        time.sleep(5)

        for url in CHECK_IP_ADDRESS_URL_LOCAL:
            # Get egress IP from web site in same GeoIP region; local split tunnel is not proxied
            
            print "Testing site: {0}".format(url)
            
            if url.startswith('https'):
                urllib3.disable_warnings()
            
            try:
                egress_ip_address = http_proxy.request('GET', url).data.split('\n')[0]

                is_proxied = (egress_ip_address in expected_egress_ip_addresses)
                
                if (transport == 'VPN' or not split_tunnel_mode) and not is_proxied:
                    raise Exception('Local case/VPN/not split tunnel: egress is %s and expected egresses are %s' % (
                                        egress_ip_address, ','.join(expected_egress_ip_addresses)))

                if transport != 'VPN' and split_tunnel_mode and is_proxied:
                    raise Exception('Local case/not VPN/split tunnel: egress is %s and expected egresses are ANYTHING OTHER THAN %s' % (
                                        egress_ip_address, ','.join(expected_egress_ip_addresses)))
                
                if url.startswith('https'):
                    output['HTTPS'] = 'PASS' if is_proxied else 'FAIL'
                else:
                    output['HTTP'] = 'PASS' if is_proxied else 'FAIL'
            
            except urllib3.exceptions.MaxRetryError:
                if url.startswith('https'):
                    output['HTTPS'] = 'FAIL'
                else:
                    output['HTTP'] = 'FAIL'
                continue
    
    except Exception as e:
        print "Could not tunnel to {0}: {1}".format(url, e)
        output['HTTP'] = output['HTTPS'] = 'FAIL'
    finally:
        print "Stopping tunnel"
        runner.stop_psiphon()
    
    return output



def test_server(server, host, encoded_server_entry, split_tunnel_url_format, 
                split_tunnel_signature_public_key, split_tunnel_dns_server, 
                expected_egress_ip_addresses, test_propagation_channel_id = '0', 
                test_sponsor_id = '0', client_platform = '', client_version = '',
                test_cases = None, executable_path = None, config_file = None):

    if executable_path is None:
        executable_path = load_default_tunnel_core()
    
    if config_file is None:
        config_file = load_default_config()
    
    capabilities = server.capabilities

    local_test_cases = copy.copy(test_cases) if test_cases else ['handshake', 'VPN', 'OSSH', 'SSH', 'UNFRONTED-MEEK-OSSH', 'UNFRONTED-MEEK-HTTPS-OSSH', 'UNFRONTED-MEEK-SESSION-TICKET-OSSH', 'FRONTED-MEEK-OSSH', 'FRONTED-MEEK-HTTP-OSSH']

    for test_case in copy.copy(local_test_cases):
        if ((test_case == 'VPN' # VPN requires handshake, SSH or SSH+
                and not (capabilities['handshake'] or capabilities['OSSH'] or capabilities['SSH'] or capabilities['FRONTED-MEEK'] or capabilities['UNFRONTED-MEEK']))
            or (test_case == 'UNFRONTED-MEEK-OSSH' and not (capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 80))
            or (test_case == 'UNFRONTED-MEEK-HTTPS-OSSH' and not (capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 443))
            or (test_case == 'UNFRONTED-MEEK-SESSION-TICKET-OSSH' and not (capabilities['UNFRONTED-MEEK-SESSION-TICKET']))
            or (test_case == 'FRONTED-MEEK-OSSH' and not (capabilities['FRONTED-MEEK']))
            or (test_case == 'FRONTED-MEEK-HTTP-OSSH' and not (capabilities['FRONTED-MEEK'] and host.alternate_meek_server_fronting_hosts))
            or (test_case in ['handshake', 'OSSH', 'SSH', 'VPN'] and not capabilities[test_case])
            or test_case == 'handshake' or test_case == 'VPN'):
            local_test_cases.remove(test_case)
    
    results = {}
    
    for test_case in local_test_cases:
        tunnel_core_runner = TunnelCoreConsoleRunner(
            encoded_server_entry, test_propagation_channel_id, test_sponsor_id,
            client_platform, client_version,
            split_tunnel_url_format, split_tunnel_signature_public_key, 
            split_tunnel_dns_server, executable_path, config_file)
        
        results[test_case] = {}
        try:
            results[test_case] = __test_server(tunnel_core_runner, test_case, expected_egress_ip_addresses, False)
            #for split_tunnel in [True, False]:
            #    results[test_case]['SPLIT TUNNEL {0}'.format(split_tunnel)] = __test_server(tunnel_core_runner, test_case, expected_egress_ip_addresses, split_tunnel)
            #results[test_case] = 'PASS'
        except Exception as ex:
            results[test_case] = 'FAIL: ' + str(ex)
    
    return results


