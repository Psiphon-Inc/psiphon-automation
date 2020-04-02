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

import string
import os
import sys
import pam
import GeoIP
import syslog
import traceback
import redis
import json
import socket
import urllib
import urllib2
import psi_config

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Automation')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Automation')))
import psi_ops_discovery

plugins = []
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Plugins'))
    import psi_server_plugins
    for (path, plugin) in psi_server_plugins.PSI_AUTH_PLUGINS:
        sys.path.insert(0, path)
        plugins.append(__import__(plugin))
except ImportError as error:
    print error
    
    
def handle_auth(pam_user, pam_rhost):

    # Read parameters tunneled through password field

    authtok = sys.stdin.readline().rstrip()[:-1]

    auth_params = None
    try:
        auth_params = json.loads(authtok)
        session_id = auth_params['SessionId']
        password = auth_params['SshPassword']
    except (ValueError, KeyError) as e:

        # Backwards compatibility case
        # Client sends a session ID prepended to the SSH password.
        # Extract the sesssion ID, and then perform standard PAM
        # authentication with the username and remaining password.
        # Older backwards compatibility case: if the password length is
        # not correct, skip the session ID logic.

        # Two hex characters per byte
        expected_authtok_length = (
            2*(psi_config.SESSION_ID_BYTE_LENGTH +
               psi_config.SSH_PASSWORD_BYTE_LENGTH))
            
        if len(authtok) == expected_authtok_length:
            session_id = authtok[0:psi_config.SESSION_ID_BYTE_LENGTH*2]
            password = authtok[psi_config.SESSION_ID_BYTE_LENGTH*2:]
            if 0 != len(filter(lambda x : x not in psi_config.SESSION_ID_CHARACTERS, session_id)):
                return False
        else:

            # Older backwards compatibility case
            session_id = None
            password = authtok

    # Authenticate user

    try:
        pam.authenticate(pam_user, password)
    except pam.PamException as e:
        return False

    # Call 'auth' plugins

    for plugin in plugins:
        if hasattr(plugin, 'auth') and not plugin.auth(auth_params):
            return False

    # Store session_id/region mapping for stats

    if session_id:
        set_session_region(pam_rhost, session_id)

    return True


def set_session_region(pam_rhost, session_id):

    # TODO: make this a plugin

    # Determine the user's region by client IP address and store
    # it in a lookup database keyed by session ID.

    # Request GeoIP lookup from web service, which has a cached database
    try:
        request = 'http://127.0.0.1:%d/geoip?ip=%s' % (psi_config.GEOIP_SERVICE_PORT, pam_rhost)
        geoip = json.loads(urllib2.urlopen(request, timeout=1).read())
    except urllib2.URLError:
        # No GeoIP info when the web service doesn't response, but proceed with tunnel...
        # TODO: load this value from psi_geoip.get_unknown(), without incurring overhead
        # of loading psi_geoip
        geoip = {'region': 'None', 'city': 'None', 'isp': 'None'}

    redis_session = redis.StrictRedis(
            host=psi_config.SESSION_DB_HOST,
            port=psi_config.SESSION_DB_PORT,
            db=psi_config.SESSION_DB_INDEX)

    if redis_session.get(session_id) == None:
        redis_session.set(session_id, json.dumps(geoip))
        redis_session.expire(session_id, psi_config.SESSION_EXPIRE_SECONDS)

    # Now fill in the discovery database
    # NOTE: We are storing a value derived from the user's IP address
    # to be used by the discovery algorithm done in handshake when
    # the web request is made through the SSH/SSH+ tunnel
    # This is potentially PII.  We have a short (5 minute) expiry on
    # this data, and it will also be discarded immediately after use
    try:
        client_ip_address_strategy_value = psi_ops_discovery.calculate_ip_address_strategy_value(pam_rhost)
        redis_discovery = redis.StrictRedis(
                host=psi_config.DISCOVERY_DB_HOST,
                port=psi_config.DISCOVERY_DB_PORT,
                db=psi_config.DISCOVERY_DB_INDEX)

        if redis_discovery.get(session_id) == None:
            redis_discovery.set(session_id, json.dumps({'client_ip_address_strategy_value' : client_ip_address_strategy_value}))
            redis_discovery.expire(session_id, psi_config.DISCOVERY_EXPIRE_SECONDS)
    except socket.error:
        pass


def handle_close_session(pam_user, pam_rhost):

    # Call 'close_session' plugins

    for plugin in plugins:
        if hasattr(plugin, 'close_session') and not plugin.close_session():
            return False

    return True


def main():
    try:
        pam_user = os.environ['PAM_USER']
        pam_rhost = os.environ['PAM_RHOST']
        pam_type = os.environ['PAM_TYPE']

        # Only apply this logic to the 'psiphon' user accounts;
        # system accounts still use normal authentication stack.

        if not pam_user.startswith('psiphon'):
            sys.exit(1)

        result = False

        if pam_type == 'auth':
            result = handle_auth(pam_user, pam_rhost)
        elif pam_type == 'close_session':
            result = handle_close_session(pam_user, pam_rhost)

        if not result:
            sys.exit(1)

    except Exception as e:
        for line in traceback.format_exc().split('\n'):
            syslog.syslog(syslog.LOG_ERR, line)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    syslog.openlog(psi_config.SYSLOG_IDENT, syslog.LOG_NDELAY, psi_config.SYSLOG_FACILITY)
    main()

