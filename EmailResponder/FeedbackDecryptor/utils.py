# Copyright (c) 2013, Psiphon Inc.
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
import urllib

import logger


###########################
# Helpers primarily used in templates
###########################

def timestamp_display(timestamp):
    '''
    To be used to format datetimes
    '''
    return '{:%Y-%m-%dT%H:%M:%S}.{:03}Z'.format(timestamp,
                                                timestamp.microsecond / 1000)


def get_timestamp_diff(last_timestamp, timestamp):
    '''
    Returns a tuple of (diff_float, diff_display_string). Arguments must be
    datetimes. `last_timestamp` may be None.
    '''
    timestamp_diff_secs = 0.0
    if last_timestamp:
        timestamp_diff_secs = (timestamp - last_timestamp).total_seconds()
    timestamp_diff_str = '{:.3f}'.format(timestamp_diff_secs)
    return (timestamp_diff_secs, timestamp_diff_str)


def urlencode(s):
    return urllib.quote_plus(s)


def safe_str(ex):
    '''
    Intended primarily to be used with exceptions. Calling `str(ex)` (on
    Linx) will throw an exception if the string representation of `ex` contains
    Unicode. This function will safely give a UTF-8 representation.
    '''
    return unicode(ex).encode('utf8')


def coalesce(obj, key_path, default_value=None):
    '''
    Looks at the chain of dict values of `obj` indicated by `key_path`. If a
    key doesn't exist or a value is None, then `default_value` will be
    returned, otherwise the target value will be returned.
    `default_value` will also be returned if one of the values along `key_path`
    is not a dict.
    `obj` must be a dict.
    `key_path` must be a possible dict key (e.g., string) or an array of
    possible dict keys.
    `default_value` will be returned if the target value is non-existent or None.
    '''

    if type(key_path) not in (list, tuple):
        key_path = [key_path]

    target_value = obj
    for key in key_path:
        if type(target_value) != dict:
            return default_value

        target_value = target_value.get(key, None)

        if target_value is None:
            return default_value

    return target_value


def coalesce_test():
    assert(coalesce(None, 'a') == None)
    assert(coalesce({}, 'a') == None)
    assert(coalesce({'a': 1}, 'a') == 1)
    assert(coalesce({'a': 1}, '') == None)
    assert(coalesce({'a': 1}, 'b', 'nope') == 'nope')
    assert(coalesce({'a': {'aa': 11}, 'b': 2}, ['a', 'aa'], 'nope') == 11)
    assert(coalesce({'a': {'aa': 11}, 'b': 2}, ['a', 'bb'], 'nope') == 'nope')
    assert(coalesce({'a': {'aa': 11}, 'b': 2}, ['a', 'aa', 'aaa'], 'nope') == 'nope')
    assert(coalesce({'a': {'aa': 11}, 'b': 2}, ('a', 'aa'), 'nope') == 11)
    print 'coalesce test okay'

coalesce.test = coalesce_test


###########################

def _get_server_id_from_ip(psinet, ip):
    server_id = None
    server = psinet.get_server_by_ip_address(ip)
    if server:
        server_id = '[%s]' % server.id
    else:
        server = psinet.get_deleted_server_by_ip_address(ip)
        if server:
            server_id = '[%s][DELETED]' % server.id

    # If the psinet DB is stale, we might not find the IP address, but
    # we still want to redact it.
    return server_id if server_id else '[UNKNOWN]'


# Very rudimentary, but sufficient
ipv4_regex = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')


