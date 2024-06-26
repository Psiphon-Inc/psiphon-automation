# Copyright (c) 2014, Psiphon Inc.
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


from typing import Union, Optional
import sys
import types
import re
import urllib.parse
from datetime import datetime


import logger
import psi_ops_helpers


###########################
# Helpers primarily used in templates
###########################

def timestamp_display(timestamp: datetime) -> str:
    '''
    To be used to format datetimes
    '''
    return '{:%Y-%m-%dT%H:%M:%S}.{:03}Z'.format(timestamp,
                                                int(timestamp.microsecond / 1000))

def timestamp_display_test():
    assert(timestamp_display(datetime(2014, 1, 1, 12, 11, 22, 333456)) == '2014-01-01T12:11:22.333Z')
    assert(timestamp_display(datetime(2014, 1, 1, 12, 11, 22, 456)) == '2014-01-01T12:11:22.000Z')
    print('timestamp_display test okay')

timestamp_display.test = timestamp_display_test


def get_timestamp_diff(last_timestamp: datetime, timestamp: datetime) -> tuple[float, str]:
    '''
    Returns a tuple of (diff_float, diff_display_string). Arguments must be
    datetimes. `last_timestamp` may be None.
    '''
    timestamp_diff_secs = 0.0
    if last_timestamp:
        timestamp_diff_secs = (timestamp - last_timestamp).total_seconds()
    timestamp_diff_str = '{:.3f}'.format(timestamp_diff_secs)
    return (timestamp_diff_secs, timestamp_diff_str)


def get_timestamp_diff_test():
    dt1 = datetime(2014, 1, 1, 12, 11, 22, 333456)

    # Ordinary size of diff
    dt2 = datetime(2014, 1, 1, 12, 11, 23, 123456)
    assert(get_timestamp_diff(dt1, dt2) == (0.79, '0.790'))

    # Rounds up to 0.001
    dt2 = datetime(2014, 1, 1, 12, 11, 22, 333956)
    assert(get_timestamp_diff(dt1, dt2) == (0.0005, '0.001'))

    # Rounds down to 0.000
    dt2 = datetime(2014, 1, 1, 12, 11, 22, 333856)
    assert(get_timestamp_diff(dt1, dt2) == (0.0004, '0.000'))

    # Very big difference
    dt2 = datetime(2015, 1, 1, 12, 11, 22, 333456)
    assert(get_timestamp_diff(dt1, dt2) == (31536000.0, '31536000.000'))

    print('get_timestamp_diff test okay')

get_timestamp_diff.test = get_timestamp_diff_test


def urlencode(s: str) -> str:
    return urllib.parse.quote_plus(s)

def urlencode_test():
    assert(urlencode('abcd!@#$') == 'abcd%21%40%23%24')
    print('urlencode test okay')

urlencode.test = urlencode_test


