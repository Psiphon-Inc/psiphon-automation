#!/usr/bin/python
#
# Copyright (c) 2016, Psiphon Inc.
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

'''

Example input:
https://192.168.0.1:80/handshake?propagation_channel_id=0987654321&sponsor_id=1234554321&client_version=1&server_secret=1234567890

'''

import string
import threading
import time
import os
import syslog
import ssl
import tempfile
import netifaces
import socket
import json
import re
from cherrypy import wsgiserver, HTTPError
from cherrypy.wsgiserver import ssl_pyopenssl
from cherrypy.lib import cpstats
from webob import Request
import psi_psk
import psi_config
import psi_geoip
import sys
import traceback
import platform
import redis
from datetime import datetime
from functools import wraps
import psi_web_patch
import multiprocessing
from base64 import b64decode
from base64 import urlsafe_b64decode
from OpenSSL.crypto import X509Store, X509StoreContext
from OpenSSL.crypto import load_certificate
from OpenSSL.crypto import FILETYPE_PEM
from OpenSSL.crypto import FILETYPE_ASN1
from OpenSSL.crypto import verify

# ===== PSINET database ===================================================

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Automation')))
import psi_ops
import psi_ops_discovery

psinet = psi_ops.PsiphonNetwork.load_from_file(psi_config.DATA_FILE_NAME)

# ===== Globals =====

CLIENT_VERIFICATION_REQUIRED = False

# one week TTL
CLIENT_VERIFICATION_TTL_SECONDS = 60 * 60 * 24 * 7

# ===== Helpers =====

# see: http://codahale.com/a-lesson-in-timing-attacks/
def constant_time_compare(a, b):
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


def consists_of(str, characters):
    return 0 == len(filter(lambda x : x not in characters, str))


def contains(str, characters):
    return True in [character in str for character in characters]


def is_valid_ip_address(str):
    try:
        socket.inet_aton(str)
        return True
    except:
        return False


# From: http://stackoverflow.com/questions/2532053/validate-a-hostname-string
#
# "ensures that each segment
#    * contains at least one character and a maximum of 63 characters
#    * consists only of allowed characters
#    * doesn't begin or end with a hyphen"
#
def is_valid_domain(hostname):
    if len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1] # strip exactly one dot from the right, if present
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))


# "<host>:<port>", where <host> is a domain or IP address
def is_valid_dial_address(str):
    strs = string.split(str, ':')
    if len(strs) != 2:
        return False
    if not is_valid_ip_address(strs[0]) and not is_valid_domain(strs[0]):
        return False
    if not strs[1].isdigit():
        return False
    port = int(strs[1])
    return port > 0 and port < 65536


# "<host>:<port>", where <host> is a domain or IP address and ":<port>" is optional
def is_valid_host_header(str):
    return is_valid_dial_address(str) or is_valid_domain(str) or is_valid_ip_address(str)


# takes "<host>:<port>" and returns "<host>"
def get_host(str):
    return string.split(str, ':', 1)[0]


EMPTY_VALUE = '(NONE)'


def is_valid_relay_protocol(str):
    return str in ['VPN', 'SSH', 'OSSH', 'FRONTED-MEEK-OSSH', 'FRONTED-MEEK-HTTP-OSSH', 'UNFRONTED-MEEK-OSSH', 'UNFRONTED-MEEK-HTTPS-OSSH', EMPTY_VALUE]


def is_valid_server_entry_source(str):
    return str in ['EMBEDDED', 'REMOTE', 'DISCOVERY', 'TARGET']


is_valid_iso8601_date_regex = re.compile(r'(?P<year>[0-9]{4})-(?P<month>[0-9]{1,2})-(?P<day>[0-9]{1,2})T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})(\.(?P<fraction>[0-9]+))?(?P<timezone>Z|(([-+])([0-9]{2}):([0-9]{2})))')
def is_valid_iso8601_date(str):
    return is_valid_iso8601_date_regex.match(str) != None


def is_valid_boolean_str(str):
    return str in ['0', '1']


def is_valid_upstream_proxy_type(value):
    return isinstance(value, basestring) and value.lower() in ['socks4a', 'socks5', 'http']


def is_valid_json_string_array(value):
    try:
        string_array = json.loads(value)
        if not isinstance(string_array, list):
            return False
        for item in string_array:
            if not isinstance(item, basestring):
                return False
    except ValueError:
        return False
    return True


# see: http://code.activestate.com/recipes/496784-split-string-into-n-size-pieces/
def split_len(seq, length):
    return [seq[i:i+length] for i in range(0, len(seq), length)]


def safe_int(input):
    return_value = 0
    try:
        return_value = int(input)
    except:
        pass
    return return_value

def decode_base64(data):
    data = str(data)
    missing_padding = 4 - len(data) % 4
    if missing_padding:
        data += b'='* missing_padding
    return urlsafe_b64decode(data)

def exception_logger(function):
    @wraps(function)
    def wrapper(*args, **kwds):
        try:
            return function(*args, **kwds)
        except:
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_ERR, line)
            raise
    return wrapper


# ===== Psiphon Web Server =====

