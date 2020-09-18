# Copyright (c) 2020, Psiphon Inc.
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


import sys
import types
import re
import json

import logger
import utils


def redact_sensitive_values(obj):
    '''
    Redacts any sensitive values present in the given diagnostic information.
    The leaves of the dictionary are searched and any sensitive values found
    are redacted by modifying the dictionary directly.
    '''

    if isinstance(obj, utils.string_types) or not isinstance(obj, types.DictType):
        return

    try:
        client_platform = obj["Metadata"]["platform"]
        sys_info = obj["DiagnosticInfo"]["SystemInformation"]
        client_version = sys_info["PsiphonInfo"]["CLIENT_VERSION"]
    except KeyError:
        return
    
    if isinstance(client_version, utils.string_types):
            try:
                client_version = int(client_version)
            except ValueError:
                return

    redactors_to_run = redactors(client_platform, client_version)
    run_redactors(obj, redactors_to_run)


def redact_sensitive_values_test():
    _redact_sensitive_values_all_clients_test()
    _redact_sensitive_values_ios_vpn_test()

    print 'redact_sensitive_values_test okay'

redact_sensitive_values.test = redact_sensitive_values_test


def _redact_sensitive_values_all_clients_test():
    # Test where a sensitive value is redacted

    # Map input log to expected log after redaction
    tests = {
        # test where no redaction should occur
        'UpstreamProxyError: {"message": "upstreamproxy error: handshake error: <nil>, response status: 403 Forbidden"}':
          'UpstreamProxyError: {"message": "upstreamproxy error: handshake error: <nil>, response status: 403 Forbidden"}',
        # simple test
        'UpstreamProxyError: {"message": "upstreamproxy error: proxyURI url.Parse: parse http:\/\/example.com: net\/url: invalid userinfo"}':
          'UpstreamProxyError: {"message": "upstreamproxy error: proxyURI url.Parse: parse <redacted>"}',
        # test nested JSON
        'UpstreamProxyError: {"message": {"nested_message": "upstreamproxy error: proxyURI url.Parse: parse http:\/\/example.com: net\/url: invalid userinfo"}}':
          'UpstreamProxyError: {"message": {"nested_message": "upstreamproxy error: proxyURI url.Parse: parse <redacted>"}}',
        # test extra JSON fields
        'UpstreamProxyError: {"message": "upstreamproxy error: proxyURI url.Parse: parse http:\/\/example.com: net\/url: invalid userinfo", "k": {"k1": "v1"}}':
          'UpstreamProxyError: {"message": "upstreamproxy error: proxyURI url.Parse: parse <redacted>", "k": {"k1": "v1"}}',
        # tests where we fallback on a destructive redaction
        'UpstreamProxyError: {"upstreamproxy error: proxyURI url.Parse: parse http:\/\/example.com: net\/url: invalid userinfo": "v"}':
          'UpstreamProxyError: {"upstreamproxy error: proxyURI url.Parse: parse <redacted>',
        'UpstreamProxyError: "upstreamproxy error: proxyURI url.Parse: parse http:\/\/example.com: net\/url: invalid userinfo"':
          'UpstreamProxyError: "upstreamproxy error: proxyURI url.Parse: parse <redacted>'
    }

    for log, expectedRedactedLog in tests.iteritems():
        obj = _generate_android_feedback(1, log)
        redact_sensitive_values(obj)
        expectedRedactedObj = _generate_android_feedback(1, expectedRedactedLog)
        assert(obj == expectedRedactedObj)

    print 'redact_sensitive_values_all_clients_test okay'


def _generate_android_feedback(client_version, msg):
    return _generate_feedback_scheme1("android", client_version, msg)


# Note: scheme should match ios-browser as well.
def _generate_ios_vpn_feedback(client_version, msg):
    return _generate_feedback_scheme1("ios-vpn", client_version, msg)


