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
import signal

from functools import wraps

# Local service should be in same GeoIP region; local split tunnel will be in effect (not proxied)
# Remote service should be in different GeoIP region; remote split tunnel will be in effect (proxied)
CHECK_IP_ADDRESS_URL_LOCAL = ['http://automation.whatismyip.com/n09230945.asp']
USER_AGENT = "Python-urllib/psiphon-tunnel-core"

SOURCE_ROOT = os.path.join(os.path.abspath('.'), 'network-health', 'bin')
TUNNEL_CORE = os.path.join(SOURCE_ROOT, 'psiphon-tunnel-core')
CONFIG_FILE_NAME = os.path.join(SOURCE_ROOT, 'tunnel-core-config.config')



def load_default_tunnel_core():
    if not os.path.exists(TUNNEL_CORE):
        print("Psiphon tunnel core binary does not exist in path {0}, exiting".format(SOURCE_ROOT))
        sys.exit(1)
    return TUNNEL_CORE


def load_default_config():
    if not os.path.exists(CONFIG_FILE_NAME):
        print("Psiphon tunnel core config does not exist in path {0}, exiting".format(SOURCE_ROOT))
        sys.exit(1)
    return CONFIG_FILE_NAME


def load_server_config(server_id):
    return os.path.join(os.path.abspath('.'), 'network-health', 'conf', 
        'tunnel-core-config-{id}.config'.format(id=server_id.replace(' ', '_')))

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    CHECK_IP_ADDRESS_URL_LOCAL = psi_data_config.CHECK_IP_ADDRESS_URL_LOCAL
    CHECK_IP_ADDRESS_URL_REMOTE = psi_data_config.CHECK_IP_ADDRESS_URL_REMOTE
    USER_AGENT = psi_data_config.USER_AGENT


def retry_on_exception_decorator(function):
    @wraps(function)
    def wrapper(*args, **kwds):
        raised_exception = None
        for i in range(2):
            try:
                if i > 0:
                    time.sleep(20)
                return function(*args, **kwds)
            except Exception as e:
                print(str(e))
                raised_exception = e
                pass
        raise raised_exception
    return wrapper


class TunnelCoreCouldNotConnectException(Exception):
    def __init__(self, *args):
        Exception.__init__(self, *args)