class ServerInstance(object):

    def __init__(self, ip_address, server_secret, capabilities, host_id):
        self.session_redis = redis.StrictRedis(
            host=psi_config.SESSION_DB_HOST,
            port=psi_config.SESSION_DB_PORT,
            db=psi_config.SESSION_DB_INDEX)
        self.discovery_redis = redis.StrictRedis(
            host=psi_config.DISCOVERY_DB_HOST,
            port=psi_config.DISCOVERY_DB_PORT,
            db=psi_config.DISCOVERY_DB_INDEX)
        self.server_ip_address = ip_address
        self.server_secret = server_secret
        self.capabilities = capabilities
        self.host_id = host_id

        self.COMMON_INPUTS = [
            ('server_secret', lambda x: constant_time_compare(x, self.server_secret)),
            ('propagation_channel_id', lambda x: consists_of(x, string.hexdigits) or x == EMPTY_VALUE),
            ('sponsor_id', lambda x: consists_of(x, string.hexdigits) or x == EMPTY_VALUE),
            ('client_version', lambda x: consists_of(x, string.digits) or x == EMPTY_VALUE),
            ('client_platform', lambda x: not contains(x, string.whitespace)),
            ('relay_protocol', is_valid_relay_protocol),
            ('tunnel_whole_device', is_valid_boolean_str)]

        self.OPTIONAL_COMMON_INPUTS = [
            ('client_build_rev', lambda x: consists_of(x, string.hexdigits) or x == EMPTY_VALUE),
            ('device_region', lambda x: consists_of(x, string.letters) and len(x) == 2),
            ('meek_dial_address', is_valid_dial_address),
            ('meek_resolved_ip_address', is_valid_ip_address),
            ('meek_sni_server_name', is_valid_domain),
            ('meek_host_header', is_valid_host_header),
            ('meek_transformed_host_name', is_valid_boolean_str),
            ('user_agent', lambda x: isinstance(x, basestring) or x == EMPTY_VALUE),
            ('server_entry_region', lambda x: consists_of(x, string.letters) and len(x) == 2),
            ('server_entry_source', is_valid_server_entry_source),
            ('server_entry_timestamp', is_valid_iso8601_date),
            ('upstream_proxy_type', is_valid_upstream_proxy_type),
            # Validation note: upstream_proxy_custom_header_names allows arbitrary string values within the array
            ('upstream_proxy_custom_header_names', is_valid_json_string_array),

            # Obsolete
            ('fronting_host', is_valid_domain),
            ('fronting_address', lambda x: is_valid_ip_address(x) or is_valid_domain(x)),
            ('fronting_resolved_ip_address', is_valid_ip_address),
            ('fronting_enabled_sni', is_valid_boolean_str),
            ('fronting_use_http', is_valid_boolean_str),
            ('substitute_server_name', is_valid_domain),
            ('substitute_host_header', is_valid_domain)]


        self.OPTIONAL_COMMON_INPUT_NAMES = [x for (x, _) in self.OPTIONAL_COMMON_INPUTS]

    def _is_request_tunnelled(self, client_ip_address):
        return client_ip_address in ['localhost', '127.0.0.1', self.server_ip_address]

    def _get_inputs(self, request, request_name, additional_inputs=None):
        if additional_inputs is None:
            additional_inputs = []

        input_values = []

        # Add server IP address for logging
        input_values.append(('server_ip_address', self.server_ip_address))

        # Log client region/city/ISP (but not IP address)
        # If the peer is localhost, the web request is coming through the
        # tunnel. In this case, check if the client provided a client_session_id
        # and check if there's a corresponding region in the tunnel session
        # database
        # Update: now we also cache GeoIP lookups done outside the tunnel
        client_ip_address = request.remote_addr
        #geoip = psi_geoip.get_unknown()
        # Use a distinct "Unknown" value to distinguish the case where the request is
        # tunneled and the session redis has expired,
        # from the case where the session has been logged with an unknown ('None') region
        geoip = {'region': 'Unknown', 'city': 'Unknown', 'isp': 'Unknown'}
        if request.params.has_key('client_session_id'):
            client_session_id = request.params['client_session_id']
            if not consists_of(client_session_id, string.hexdigits):
                syslog.syslog(
                    syslog.LOG_ERR,
                    'Invalid client_session_id in %s [%s]' % (request_name, str(request.params)))
                return False
            record = self.session_redis.get(client_session_id)
            if record:
                # Extend the expiry for this record for subsequent requests
                self.session_redis.expire(client_session_id, psi_config.SESSION_EXPIRE_SECONDS)
                try:
                    geoip = json.loads(record)
                except ValueError:
                    # Backwards compatibility case
                    geoip = psi_geoip.get_region_only(record)
            elif not self._is_request_tunnelled(client_ip_address):
                geoip = psi_geoip.get_geoip(client_ip_address)
                # Cache the result for subsequent requests with the same client_session_id
                if len(client_session_id) > 0:
                    self.session_redis.set(client_session_id, json.dumps(geoip))
                    self.session_redis.expire(client_session_id, psi_config.SESSION_EXPIRE_SECONDS)
            # else: is-tunnelled and no cache, so GeoIP is unknown
        elif not self._is_request_tunnelled(client_ip_address):
            # Can't use cache without a client_session_id
            geoip = psi_geoip.get_geoip(client_ip_address)

        # Hack: log parsing is space delimited, so remove spaces from
        # GeoIP string (ISP names in particular)

        input_values.append(('client_region', geoip['region'].replace(' ', '_')))
        input_values.append(('client_city', geoip['city'].replace(' ', '_')))
        input_values.append(('client_isp', geoip['isp'].replace(' ', '_')))

        # Check for each expected input
        for (input_name, validator) in self.COMMON_INPUTS + self.OPTIONAL_COMMON_INPUTS + additional_inputs:
            try:
                value = request.params[input_name]
            except KeyError as e:
                # Backwards compatibility patches
                # - Older clients don't specifiy relay_protocol, default to VPN
                # - Older clients specify vpn_client_ip_address for session ID
                # - Older clients specify client_id for propagation_channel_id
                # - Older clients don't specify client_platform
                # - Older clients don't specify last session date
                # - Older clients (and Windows clients) don't specify tunnel_whole_device
                if input_name == 'relay_protocol':
                    value = 'VPN'
                elif input_name == 'session_id' and request.params.has_key('vpn_client_ip_address'):
                    value = request.params['vpn_client_ip_address']
                elif input_name == 'propagation_channel_id' and request.params.has_key('client_id'):
                    value = request.params['client_id']
                elif input_name == 'client_platform':
                    value = 'Windows'
                elif input_name == 'last_connected':
                    value = 'Unknown'
                elif input_name == 'tunnel_whole_device':
                    value = '0'
                elif input_name in self.OPTIONAL_COMMON_INPUT_NAMES:
                    # Skip this input
                    continue
                else:
                    syslog.syslog(
                        syslog.LOG_ERR,
                        'Missing %s in %s [%s]' % (input_name, request_name, str(request.params)))
                    return False
            if len(value) == 0:
                value = EMPTY_VALUE
            if not validator(value):
                syslog.syslog(
                    syslog.LOG_ERR,
                    'Invalid %s in %s [%s]' % (input_name, request_name, str(request.params)))
                return False
            # Special case: omit server_secret from logging
            if input_name != 'server_secret':
                input_values.append((input_name, value))

        # Caller gets a list of name/value input tuples, used for logging etc.
        return input_values

    def _log_event(self, event_name, log_values):
        # Note: OPTIONAL_COMMON_INPUTS are excluded from legacy stats
        if event_name not in ['domain_bytes', 'session']:
            syslog.syslog(
                syslog.LOG_INFO,
                ' '.join([event_name] + [str(value.encode('utf8') if type(value) == unicode else value)
                                        for (name, value) in log_values if name not in self.OPTIONAL_COMMON_INPUT_NAMES]))

        if event_name not in ['status', 'speed', 'routes', 'download', 'discovery', 'https_requests', 'page_views', 'failed', 'bytes_transferred', 'session', 'domain_bytes', 'handshake', 'user_count', 'disconnected']:
            json_log = {'event_name': event_name, 'timestamp': datetime.utcnow().isoformat() + 'Z', 'host_id': self.host_id}
            for key, value in log_values:
                # convert a number in a string to a long
                if (type(value) == str or type(value) == unicode) and value.isdigit():
                    normalizedValue = long(value)
                # encode unicode to utf8
                elif type(value) == unicode:
                    normalizedValue = str(value.encode('utf8'))
                else:
                    normalizedValue = value

                # Special cases: for ELK performance we record these domain-or-IP
                # fields as one of two different values based on type; we also
                # omit port from host:port fields for now.
                if key == 'fronting_address':
                    if is_valid_ip_address(normalizedValue):
                        json_log['fronting_ip_address'] = normalizedValue
                    else:
                        json_log['fronting_domain'] = normalizedValue
                elif key == 'meek_dial_address':
                    normalizedValue = get_host(normalizedValue)
                    if is_valid_ip_address(normalizedValue):
                        json_log['meek_dial_ip_address'] = normalizedValue
                    else:
                        json_log['meek_dial_domain'] = normalizedValue
                elif key == 'meek_host_header':
                    normalizedValue = get_host(normalizedValue)
                    json_log['meek_host_header'] = normalizedValue
                elif key == 'upstream_proxy_type':
                    # Submitted value could be e.g., "SOCKS5" or "socks5"; log lowercase
                    normalizedValue = normalizedValue.lower()
                    json_log['upstream_proxy_type'] = normalizedValue
                elif key == 'upstream_proxy_custom_header_names':
                    # Note: upstream_proxy_custom_header_names has been validated with is_valid_json_string_array
                    normalizedValue = json.dumps([(str(item.encode('utf8')) if type(item) == unicode else item) for item in json.loads(normalizedValue)])
                    json_log['upstream_proxy_custom_header_names'] = normalizedValue
                elif key in ['tunnel_whole_device', 'meek_transformed_host_name', 'connected', 'fronting_enabled_sni']:
                  # Submitted values could be "0" or "1", but need to be logged as booleans
                  if normalizedValue == "1":
                    json_log[key] = True
                  else:
                    json_log[key] = False
                else:
                    json_log[key] = normalizedValue

            syslog.syslog(
                syslog.LOG_INFO | syslog.LOG_LOCAL0,
                json.dumps(json_log, separators=(',', ':')))

    @exception_logger
    def handshake(self, environ, start_response):
        request = Request(environ)
        inputs = self._get_inputs(request, 'handshake')
        if not inputs:
            start_response('404 Not Found', [])
            return []
        # Client submits a list of known servers which is used to
        # flag "new" discoveries in the stats logging
        # NOTE: not validating that server IP addresses are part of the network
        #       (if we do add this, be careful to not introduce a timing based
        #        attack that could be used to enumerate valid server IPs)
        if hasattr(request, 'str_params'):
            known_servers = request.str_params.getall('known_server')
        else:
            known_servers = request.params.getall('known_server')
        for known_server in known_servers:
            if not is_valid_ip_address(known_server):
                syslog.syslog(
                    syslog.LOG_ERR,
                    'Invalid known server in handshake [%s]' % (str(request.params),))
                start_response('404 Not Found', [])
                return []
        #
        # NOTE: Change PSK *last*
        # There's a race condition between setting it and the client connecting:
        # another client may request /handshake and change the PSK before the
        # first client authenticates to the VPN.  We accept the risk and the
        # client is designed to retry.  Still, best to minimize the time
        # between the PSK change on the server side and the submit by the
        # client.  See the design notes for why we aren't using multiple PSKs
        # and why we're using PSKs instead of VPN PKI: basically, lowest
        # common denominator compatibility.
        #
        self._log_event('handshake', inputs)
        client_ip_address = request.remote_addr

        client_session_id = None
        if request.params.has_key('client_session_id'):
            client_session_id = request.params['client_session_id']

        # If the request is tunnelled, we should find a pre-computed
        # ip_address_strategy_value stored in redis by psi_auth.

        client_ip_address_strategy_value = None
        if self._is_request_tunnelled(client_ip_address):
            client_ip_address = None
            if client_session_id != None:
                record = self.discovery_redis.get(client_session_id)
                if record:
                    self.discovery_redis.delete(client_session_id)
                    discovery_info = json.loads(record)
                    client_ip_address_strategy_value = discovery_info['client_ip_address_strategy_value']
        else:
            client_ip_address_strategy_value = psi_ops_discovery.calculate_ip_address_strategy_value(client_ip_address)
            if client_session_id != None:
                if self.discovery_redis.get(client_session_id) == None:
                    self.discovery_redis.set(client_session_id, json.dumps({'client_ip_address_strategy_value' : client_ip_address_strategy_value}))
                    self.discovery_redis.expire(client_session_id, psi_config.DISCOVERY_EXPIRE_SECONDS)

        # logger callback will add log entry for each server IP address discovered
        def discovery_logger(server_ip_address):
            unknown = '0' if server_ip_address in known_servers else '1'
            self._log_event('discovery',
                             inputs + [('server_ip_address', server_ip_address),
                                       ('unknown', unknown)])

        inputs_lookup = dict(inputs)
        client_region = inputs_lookup['client_region']

        config = psinet.handshake(
                    self.server_ip_address,
                    client_ip_address_strategy_value,
                    client_region,
                    inputs_lookup['propagation_channel_id'],
                    inputs_lookup['sponsor_id'],
                    inputs_lookup['client_platform'],
                    inputs_lookup['client_version'],
                    event_logger=discovery_logger)

        # Report back client region in case client needs to fetch routes file
        # for his region off a 3rd party
        config['client_region'] = client_region

        config['preemptive_reconnect_lifetime_milliseconds'] = \
            psi_config.PREEMPTIVE_RECONNECT_LIFETIME_MILLISECONDS if \
            client_region in psi_config.PREEMPTIVE_RECONNECT_REGIONS else 0

        output = []

        # Legacy handshake output is a series of Name:Value lines returned to
        # the client. That format will continue to be supported (old client
        # versions expect it), but the new format of a JSON-ified object will
        # also be output.

        for homepage_url in config['homepages']:
            output.append('Homepage: %s' % (homepage_url,))

        if config['upgrade_client_version']:
            output.append('Upgrade: %s' % (config['upgrade_client_version'],))

        for encoded_server_entry in config['encoded_server_list']:
            output.append('Server: %s' % (encoded_server_entry,))

        if config['ssh_host_key']:
            output.append('SSHUsername: %s' % (config['ssh_username'],))
            output.append('SSHPassword: %s' % (config['ssh_password'],))
            output.append('SSHHostKey: %s' % (config['ssh_host_key'],))
            output.append('SSHSessionID: %s' % (config['ssh_session_id'],))
            if config.has_key('ssh_port'):
                output.append('SSHPort: %s' % (config['ssh_port'],))
            if config.has_key('ssh_obfuscated_port'):
                output.append('SSHObfuscatedPort: %s' % (config['ssh_obfuscated_port'],))
                output.append('SSHObfuscatedKey: %s' % (config['ssh_obfuscated_key'],))

        # We assume VPN for backwards compatibility, but if a different relay_protocol
        # is specified, then we won't need a PSK.
        if inputs_lookup['relay_protocol'] == 'VPN' and (
                self.capabilities.has_key('VPN') and self.capabilities['VPN']):
            psk = psi_psk.set_psk(self.server_ip_address)
            config['l2tp_ipsec_psk'] = psk
            output.append('PSK: %s' % (psk,))


        config["server_timestamp"] = datetime.utcnow().isoformat() + 'Z'

        # The entire config is JSON encoded and included as well.

        output.append('Config: ' + json.dumps(config))

        response_headers = [('Content-type', 'text/plain')]
        start_response('200 OK', response_headers)
        return ['\n'.join(output)]

    @exception_logger
    def download(self, environ, start_response):
        # NOTE: currently we ignore client_version and just download whatever
        # version is currently in place for the propagation channel ID and sponsor ID.
        inputs = self._get_inputs(Request(environ), 'download')
        if not inputs:
            start_response('404 Not Found', [])
            return []
        self._log_event('download', inputs)
        # e.g., /root/PsiphonV/download/psiphon-<propagation_channel_id>-<sponsor_id>.exe
        inputs_lookup = dict(inputs)
        try:
            if inputs_lookup['client_platform'].lower().find('android') != -1:
                filename = 'PsiphonAndroid-%s-%s.apk' % (
                                inputs_lookup['propagation_channel_id'],
                                inputs_lookup['sponsor_id'])
            else:
                filename = 'psiphon-%s-%s.exe' % (
                                inputs_lookup['propagation_channel_id'],
                                inputs_lookup['sponsor_id'])
            path = os.path.join(psi_config.UPGRADE_DOWNLOAD_PATH, filename)
            with open(path, 'rb') as file:
                contents = file.read()
        # NOTE: exceptions other than IOError will kill the server thread, but
        # we expect only IOError in normal circumstances ("normal" being,
        # for example, an invalid ID so no file exists)
        except IOError as e:
            start_response('404 Not Found', [])
            return []
        response_headers = [('Content-Type', 'application/exe'),
                            ('Content-Length', '%d' % (len(contents),))]
        start_response('200 OK', response_headers)
        return [contents]

    @exception_logger
    def routes(self, environ, start_response):
        request = Request(environ)
        additional_inputs = [('session_id', lambda x: is_valid_ip_address(x) or
                                                      consists_of(x, string.hexdigits))]
        inputs = self._get_inputs(request, 'routes', additional_inputs)
        if not inputs:
            start_response('404 Not Found', [])
            return []
        self._log_event('routes', inputs)
        inputs_lookup = dict(inputs)
        return self._send_routes(inputs_lookup, start_response)

    def _send_routes(self, inputs_lookup, start_response):
        # Do not send routes to Android clients
        if inputs_lookup['client_platform'].lower().find('android') != -1:
            start_response('200 OK', [])
            return []
        try:
            path = os.path.join(
                        psi_config.ROUTES_PATH,
                        psi_config.ROUTE_FILE_NAME_TEMPLATE % (inputs_lookup['client_region'],))
            with open(path, 'rb') as file:
                contents = file.read()
            response_headers = [('Content-Type', 'application/octet-stream'),
                                ('Content-Length', '%d' % (len(contents),))]
            start_response('200 OK', response_headers)
            return [contents]
        except IOError as e:
            # When region route file is missing (including None, A1, ...) then
            # the response is empty.
            start_response('200 OK', [])
            return []

    @exception_logger
    def connected(self, environ, start_response):
        request = Request(environ)
        # Peek at input to determine required parameters
        # We assume VPN for backwards compatibility
        # Note: session ID is a VPN client IP address for backwards compatibility
        additional_inputs = [('session_id', lambda x: is_valid_ip_address(x) or
                                                      consists_of(x, string.hexdigits)),
                             ('last_connected', lambda x: is_valid_iso8601_date(x) or
                                                          x == 'None' or
                                                          x == 'Unknown')]
        inputs = self._get_inputs(request, 'connected', additional_inputs)
        if not inputs:
            start_response('404 Not Found', [])
            return []

        self._log_event('connected', inputs)
        inputs_lookup = dict(inputs)

        # For older Windows clients upon successful connection, we return
        # routing information for the user's country for split tunneling.
        # There is no need to do Android check since older clients ignore
        # this response.
        #
        # Latest Windows version is 44
        if (inputs_lookup['client_platform'].lower().find('windows') != -1
                and int(inputs_lookup['client_version']) <= 44):
            return self._send_routes(inputs_lookup, start_response)
        else:
            now = datetime.utcnow()
            connected_timestamp = {
                    'connected_timestamp' : now.strftime('%Y-%m-%dT%H:00:00.000Z')}
            response_headers = [('Content-type', 'text/plain')]
            start_response('200 OK', response_headers)
            return [json.dumps(connected_timestamp)]

    @exception_logger
    def failed(self, environ, start_response):
        request = Request(environ)
        additional_inputs = [('error_code', lambda x: consists_of(x, string.digits))]
        inputs = self._get_inputs(request, 'failed', additional_inputs)
        if not inputs:
            start_response('404 Not Found', [])
            return []
        self._log_event('failed', inputs)
        # No action, this request is just for stats logging
        start_response('200 OK', [])
        return []

    @exception_logger
    def status(self, environ, start_response):
        request = Request(environ)
        additional_inputs = [('session_id', lambda x: is_valid_ip_address(x) or
                                                      consists_of(x, string.hexdigits)),
                             ('connected', is_valid_boolean_str)]
        inputs = self._get_inputs(request, 'status', additional_inputs)
        if not inputs:
            start_response('404 Not Found', [])
            return []

        log_event = 'status' if request.params['connected'] == '1' else 'disconnected'
        self._log_event(log_event,
                         [('relay_protocol', request.params['relay_protocol']),
                          ('session_id', request.params['session_id'])])

        # Log page view and traffic stats, if available.

        # Traffic stats include session_id so we can report e.g., average bytes
        # transferred per session by region/sponsor.
        # NOTE: The session_id isn't associated with any PII.

        if request.body:
            try:
                stats = json.loads(request.body)

                if stats['bytes_transferred'] > 0:
                    self._log_event('bytes_transferred',
                                    inputs + [('bytes', stats['bytes_transferred'])])

                # Note: no input validation on page/domain.
                # Any string is accepted (regex transform may result in arbitrary string).
                # Stats processor must handle this input with care.

                for page_view in stats['page_views']:
                    self._log_event('page_views',
                                    inputs + [('page', page_view['page']),
                                              ('count', safe_int(page_view['count']))])

                for https_req in stats['https_requests']:
                    self._log_event('https_requests',
                                    inputs + [('domain', https_req['domain']),
                                              ('count', safe_int(https_req['count']))])

                # Older clients will not send this key in the message body
                if 'tunnel_stats' in stats.keys():
                    for tunnel in stats['tunnel_stats']:
                        self._log_event('session', inputs + [
                            ('session_id', tunnel['session_id']),
                            ('tunnel_number', tunnel['tunnel_number']),
                            ('tunnel_server_ip_address', tunnel['tunnel_server_ip_address']),] +

                            # Tunnel Core sends establishment_duration in nanoseconds, divide to get to milliseconds
                            ([('establishment_duration', (int(tunnel['establishment_duration']) / 1000000)),] if 'establishment_duration' in tunnel else []) +

                            [('server_handshake_timestamp', tunnel['server_handshake_timestamp']),
                            # Tunnel Core sends duration in nanoseconds, divide to get to milliseconds
                            ('duration', (int(tunnel['duration']) / 1000000)),
                            ('total_bytes_sent', tunnel['total_bytes_sent']),
                            ('total_bytes_received', tunnel['total_bytes_received'])
                        ])

                # Older clients do not send this key
                if 'host_bytes' in stats.keys():
                    for domain, bytes in stats['host_bytes'].iteritems():
                        self._log_event('domain_bytes', inputs + [
                            ('domain', domain),
                            ('bytes', bytes)
                        ])

                # Older clients do not send this key
                if 'remote_server_list_stats' in stats.keys():
                    for remote_server_list in stats['remote_server_list_stats']:
                        self._log_event('remote_server_list', inputs + [
                            ('client_download_timestamp', remote_server_list['client_download_timestamp']),
                            ('url', remote_server_list['url']),
                            ('etag', remote_server_list['etag'])])

            except:
                # Note that this response will cause clients to keep trying to send the same stats repeatedly, so bugs in the above code block
                # can have bad consequences.
                start_response('403 Forbidden', [])
                return []

        # Clean up session data
        if request.params['connected'] == '0' and request.params.has_key('client_session_id'):
            self.session_redis.delete(request.params['client_session_id'])

        # No action, this request is just for stats logging
        start_response('200 OK', [])
        return []

    @exception_logger
    def client_verification(self, environ, start_response):
        SAFTEYNET_CN = 'attest.android.com'
        PSIPHON3_APK_PACKAGENAMES = ['com.psiphon3', 'com.psiphon3.subscription']
        # cert of the root certificate authority (GeoTrust Global CA)
        # which signs the intermediate certificate from Google (GIAG2)
        GEOTRUST_CERT = '-----BEGIN CERTIFICATE-----\nMIIDVDCCAjygAwIBAgIDAjRWMA0GCSqGSIb3DQEBBQUAMEIxCzAJBgNVBAYTAlVT\nMRYwFAYDVQQKEw1HZW9UcnVzdCBJbmMuMRswGQYDVQQDExJHZW9UcnVzdCBHbG9i\nYWwgQ0EwHhcNMDIwNTIxMDQwMDAwWhcNMjIwNTIxMDQwMDAwWjBCMQswCQYDVQQG\nEwJVUzEWMBQGA1UEChMNR2VvVHJ1c3QgSW5jLjEbMBkGA1UEAxMSR2VvVHJ1c3Qg\nR2xvYmFsIENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2swYYzD9\n9BcjGlZ+W988bDjkcbd4kdS8odhM+KhDtgPpTSEHCIjaWC9mOSm9BXiLnTjoBbdq\nfnGk5sRgprDvgOSJKA+eJdbtg/OtppHHmMlCGDUUna2YRpIuT8rxh0PBFpVXLVDv\niS2Aelet8u5fa9IAjbkU+BQVNdnARqN7csiRv8lVK83Qlz6cJmTM386DGXHKTubU\n1XupGc1V3sjs0l44U+VcT4wt/lAjNvxm5suOpDkZALeVAjmRCw7+OC7RHQWa9k0+\nbw8HHa8sHo9gOeL6NlMTOdReJivbPagUvTLrGAMoUgRx5aszPeE4uwc2hGKceeoW\nMPRfwCvocWvk+QIDAQABo1MwUTAPBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQWBBTA\nephojYn7qwVkDBF9qn1luMrMTjAfBgNVHSMEGDAWgBTAephojYn7qwVkDBF9qn1l\nuMrMTjANBgkqhkiG9w0BAQUFAAOCAQEANeMpauUvXVSOKVCUn5kaFOSPeCpilKIn\nZ57QzxpeR+nBsqTP3UEaBU6bS+5Kb1VSsyShNwrrZHYqLizz/Tt1kL/6cdjHPTfS\ntQWVYrmm3ok9Nns4d0iXrKYgjy6myQzCsplFAMfOEVEiIuCl6rYVSAlk6l5PdPcF\nPseKUgzbFbS9bZvlxrFUaKnjaZC2mqUPuLk/IH2uSrW4nOQdtqvmlKXBx4Ot2/Un\nhw4EbNX/3aBd7YdStysVAq45pmp06drE57xNNB6pXE0zX5IJL4hmXXeXxx12E6nV\n5fEWCRE11azbJHFwLJhWC9kXtNHjUStedejV0NxPNO3CBWaAocvmMw==\n-----END CERTIFICATE-----\n'
        # base64 encoded sha256 hash of the license used to sign the android
        # client (.apk) https://psiphon.ca/en/faq.html#authentic-android
        #
        # keytool -printcert -file CERT.RSA
        # SHA256: 76:DB:EF:15:F6:77:26:D4:51:A1:23:59:B8:57:9C:0D:7A:9F:63:5D:52:6A:A3:74:24:DF:13:16:32:F1:78:10
        #
        # echo dtvvFfZ3JtRRoSNZuFecDXqfY11SaqN0JN8TFjLxeBA= | base64 -d | hexdump  -e '32/1 "%02X " "\n"'
        # 76 DB EF 15 F6 77 26 D4 51 A1 23 59 B8 57 9C 0D 7A 9F 63 5D 52 6A A3 74 24 DF 13 16 32 F1 78 10
        PSIPHON3_BASE64_CERTHASH = 'dtvvFfZ3JtRRoSNZuFecDXqfY11SaqN0JN8TFjLxeBA='

        global CLIENT_VERIFICATION_REQUIRED
        global CLIENT_VERIFICATION_TTL_SECONDS

        request = Request(environ)

        # get default inputs for logging
        get_inputs = self._get_inputs(request, "client_verification")
        # still log malformed requests for now
        inputs = get_inputs if get_inputs else []

        if not request.body:
            start_response('200 OK', [("Content-Type", "application/json")])
            if CLIENT_VERIFICATION_REQUIRED:
                return [json.dumps({"client_verification_ttl_seconds":CLIENT_VERIFICATION_TTL_SECONDS})]
            else:
                # Send valid empty JSON here.
                # There is a bug in Android client v.133 that treats JSON parse failure as a
                # failure to send payload and sends client into an infinite retry loop
                return ['{}']
        else:
            try:
                body = json.loads(request.body)
                status = body['status']

                status_strings = {
                    0: "API_REQUEST_OK",
                    1: "API_REQUEST_FAILED",
                    2: "API_CONNECT_FAILED"
                }

                status_string = status_strings.get(status, "INVALID_STATUS: expected 0-2, got %d" % status)

                if (status != 0):
                    # log errors for now
                    self._log_event("client_verification", inputs + [('safetynet_check',
                                                                    {
                                                                        'error_message': status_string,
                                                                        'payload': body.get('payload', None)
                                                                    }
                                                                    )])
                    start_response('200 OK', [("Content-Type", "application/json")])
                    return ['{}']

                jwt = body['payload']
                jwt_parts = jwt.split('.')

                if (len(jwt_parts) == 3):
                    header = decode_base64(jwt_parts[0])
                    payload = decode_base64(jwt_parts[1])
                    signature = decode_base64(jwt_parts[2])
                else:
                    # invalid request to /client_verification, log for now
                    self._log_event("client_verification", inputs + [('safetynet_check',
                                                                    {
                                                                        'error_message': 'Invalid request to client_verification, malformed jwt',
                                                                        'payload': str(jwt)
                                                                    }
                                                                    )])
                    start_response('200 OK', [("Content-Type", "application/json")])
                    return ['{}']

                jwt_header_obj = json.loads(header)
                jwt_payload_obj = json.loads(payload)

                # verify cert chain
                x5c = jwt_header_obj['x5c']

                if (len(x5c) == 0 or len(x5c) > 10):
                    # invalid cert chain, log for now
                    # OpenSSL's default maximum chain length is 10
                    self._log_event("client_verification", inputs + [('safetynet_check',
                                                                    {
                                                                        'error_message': 'Invalid certchain of size %d' % len(x5c),
                                                                        'payload': str(jwt)
                                                                    }
                                                                    )])
                    start_response('200 OK', [("Content-Type", "application/json")])
                    return ['{}']

                leaf_cert_data = b64decode(x5c[0])
                leaf_cert = load_certificate(FILETYPE_ASN1, leaf_cert_data)
                root_cert = load_certificate(FILETYPE_PEM, GEOTRUST_CERT)

                store = X509Store()
                store.add_cert(root_cert)

                for cert_index in xrange(1,len(x5c)):
                    intermediate_data = b64decode(x5c[cert_index])
                    intermediate_cert = load_certificate(FILETYPE_ASN1, intermediate_data)
                    store.add_cert(intermediate_cert)

                store_ctx = X509StoreContext(store, leaf_cert)

                try:
                    valid_certchain = store_ctx.verify_certificate()
                except Exception as e:
                    valid_certchain = e

                # verify CN
                components = dict(leaf_cert.get_subject().get_components())
                valid_CN = components['CN'] == SAFTEYNET_CN

                # verify signature
                try:
                    signature_errors = verify(leaf_cert, signature, jwt_parts[0] + '.' + jwt_parts[1], 'sha256')
                except Exception as e:
                    signature_errors = e

                # verify apkCertificateDigest
                valid_apk_cert = (len(jwt_payload_obj['apkCertificateDigestSha256']) > 0 and
                                    jwt_payload_obj['apkCertificateDigestSha256'][0] == PSIPHON3_BASE64_CERTHASH)

                # verify packagename
                valid_apk_packagename = jwt_payload_obj['apkPackageName'] in PSIPHON3_APK_PACKAGENAMES

                # convert timestamp from ms to iso format
                timestamp = datetime.fromtimestamp(jwt_payload_obj['timestampMs']/1000.0).isoformat() + 'Z'

                # both will be error type otherwise
                is_valid_certchain = valid_certchain == None
                is_valid_sig = signature_errors == None

                self._log_event("client_verification", inputs +
                                                    [('safetynet_check',
                                                    {
                                                        'apk_certificate_digest_sha256': (jwt_payload_obj['apkCertificateDigestSha256'][0]
                                                                                            if len(jwt_payload_obj['apkCertificateDigestSha256']) > 0 else ''),
                                                        'apk_digest_sha256': jwt_payload_obj['apkDigestSha256'],
                                                        'apk_package_name': jwt_payload_obj['apkPackageName'],
                                                        'certchain_errors': str(valid_certchain),
                                                        'cts_profile_match': jwt_payload_obj['ctsProfileMatch'],
                                                        'extension': jwt_payload_obj['extension'],
                                                        'nonce': jwt_payload_obj['nonce'],
                                                        'signature_errors': str(signature_errors),
                                                        'status': str(status),
                                                        'status_string': status_string,
                                                        'valid_cn': valid_CN,
                                                        'valid_apk_cert': valid_apk_cert,
                                                        'valid_apk_packagename': valid_apk_packagename,
                                                        'valid_certchain': is_valid_certchain,
                                                        'valid_signature': is_valid_sig,
                                                        'verification_timestamp': timestamp
                                                    }
                                                    )])
            except Exception:
                try:
                    payload = json.loads(request.body).get('payload', None)
                    jwt_parts = payload.split('.')
                    if len(jwt_parts) != 3:
                        payload = "JWT does not have 3 parts"
                    else:
                        payload = decode_base64(jwt_parts[1])
                except (AttributeError, ValueError):
                    payload = "No valid JSON could be decoded in request body"
                except:
                    payload = "Payload is not valid base64"

                exc_type, exc_obj, exc_tb = sys.exc_info()
                self._log_event("client_verification", inputs + [('safetynet_check',
                                                                {
                                                                    'error_message': 'Exception: %s %s on line %s' % (str(exc_type), str(exc_obj), str(exc_tb.tb_lineno)),
                                                                    'payload': payload
                                                                }
                                                                )])
        start_response('200 OK', [("Content-Type", "application/json")])
        return ['{}']

    @exception_logger
    def speed(self, environ, start_response):
        request = Request(environ)

        # Note: 'operation' and 'info' are arbitrary strings. See note above.

        additional_inputs = [('operation', lambda x: True),
                             ('info', lambda x: True),
                             ('milliseconds', lambda x: consists_of(x, string.digits)),
                             ('size', lambda x: consists_of(x, string.digits))]
        inputs = self._get_inputs(request, 'speed', additional_inputs)
        if not inputs:
            start_response('404 Not Found', [])
            return []
        self._log_event('speed', inputs)
        # No action, this request is just for stats logging
        start_response('200 OK', [])
        return []

    @exception_logger
    def feedback(self, environ, start_response):
        # TODO: When enough people have upgraded, remove this handler completely
        start_response('200 OK', [])
        return []

    @exception_logger
    def check(self, environ, start_response):
        # Just check the server secret; no logging or action for this request
        request = Request(environ)
        if ('server_secret' not in request.params or
            not constant_time_compare(request.params['server_secret'], self.server_secret)):
            start_response('404 Not Found', [])
            return []
        start_response('200 OK', [])
        return []

    @exception_logger
    def stats(self, environ, start_response):
        # Just check the server secret; no logging or action for this request
        request = Request(environ)
        if ('server_secret' not in request.params or
            not constant_time_compare(request.params['server_secret'], self.server_secret) or
            'stats_client_secret' not in request.params or
            not hasattr(psi_config, 'STATS_CLIENT_SECRET') or
            not constant_time_compare(request.params['stats_client_secret'], psi_config.STATS_CLIENT_SECRET)):
            start_response('404 Not Found', [])
            return []
        contents = ''.join(list(cpstats.StatsPage().index()))
        response_headers = [('Content-Type', 'text/html'),
                            ('Content-Length', '%d' % (len(contents),))]
        start_response('200 OK', response_headers)
        return [contents]