# Note: this scheme is shared between iOS and Android clients, but there is at
# least one other scheme used on Android.
def _generate_feedback_scheme1(client_platform, client_version, msg):
    return {
        "Metadata": {
            "platform": client_platform
        },
        "DiagnosticInfo": {
            "SystemInformation": {
                "PsiphonInfo": {
                    "CLIENT_VERSION": client_version
                },
            },
            "DiagnosticHistory": [
                {
                    "data": {
                        "msg": msg,
                    },
                    "msg": msg,
                    "timestamp": "",
                }
            ],
        },
    }


def _redact_sensitive_values_ios_vpn_test():

    # Test where a sensitive value is redacted

    log = 'ExtensionInfo: {"PacketTunnelProvider":{"Event":"Start","StartMethod":"Container","ExpectFieldToBeRedacted":{"ExpectFieldToBeRedacted":"ExpectValueToBeRedacted"}}}'

    obj = _generate_ios_vpn_feedback(171, log)
    redact_sensitive_values(obj)

    # The order of fields in the JSON string may change due to reserialization # during redaction.
    expectedOutputOrdering1 = _generate_ios_vpn_feedback(171, 'ExtensionInfo: {"PacketTunnelProvider": {"Event": "Start", "StartMethod": "Container"}}')
    expectedOutputOrdering2 = _generate_ios_vpn_feedback(171, 'ExtensionInfo: {"PacketTunnelProvider": {"StartMethod": "Container", "Event": "Start"}}')

    assert(obj == expectedOutputOrdering1 or
           obj == expectedOutputOrdering2)
    
    # Test where no redaction attempts are made based on the client version

    obj = _generate_ios_vpn_feedback(1, log)
    obj_copy = _generate_ios_vpn_feedback(1, log)
    redact_sensitive_values(obj)
    assert(obj == obj_copy)

    # Test where no redaction attempts are made based on the client platform

    obj = _generate_android_feedback(171, log)
    obj_copy = _generate_android_feedback(171, log)
    redact_sensitive_values(obj)
    assert(obj == obj_copy)

    print 'redact_sensitive_values_ios_vpn_test okay'


def redactors(client_platform, client_version):
    '''
    Return redactors to use for the target client platform and version.
    '''
    redactors = [_redact_upstream_proxy_errors]
    if client_platform == "ios-vpn" and client_version >= 160:
        redactors.append(_ios_vpn_redact_start_tunnel_with_options)
    return redactors


def run_redactors(obj, redactors):
    '''
    Traverse the object and perform any necessary redactions.
    '''
    for path, val in utils.objwalk(obj):
        for redactor in redactors:
            redactor(obj, path, val)

diagnostic_msg_regex = re.compile(r'([a-zA-Z]+): ({.*})')


def _redact_upstream_proxy_errors(obj, path, val):
    '''
    Redacts any text which follows the target upstream proxy error string.
    '''
    if isinstance(val, utils.string_types):

        target = "upstreamproxy error: proxyURI url.Parse: parse "

        index = val.find(target)
        if index == -1:
            return

        result = diagnostic_msg_regex.match(val)
        if result is not None:
            try:
                j = json.loads(result.group(2))
                found = _redact_target_from_dict(target, j)
                if found is True:
                    redacted_val = result.group(1) + ": " + json.dumps(j)
                    utils.assign_value_to_obj_at_path(obj, path, redacted_val)
                    return
            except ValueError:
                pass
       
        # Fallback on a less finessed redaction
        redacted_val = val[:index+len(target)] + "<redacted>"
        utils.assign_value_to_obj_at_path(obj, path, redacted_val)


def _redact_target_from_dict(target, d):
    '''
    Redact the target string from any values in the dictionary.
    Returns True if any values were redacted; otherwise, returns False.
    '''
    if isinstance(target, utils.string_types) is False:
        return False

    found = False

    for k, v in d.iteritems():
        if isinstance(v, utils.string_types):
            index = v.find(target)
            if index != -1:
                redacted_v = v[:index + len(target)] + "<redacted>"
                d[k] = redacted_v
                found = True
        elif isinstance(v, dict):
            if _redact_target_from_dict(target, v) is True:
                found = True
    
    return found