class TunnelCoreConsoleRunner:
    def __init__(self, encoded_server_entry, propagation_channel_id='0', 
                 sponsor_id='0', client_platform='', client_version='0', 
                 use_indistinguishable_tls=True, split_tunnel_url_format='', 
                 split_tunnel_signature_public_key='', split_tunnel_dns_server='', 
                 tunnel_core_binary=None, tunnel_core_config=None, packet_tunnel_params=dict()):
        self.proc = None
        self.http_proxy_port = 0
        self.socks_proxy_port = 0
        self.encoded_server_entry = encoded_server_entry
        self.propagation_channel_id = propagation_channel_id
        self.sponsor_id = sponsor_id
        self.client_platform = client_platform
        self.client_version = client_version
        self.use_indistinguishable_tls = use_indistinguishable_tls
        self.split_tunnel_url_format = split_tunnel_url_format
        self.split_tunnel_signature_public_key = split_tunnel_signature_public_key
        self.split_tunnel_dns_server = split_tunnel_dns_server
        self.tunnel_core_binary = tunnel_core_binary
        self.tunnel_core_config = tunnel_core_config
        
        self.packet_tunnel_tests = False
        self.cmdline_opts = list()
        self.tun_source_ip_address = ''
        self.tun_source_port = 0
        self.test_sites = []
        if len(packet_tunnel_params) > 0:
            self.packet_tunnel_tests = True
            self.tun_source_ip_address = packet_tunnel_params.pop('tunIPAddress')
            self.test_sites = packet_tunnel_params.pop('test_sites')
            for k,v in packet_tunnel_params.items():
                self.cmdline_opts += ['-'+k, v]
    
     
    # Setup and create tunnel core config file.
    def _setup_tunnel_config(self, transport):
        config = {
            "DataRootDirectory": os.path.dirname(self.tunnel_core_config),
            "TargetServerEntry": self.encoded_server_entry, # Single Test Server Parameter
            "TunnelProtocol": transport, # Single or group Test Protocol
            "PropagationChannelId" : self.propagation_channel_id, # Propagation Channel ID = "Testing"
            "SponsorId" : self.sponsor_id,
            "ClientPlatform" : self.client_platform,
            "ClientVersion" : self.client_version,
            "LocalHttpProxyPort" : self.http_proxy_port,
            "LocalSocksProxyPort" : self.socks_proxy_port,
            "UseIndistinguishableTLS": self.use_indistinguishable_tls,
            "TunnelPoolSize" : 1,
            "ConnectionWorkerPoolSize" : 1,
            "PortForwardFailureThreshold" : 5,
            "EmitDiagnosticNotices": True,
            "DisableReplay": True,
            "SplitTunnelRoutesUrlFormat" : self.split_tunnel_url_format,
            "SplitTunnelRoutesSignaturePublicKey" : self.split_tunnel_signature_public_key,
            "SplitTunnelDnsServer" : self.split_tunnel_dns_server
        }
        
        if self.packet_tunnel_tests:
            config['DisableLocalSocksProxy'] = True
            config['DisableLocalHTTPProxy'] = True

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

        cmd = [self.tunnel_core_binary, '-config', self.tunnel_core_config] + self.cmdline_opts

        self.proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)

    def wait_for_connection(self):
        # If using tunnel-core
        # Read tunnel-core log file for connection message instead of sleep 25 second

        time.sleep(1)
        print('Tunnel Core is connecting...')
        start_time = time.time()

        # Breaking this loop means the process sent EOF to stderr, or 'tunnels' tunnels were established
        while True:
            line = self.proc.stderr.readline()
            if not line:
                raise TunnelCoreCouldNotConnectException('Could not connect, reading output failed.')

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
                print('Not successfully connected after 25 second.')
                raise TunnelCoreCouldNotConnectException('Could not connect after 25 seconds')


    def setup_proxy(self):
        return urllib3.ProxyManager("http://127.0.0.1:{http_port}".format(http_port=self.http_proxy_port), timeout=30.0)
    
    
    def run_packet_tunnel_tests(self, test_sites, expected_egress_ip_addresses, user_agent):
        import dns.resolver
        import urllib3
        
        if len(test_sites) == 0:
            output = {'PT-DNS' : 'FAIL: No test sites provided',
                      'PT-HTTPS' : 'FAIL: No test sites provided'}
        else:
            # TODO: Perform the test on multiple sites and record each result
            url = test_sites[0]['url']
            expected_ip = test_sites[0]['expected_ip']
            
            # packet tunnel dns test. Resolve the url through the tunnel
            output = {'PT-DNS' : 'FAIL',
                      'PT-HTTPS' : 'FAIL'}
            
            fqdn=''
            remote_host = expected_ip
            remote_port = 443
            split_url = url.split('://')
            if len(split_url) >= 2:
                parts = split_url[1].split('/', 2)
                fqdn = parts[0]
                path = '/'
                if len(parts) >= 2:
                    path += parts[1]
            
            resolver = dns.resolver.Resolver(configure=False) # Don't use the system resolver settings
            resolver.nameservers = ['10.0.0.2']
            answer = resolver.query(fqdn, source=self.tun_source_ip_address)
            for rr in answer.rrset:
                if rr.address == expected_ip:
                    print('Packet Tunnel DNS Test successful')
                    output['PT-DNS'] = 'PASS: {0} resolved to {1}'.format(fqdn, rr.address)
                    break
            
            
            pool = urllib3.HTTPSConnectionPool(host=fqdn, port=remote_port,
                                               maxsize=2,
                                               timeout=30.0,
                                               source_address=(self.tun_source_ip_address,
                                                               self.tun_source_port))
            response = pool.request('GET', path, headers={"User-Agent": user_agent}, release_conn=True)
            egress_ip_address = response.data.strip()
            is_proxied = (egress_ip_address.decode("UTF-8") in expected_egress_ip_addresses)
            if is_proxied:
                output['PT-HTTPS'] = 'PASS'
        
        
        return output

    def stop_psiphon(self):
        try:
            self.proc.send_signal(signal.SIGINT)
            (stdin, stderr) = self.proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

        try:
            #os.remove(self.tunnel_core_config)
            time.sleep(1)
        except Exception as e:
            print("Remove Config/Log File Failed" + str(e))