def get_servers():
    # enumerate all interfaces with an IPv4 address and server entry
    # return an array of server info for each server to be run
    servers = []
    for interface in netifaces.interfaces():
        try:
            if (interface.find('ipsec') == -1 and interface.find('mast') == -1 and
                    netifaces.ifaddresses(interface).has_key(netifaces.AF_INET)):
                interface_ip_address = netifaces.ifaddresses(interface)[netifaces.AF_INET][0]['addr']
                server = psinet.get_server_by_internal_ip_address(interface_ip_address)
                if server:
                    servers.append(
                        (interface_ip_address,
                         server.web_server_port,
                         server.web_server_secret,
                         server.web_server_certificate,
                         server.web_server_private_key,
                         server.capabilities,
                         server.host_id))
        except ValueError as e:
            if str(e) != 'You must specify a valid interface name.':
                raise
    return servers


class WebServerThread(threading.Thread):

    def __init__(self, ip_address, port, secret, certificate, private_key, capabilities, host_id, server_threads):
        #super(WebServerThread, self).__init__(self)
        threading.Thread.__init__(self)
        self.ip_address = ip_address
        self.port = port
        self.secret = secret
        self.certificate = certificate
        self.private_key = private_key
        self.capabilities = capabilities
        self.host_id = host_id
        self.server = None
        self.certificate_temp_file = None
        self.private_key_temp_file = None
        self.server_threads = server_threads

    def stop_server(self):
        # Retry loop in case self.server.stop throws an exception
        for i in range(5):
            try:
                if self.server:
                    # blocks until server stops
                    self.server.stop()
                    self.server = None
                break
            except Exception as e:
                # Log errors
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                time.sleep(i)
        if self.certificate_temp_file:
            # closing the temp file auto deletes it (NOTE: not secure wipe)
            self.certificate_temp_file.close()
            self.certificate_temp_file = None
        if self.private_key_temp_file:
            self.private_key_temp_file.close()
            self.private_key_temp_file = None

    def run(self):
        # While loop is for recovery from 'unknown ca' issue.
        while True:
            try:
                server_instance = ServerInstance(self.ip_address, self.secret, self.capabilities, self.host_id)

                self.server = wsgiserver.CherryPyWSGIServer(
                                (self.ip_address, int(self.port)),
                                wsgiserver.WSGIPathInfoDispatcher(
                                    {'/handshake': server_instance.handshake,
                                     '/download': server_instance.download,
                                     '/connected': server_instance.connected,
                                     '/routes': server_instance.routes,
                                     '/failed': server_instance.failed,
                                     '/status': server_instance.status,
                                     '/client_verification': server_instance.client_verification,
                                     '/speed': server_instance.speed,
                                     '/feedback': server_instance.feedback,
                                     '/check': server_instance.check,
                                     '/stats': server_instance.stats}),
                                numthreads=self.server_threads, timeout=20)

                self.server.stats['Enabled'] = True

                # Set maximum request input sizes to avoid processing DoS inputs
                self.server.max_request_header_size = 100000
                self.server.max_request_body_size = 100000

                # Lifetime of cert/private key temp file is lifetime of server
                # file is closed by ServerInstance, and that auto deletes tempfile
                self.certificate_temp_file = tempfile.NamedTemporaryFile()
                self.private_key_temp_file = tempfile.NamedTemporaryFile()
                self.certificate_temp_file.write(
                    '-----BEGIN CERTIFICATE-----\n' +
                    '\n'.join(split_len(self.certificate, 64)) +
                    '\n-----END CERTIFICATE-----\n');
                self.certificate_temp_file.flush()
                self.private_key_temp_file.write(
                    '-----BEGIN RSA PRIVATE KEY-----\n' +
                    '\n'.join(split_len(self.private_key, 64)) +
                    '\n-----END RSA PRIVATE KEY-----\n');
                self.private_key_temp_file.flush()
                self.server.ssl_adapter = ssl_pyopenssl.pyOpenSSLAdapter(
                                              self.certificate_temp_file.name,
                                              self.private_key_temp_file.name,
                                              None)
                psi_web_patch.patch_ssl_adapter(self.server.ssl_adapter)
                # Blocks until server stopped
                syslog.syslog(syslog.LOG_INFO, 'started %s' % (self.ip_address,))
                self.server.start()
                break
            except (EnvironmentError,
                    EOFError,
                    SystemError,
                    ValueError,
                    ssl.SSLError,
                    socket.error) as e:
                # Log recoverable errors and try again
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                if self.server:
                    self.stop_server()
            except TypeError as e:
                trace = traceback.format_exc()
                for line in trace.split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                # Recover on this Cherrypy internal error
                # See bitbucket Issue 59
                if (str(e).find("'NoneType' object") == 0 and
                    trace.find("'SSL_PROTOCOL': cipher[1]") != -1):
                    if self.server:
                        self.stop_server()
                else:
                    raise
            except Exception as e:
                # Log other errors and abort
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                raise