def _ios_vpn_redact_start_tunnel_with_options(obj, path, val):
    '''
    Redact target fields from startTunnelWithOptions log.
    See `_redact_sensitive_values_test()` for examples.
    '''
    if isinstance(val, utils.string_types):

        extensionInfoPrefix = "ExtensionInfo: "

        if val.find(extensionInfoPrefix) == 0:

            try:
                j = json.loads(val[len(extensionInfoPrefix):])
            except ValueError:
                return

            try:
                event = j["PacketTunnelProvider"]["Event"]

                if event == "Start":

                    redacted = _redact_start_tunnel_with_options(j["PacketTunnelProvider"])

                    if not _validate_start_tunnel_with_options(redacted):
                        # Invalid log, redact for safe measure.
                        utils.assign_value_to_obj_at_path(obj, path, "[REDACTED]")

                    else:
                        redacted_val = extensionInfoPrefix + json.dumps({"PacketTunnelProvider":redacted})
                        utils.assign_value_to_obj_at_path(obj, path, redacted_val)
                    
            except KeyError:
                return

            except TypeError:
                return


def _redact_start_tunnel_with_options(obj):
    '''
    Returns redacted dictionary which only contains non-sensitive fields.
    '''

    if not isinstance(obj, types.DictType):
        return None

    redacted = {}
    target_fields = ["Event", "StartMethod"]
    for field in target_fields:
        try:
            redacted[field] = obj[field]
        except KeyError:
            pass

    return redacted


def _redact_start_tunnel_with_options_test():

    assert(_redact_start_tunnel_with_options({'Event':'a'}) 
           == {'Event':'a'})
    assert(_redact_start_tunnel_with_options({'StartMethod':'b'})
           == {'StartMethod':'b'})
    assert(_redact_start_tunnel_with_options({'Event':'a', 'StartMethod':'b'}) 
           == {'Event':'a', 'StartMethod':'b'})
    assert(_redact_start_tunnel_with_options({'Event':'a',
                                              'StartMethod':'b', 'ExpectFieldToBeRedacted':'c'}) 
           == {'Event':'a', 'StartMethod':'b'})

    print '_redact_start_tunnel_with_options_test okay'

_redact_start_tunnel_with_options.test = _redact_start_tunnel_with_options_test


def _validate_start_tunnel_with_options(obj):
    '''
    Validate each key-value pair in the dictionary.
    '''

    if set(obj.keys()) != set(['Event', 'StartMethod']):
        return False

    exemplar = {
        'Event': lambda val: val == "Start",
        'StartMethod': lambda val: val in ['Container', 'Boot', 'Crash', 'Other']
    }

    return utils._check_exemplar(obj, exemplar)


def _validate_start_tunnel_with_options_test():
    
    assert(_validate_start_tunnel_with_options({'a':'b'}) == False)
    assert(_validate_start_tunnel_with_options({'Event':'Start'}) == False)
    assert(_validate_start_tunnel_with_options({'StartMethod':'Container'}) == False)
    assert(_validate_start_tunnel_with_options({'Event':'Stop', 'StartMethod':'Container'}) == False)
    assert(_validate_start_tunnel_with_options({'Event':'Start', 'StartMethod':'a'}) == False)
    assert(_validate_start_tunnel_with_options({'Event':'Start', 'StartMethod':'Container'}) == True)
    assert(_validate_start_tunnel_with_options({'Event':'Start', 'StartMethod':'Boot'}) == True)
    assert(_validate_start_tunnel_with_options({'Event':'Start', 'StartMethod':'Crash'}) == True)
    assert(_validate_start_tunnel_with_options({'Event':'Start', 'StartMethod':'Other'}) == True)
    assert(_validate_start_tunnel_with_options({'Event':'Start', 'StartMethod':'Container', 'UnexpectedField':'UnexpectedValue'}) == False)

    print '_validate_start_tunnel_with_test okay'

_validate_start_tunnel_with_options.test = _validate_start_tunnel_with_options_test


# TODO: proper unit test framework
def test():
    logger.disable()

    for name_in_module in dir(sys.modules[__name__]):
        testee = getattr(sys.modules[__name__], name_in_module)

        if not hasattr(testee, 'test') or not hasattr(testee.test, '__call__'):
            continue

        testee.test()