@retry_on_exception_decorator
def __test_server(runner, transport, expected_egress_ip_addresses, test_sites, additional_test_sites, user_agent, split_tunnel_mode):
    # test:
    # - spawn client process, which starts the VPN
    # - sleep 5 seconds, which allows time to establish connection
    # - determine egress IP address and assert it matches host IP address
    
    output_str = ''
    output = {}
    url = ''
    packet_tunnel_test_results = {}
    # Split tunnelling is not implemented for VPN.
    # Also, if there is no remote check, don't use split tunnel mode because we always want
    # to test at least one proxied case.
    
    print('Testing egress IP addresses %s in %s mode (split tunnel %s)...' % (
            ','.join(expected_egress_ip_addresses), transport, 'ENABLED' if split_tunnel_mode else 'DISABLED'))
    
    try:
        runner.connect_to_server(transport, split_tunnel_mode)
        
        runner.wait_for_connection()
        
        if runner.packet_tunnel_tests:
            output.update(runner.run_packet_tunnel_tests(
                                    runner.test_sites, 
                                    expected_egress_ip_addresses,
                                    user_agent))
        
        else:
            
            http_proxy = runner.setup_proxy()

            
            time.sleep(5)
            
            for url in test_sites:
                # Get egress IP from web site in same GeoIP region; local split tunnel is not proxied
                
                print("Testing site: {0}".format(url)) 
                
                if url.startswith('https'):
                    urllib3.disable_warnings()
                
                try:
                    egress_ip_address = http_proxy.request(
                        'GET', 
                        url, 
                        headers={
                            "User-Agent":   user_agent
                        }).data.split(b'\n')[0]
                    
                    is_proxied = (egress_ip_address.decode("UTF-8") in expected_egress_ip_addresses)
                    
                    if url.startswith('https'):
                        output['HTTPS'] = 'PASS' if is_proxied else 'FAIL : Connection is not proxied.  Egress IP is: {0}, expected: {1}'.format(egress_ip_address, expected_egress_ip_addresses)
                    else:
                        output['HTTP'] = 'PASS' if is_proxied else 'FAIL : Connection is not proxied.  Egress IP is: {0}, expected: {1}'.format(egress_ip_address, expected_egress_ip_addresses)
                                
                except urllib3.exceptions.MaxRetryError as err:
                    if url.startswith('https'):
                        output['HTTPS'] = 'FAIL : MaxRetryError: {0}'.format(err)
                    else:
                        output['HTTP'] = 'FAIL MaxRetryError: {0}'.format(err)
                    continue
            
            if len(additional_test_sites) > 0:
                output['AdditionalSites'] = list()
                for url in additional_test_sites:
                    try:
                        if url.startswith('https'):
                            urllib3.disable_warnings()
                        
                        print('Testing: {0}'.format(url))
                        if is_proxied:
                            tunneled_site = http_proxy.request('GET', url)
                            
                            pool = urllib3.PoolManager(timeout=30.0)
                            untunneled_site = pool.request('GET', url)
                            
                            # Compare sites:
                            if tunneled_site.status != untunneled_site.status:
                                output_str = 'FAIL : mismatched status code returned'
                            else:
                                import hashlib
                                untunneled_hash = hashlib.sha1(untunneled_site.data).hexdigest()
                                tunneled_hash = hashlib.sha1(tunneled_site.data).hexdigest()
                                if tunneled_hash != untunneled_hash:
                                    output_str = 'FAIL : Mismatched site hashes'
                                else:
                                    output_str = 'SUCCESS : {url} returned the same site tunneled and untunneled'.format(url=url)
                        else:
                            output_str = 'FAIL : Connection to server is unproxied.  Check server connection'
                        
                        output['AdditionalSites'].append({url: output_str})
                        
                    except urllib3.exceptions.MaxRetryError:
                        output['AdditionalSites'] = 'FAIL {0}'.format(output_str)
                        continue 
    
    except Exception as err:
        print("Could not tunnel to {0}: {1}".format(url, err))
        output['HTTP'] = output['HTTPS'] = 'FAIL : General Exception: {0}'.format(err)
        raise
    finally:
        print("Stopping tunnel to {ipaddr}".format(ipaddr = expected_egress_ip_addresses))
        runner.stop_psiphon()
    
    return output