_psinet = None
def convert_psinet_values(config, obj):
    '''
    Converts sensitive or non-human-readable values in the YAML to IDs and
    names. Modifies the YAML directly.
    '''

    global _psinet
    if not _psinet:
        # Load the psinet DB
        sys.path.append(config['psiOpsPath'])
        import psi_ops
        _psinet = psi_ops.PsiphonNetwork.load_from_file(config['psinetFilePath'])

    if isinstance(obj, string_types):
        return

    for path, val in objwalk(obj):

        if type(val) == str:
            # Find any/all IP addresses in the value and replace them.
            split = re.split(ipv4_regex, val)

            # With re.split, the odd items are the matches.
            val_modified = False
            for i in range(1, len(split)-1, 2):
                # Leave localhost IP intact
                if split[i] != '127.0.0.1':
                    split[i] = _get_server_id_from_ip(_psinet, split[i])
                    val_modified = True

            if val_modified:
                clean_val = ''.join(split)
                assign_value_to_obj_at_path(obj, path, clean_val)

        if path[-1] == 'PROPAGATION_CHANNEL_ID':
            propagation_channel = _psinet.get_propagation_channel_by_id(val)
            if propagation_channel:
                assign_value_to_obj_at_path(obj,
                                            path,
                                            propagation_channel.name)
        elif path[-1] == 'SPONSOR_ID':
            sponsor = _psinet.get_sponsor_by_id(val)
            if sponsor:
                assign_value_to_obj_at_path(obj,
                                            path,
                                            sponsor.name)


def is_diagnostic_info_sane(obj):
    '''
    Returns true if `obj` is a sane-looking diagnostic info object.
    '''
    # TODO: Add better, more comprehensive checks.
    # TODO: Need to implement per-version, per-platform checks.
    # TODO: Having to increase the sane version range every time the version
    #       changes (and per-platform) is going to cause problems.

    if not isinstance(obj, object):
        return False

    exemplar = {
                'Metadata': {
                             'platform': lambda val: val in ['android', 'windows'],
                             'version': lambda val: val in range(1, 3),
                             'id': lambda val: re.match(r'^[a-fA-F0-9]{16}', val) is not None
                             }
                }

    if not _check_exemplar(obj, exemplar):
        logger.error('is_diagnostic_info_sane: exemplar fail')
        return False

    return True


def _check_exemplar(check, exemplar):
    if isinstance(exemplar, types.DictType):
        if not isinstance(check, types.DictType):
            return False

        for k in exemplar.iterkeys():
            if not k in check:
                return False

            if not _check_exemplar(check[k], exemplar[k]):
                return False

        return True

    elif isinstance(exemplar, types.FunctionType):
        return exemplar(check)

    elif exemplar is None:
        return True

    else:
        # We don't support whatever this is
        assert(False)
        return False

    # Should have hit an exit condition above
    assert(False)


###
# From http://code.activestate.com/recipes/577982-recursively-walk-python-objects/
###

from collections import Mapping, Set, Sequence

# dual python 2/3 compatability, inspired by the "six" library
string_types = (str, unicode) if str is bytes else (str, bytes)
iteritems = lambda mapping: getattr(mapping, 'iteritems', mapping.items)()


def objwalk(obj, path=(), memo=None):
    if memo is None:
        memo = set()
    iterator = None
    if isinstance(obj, Mapping):
        iterator = iteritems
    elif isinstance(obj, (Sequence, Set)) and not isinstance(obj, string_types):
        iterator = enumerate
    if iterator:
        if id(obj) not in memo:
            memo.add(id(obj))
            for path_component, value in iterator(obj):
                for result in objwalk(value, path + (path_component,), memo):
                    yield result
            memo.remove(id(obj))
    else:
        yield path, obj


def assign_value_to_obj_at_path(obj, obj_path, value):
    if not obj or not obj_path:
        return

    target = obj
    for k in obj_path[:-1]:
        target = target[k]
    target[obj_path[-1]] = value


def rename_key_in_obj_at_path(obj, obj_path, new_key):
    if not obj or not obj_path:
        return

    target = obj
    for k in obj_path[:-1]:
        target = target[k]

    # Copy the old value to the new key
    target[new_key] = target[obj_path[-1]]
    # Delete the old key
    del target[obj_path[-1]]


####################


# TODO: proper unit test framework
def test():
    for name_in_module in dir(sys.modules[__name__]):
        testee = getattr(sys.modules[__name__], name_in_module)

        if not hasattr(testee, 'test') or not hasattr(testee.test, '__call__'):
            continue

        testee.test()