# ===== GeoIP Service =====

class GeoIPServerInstance(object):

    @exception_logger
    def geoip(self, environ, start_response):
        request = Request(environ)
        geoip = psi_geoip.get_geoip(request.params['ip'])
        response_headers = [('Content-type', 'text/plain')]
        start_response('200 OK', response_headers)
        return [json.dumps(geoip)]


class GeoIPServerThread(threading.Thread):

    def __init__(self):
        #super(WebServerThread, self).__init__(self)
        threading.Thread.__init__(self)
        self.server = None

    def stop_server(self):
        # Retry loop in case self.server.stop throws an exception
        for i in range(5):
            try:
                if self.server:
                    # blocks until server stops
                    self.server.stop()
                    self.server = None
                break
            except Exception as e:
                # Log errors
                for line in traceback.format_exc().split('\n'):
                    syslog.syslog(syslog.LOG_ERR, line)
                time.sleep(i)

    def run(self):
        try:
            server_instance = GeoIPServerInstance()
            self.server = wsgiserver.CherryPyWSGIServer(
                            ('127.0.0.1', int(psi_config.GEOIP_SERVICE_PORT)),
                            wsgiserver.WSGIPathInfoDispatcher(
                                {'/geoip': server_instance.geoip}))

            # Blocks until server stopped
            syslog.syslog(syslog.LOG_INFO, 'started GeoIP service on port %d' % (psi_config.GEOIP_SERVICE_PORT,))
            self.server.start()
        except Exception as e:
            # Log other errors and abort
            for line in traceback.format_exc().split('\n'):
                syslog.syslog(syslog.LOG_ERR, line)
            raise


# ===== Main Process =====

def main():
    syslog.openlog(psi_config.SYSLOG_IDENT, syslog.LOG_NDELAY, psi_config.SYSLOG_FACILITY)
    threads = []
    servers = get_servers()
    # run a web server for each server entry
    # (presently web server-per-entry since each has its own certificate;
    #  we could, in principle, run one web server that presents a different
    #  cert per IP address)
    threads_per_server = 30 * multiprocessing.cpu_count()
    if '32bit' in platform.architecture():
        # Only 381 threads can run on 32-bit Linux
        # Assuming 361 to allow for some extra overhead, plus the additional overhead
        # of 1 main thread and 2 threads per web server
        threads_per_server = min(threads_per_server, 360 / len(servers) - 2)
    for server_info in servers:
        thread = WebServerThread(*server_info, server_threads=threads_per_server)
        thread.start()
        threads.append(thread)
    print 'Web servers running...'

    geoip_thread = GeoIPServerThread()
    geoip_thread.start()
    threads.append(geoip_thread)
    print 'GeoIP server running...'

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt as e:
        pass
    print 'Stopping...'

    for thread in threads:
        thread.stop_server()
        thread.join()


if __name__ == "__main__":
    main()