def coalesce(obj: dict, key_path: Union[str, list], default_value: Optional[any]=None, required_types: Optional[Union[tuple[type],type]]=None):
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
    `required_types` is an optional tuple of types. If the target value does
    not match any of these types, `None` will be returned.
    '''

    if type(key_path) not in (list, tuple):
        key_path = [key_path]

    if required_types and type(required_types) == type:
        required_types = (required_types,)

    target_value = obj
    for key in key_path:
        if type(target_value) != dict:
            return default_value

        target_value = target_value.get(key, None)

        if target_value is None:
            return default_value

    if required_types and type(target_value) not in required_types:
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

    # Test required_types
    assert(coalesce({'a': 1}, 'a', default_value='nope', required_types=int) == 1)
    assert(coalesce({'a': 1}, 'a', default_value='nope', required_types=(int, str)) == 1)
    assert(coalesce({'a': 1}, 'a', default_value='nope', required_types=(str,)) == 'nope')

    print('coalesce test okay')

coalesce.test = coalesce_test


###########################

# Very rudimentary, but sufficient
ipv4_regex = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')

prop_channel_id_to_name = dict()
sponsor_id_to_name = dict()

def convert_psinet_values(config, obj):
    '''
    Converts sensitive or non-human-readable values in the YAML to IDs and
    names. Modifies the YAML directly.
    '''

    if isinstance(obj, str):
        return

    for path, val in objwalk(obj):

        if isinstance(val, str):

            #
            # Find IP addresses in the value and replace them.
            #

            split = re.split(ipv4_regex, val)

            # With re.split, the odd items are the matches.
            val_modified = False
            for i in range(1, len(split)-1, 2):
                # Leave localhost IP intact
                if split[i] != '127.0.0.1':
                    split[i] = psiphon_server_id_from_ip(split[i])
                    val_modified = True

            if val_modified:
                clean_val = ''.join(split)
                assign_value_to_obj_at_path(obj, path, clean_val)

        if path[-1] == 'PROPAGATION_CHANNEL_ID':
            prop_channel_name = prop_channel_id_to_name.get(val)
            if not prop_channel_name:
                prop_channel_name = psi_ops_helpers.get_propagation_channel_name_by_id(val)
                prop_channel_id_to_name[val] = prop_channel_name

            if prop_channel_name:
                assign_value_to_obj_at_path(obj,
                                            path,
                                            prop_channel_name)
        elif path[-1] == 'SPONSOR_ID':
            sponsor_name = sponsor_id_to_name.get(val)
            if not sponsor_name:
                sponsor_name = psi_ops_helpers.get_sponsor_name_by_id(val)
                sponsor_id_to_name[val] = sponsor_name

            if sponsor_name:
                assign_value_to_obj_at_path(obj,
                                            path,
                                            sponsor_name)


# Global cache used by psiphon_server_id_from_ip()
server_ip_to_id = dict()

def psiphon_server_id_from_ip(ip):
    '''
    Converts the given IP to the human-readable (and safe) ID used by psinet.
    Note: Not threadsafe.
    '''

    server_id = server_ip_to_id.get(ip)
    if server_id:
        return server_id

    # We haven't already cached this IP->ID, so fetch it.
    server_id = psi_ops_helpers.get_server_display_id_from_ip(ip)
    server_ip_to_id[ip] = server_id
    return server_id


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
                             'platform': lambda val: val in ['android', 'ios', 'ios-browser', 'ios-vpn', 'ios-vpn-on-mac', 'windows', 'inproxy'],
                             'version': lambda val: val in range(1, 5),
                             'id': lambda val: re.match(r'^[a-fA-F0-9]{16}', str(val)) is not None
                             },

                # These two fields are special in MongoDB and should not be
                # present in the diagnostic data package.
                '-_id': None,
                '-datetime': None,
                }

    if not _check_exemplar(obj, exemplar):
        logger.error('is_diagnostic_info_sane: exemplar fail')
        return False

    return True


def upgrade_diagnostic_info(diagnostic_info) -> None:
    '''
    Modifies diagnostic_info from older clients to match the structure expected from newer.
    Must be called after is_diagnostic_info_sane.
    '''

    # In early Psiphon clients, we didn't include the appName in the
    # diagnostic info (because Psiphon was the only app).
    # Note that is_diagnostic_info_sane will have ensured that Metadata is present.
    if diagnostic_info['Metadata'].get('platform') == 'inproxy':
        diagnostic_info['Metadata']['appName'] = 'inproxy'
    elif not diagnostic_info['Metadata'].get('appName'):
        diagnostic_info['Metadata']['appName'] = 'psiphon'

    # Early Psiphon clients nested SystemInformation, but now we want it at the top level.
    # We will leave it in both locations for now.
    if diagnostic_info.get('DiagnosticInfo', {}).get('SystemInformation') and not diagnostic_info.get('SystemInformation'):
        diagnostic_info['SystemInformation'] = diagnostic_info['DiagnosticInfo']['SystemInformation']


def is_diagnostic_info_sane_test():
    assert(not is_diagnostic_info_sane({}))
    assert(is_diagnostic_info_sane({'Metadata': {'platform': 'windows', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    assert(is_diagnostic_info_sane({'extra': 1, 'Metadata': {'extra': 1, 'platform': 'windows', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    assert(not is_diagnostic_info_sane({'_id': 1, 'Metadata': {'extra': 1, 'platform': 'windows', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    assert(not is_diagnostic_info_sane({'datetime': 1, 'Metadata': {'extra': 1, 'platform': 'windows', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    assert(not is_diagnostic_info_sane({'_id': 1, 'datetime': 1, 'Metadata': {'extra': 1, 'platform': 'windows', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    assert(not is_diagnostic_info_sane({'Metadata': {'platform': 'badplatform', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    assert(is_diagnostic_info_sane({'Metadata': {'_id': 1, 'platform': 'windows', 'version': 1, 'id': 'AAAAAAAAAAAAAAAA'}}))
    print('is_diagnostic_info_sane test okay')

is_diagnostic_info_sane.test = is_diagnostic_info_sane_test


def _check_exemplar(check, exemplar):
    '''
    If an `exemplar` dict key starts with '-', then it must *not* be present
    in `check`.
    '''

    if isinstance(exemplar, dict):
        if not isinstance(check, dict):
            return False

        for k in exemplar.keys():
            if k.startswith('-'):
                # Special negation key
                if k[1:] in check:
                    return False
            else:
                if k not in check:
                    return False

                if not _check_exemplar(check[k], exemplar[k]):
                    return False

        return True

    elif isinstance(exemplar, types.FunctionType):
        try:
            return exemplar(check)
        except:
            # Log the value that failed, but still raise it
            logger.error('Exemplar check failed for: %s' % str(check))
            raise

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

iteritems = lambda mapping: getattr(mapping, 'iteritems', mapping.items)()


def objwalk(obj, path=(), memo=None):
    """
    Iterates across all leaves of an object, yielding (path, value).
    The path is a tuple of the keys up to the value. For example:
        >>> for path, val in utils.objwalk({'a': 1, 'b': {'c': 2}}):
        ...   print(path, val)
        ('b', 'c') 2
        ('a',) 1

    This function operates on types that satisfy collections.Mapping, .Set, and .Sequence,
    such as dicts, sets, lists, and tuples.

    path and memo should have their default values on first call (they're used for
    recursive calls).

    Note: DO NOT modify the object's keys while iterating, or the iteration will be messed
    up. Instead, save the keys into a list, which you can then iterate and modify.
    """
    if obj is None:
        return

    if memo is None:
        memo = set()
    iterator = None
    if isinstance(obj, Mapping):
        iterator = iteritems
    elif isinstance(obj, (Sequence, Set)) and not isinstance(obj, str):
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
    logger.disable()

    for name_in_module in dir(sys.modules[__name__]):
        testee = getattr(sys.modules[__name__], name_in_module)

        if not hasattr(testee, 'test') or not hasattr(testee.test, '__call__'):
            continue

        testee.test()