def get_server_test_cases(server, host, test_cases):
    capabilities = server.capabilities
    
    local_test_cases = copy.copy(test_cases) if test_cases else ['handshake', 'VPN', 'OSSH', 'SSH', 'UNFRONTED-MEEK-OSSH', 'UNFRONTED-MEEK-HTTPS-OSSH', 'UNFRONTED-MEEK-SESSION-TICKET-OSSH', 'FRONTED-MEEK-OSSH', 'FRONTED-MEEK-HTTP-OSSH', 'FRONTED-MEEK-QUIC-OSSH', 'QUIC-OSSH', 'TAPDANCE-OSSH']

    for test_case in copy.copy(local_test_cases):
        if ((test_case == 'VPN' # VPN requires handshake, SSH or SSH+
                and not (capabilities['handshake'] or capabilities['OSSH'] or capabilities['SSH'] or capabilities['FRONTED-MEEK'] or capabilities['UNFRONTED-MEEK']))
            or (test_case == 'UNFRONTED-MEEK-OSSH' and not (capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 80))
            or (test_case == 'UNFRONTED-MEEK-HTTPS-OSSH' and not (capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 443))
            or (test_case == 'UNFRONTED-MEEK-SESSION-TICKET-OSSH' and not capabilities['UNFRONTED-MEEK-SESSION-TICKET'])
            or (test_case == 'FRONTED-MEEK-OSSH' and not capabilities['FRONTED-MEEK'])
            or (test_case == 'FRONTED-MEEK-HTTP-OSSH' and not (capabilities['FRONTED-MEEK'] and host.alternate_meek_server_fronting_hosts))
            or (test_case == 'FRONTED-MEEK-QUIC-OSSH' and not capabilities['FRONTED-MEEK-QUIC'])
            or (test_case == 'QUIC-OSSH' and not capabilities['QUIC'])
            or (test_case == 'TAPDANCE-OSSH' and not capabilities['TAPDANCE'])
            or (test_case in ['handshake', 'OSSH', 'SSH', 'VPN'] and not capabilities[test_case])
            or test_case == 'handshake' or test_case == 'VPN'):
            local_test_cases.remove(test_case)
    
    return local_test_cases



def test_server(server, host, encoded_server_entry, split_tunnel_url_format, 
                split_tunnel_signature_public_key, split_tunnel_dns_server, 
                expected_egress_ip_addresses, test_propagation_channel_id='0', 
                test_sponsor_id='0', client_platform='', client_version='',
                use_indistinguishable_tls=True, test_cases = None, 
                ip_test_sites = [], additional_test_sites = [], user_agent=USER_AGENT,
                executable_path = None, config_file = None, 
                packet_tunnel_params=dict()):
    
    if len(ip_test_sites) == 0:
        ip_test_sites = CHECK_IP_ADDRESS_URL_LOCAL
        if isinstance(ip_test_sites, str):
            ip_test_sites = [ip_test_sites]
    
    if executable_path is None:
        executable_path = load_default_tunnel_core()
    
    if config_file is None:
        config_file = load_default_config()
    
    test_cases = get_server_test_cases(server, host, test_cases)
    
    
    # Use kwargs to pass command line options
    cmdline_opts = list()
    
    if len(packet_tunnel_params) > 0:
        test_cases = [test_cases][0]
        print('Testing Packet Tunnel using {}'.format(test_cases[0]))
    
    results = {}
    for test_case in test_cases:
        tunnel_core_runner = TunnelCoreConsoleRunner(
            encoded_server_entry, test_propagation_channel_id, test_sponsor_id,
            client_platform, client_version, use_indistinguishable_tls,
            split_tunnel_url_format, split_tunnel_signature_public_key, 
            split_tunnel_dns_server, executable_path, config_file, packet_tunnel_params)
        
        results[test_case] = {}
        try:
            results[test_case] = __test_server(tunnel_core_runner, test_case, 
                                               expected_egress_ip_addresses, 
                                               ip_test_sites, additional_test_sites, user_agent, False)
            #for split_tunnel in [True, False]:
            #    results[test_case]['SPLIT TUNNEL {0}'.format(split_tunnel)] = __test_server(tunnel_core_runner, test_case, expected_egress_ip_addresses, split_tunnel)
            #results[test_case] = 'PASS'
        except Exception as err:
            results[test_case] = 'FAIL : Exception: {0}'.format(str(err))
    
    return results


