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


import sys
import types
import re
import urllib
from apiclient.discovery import build
from config import config


###########################
# Helpers primarily used in templates
###########################

# To be used to format datetimes
def timestamp_display(timestamp):
    return '{:%Y-%m-%dT%H:%M:%S}.{:03}Z'.format(timestamp,
                                                timestamp.microsecond / 1000)


# Returns a tuple of (diff_float, diff_display_string). Arguments must be
# datetimes. `last_timestamp` may be None.
def get_timestamp_diff(last_timestamp, timestamp):
    timestamp_diff_secs = 0.0
    if last_timestamp:
        timestamp_diff_secs = (timestamp - last_timestamp).total_seconds()
    timestamp_diff_str = '{:.3f}'.format(timestamp_diff_secs)
    return (timestamp_diff_secs, timestamp_diff_str)


def urlencode(s):
    return urllib.quote_plus(s)


_languages = {}
def translate_message(msg):
    '''
    Translates msg to English. Returns a tuple of:
      (original-language-code, original-language-fullname, translated-msg)

    Special values: `original-language-code` may have the values:
      - "[INDETERMINATE]": If the language of `msg` can't be determined.
      - "[TRANSLATION_FAIL]": If the translation process threw an exception.
        In this case, `original-language-fullname` will have the exception message.
    '''

    global _languages

    TARGET_LANGUAGE = 'en'

    if not msg:
        return ('[EMPTY]', '[EMPTY]', '')

    service = build('translate', 'v2', developerKey=config['googleApiKey'])

    try:
        if not _languages:
            # Get the full set of possible languages
            langs = service.languages().list(target='en').execute()
            # Convert to a dict of {'lang_code': 'full_lang_name'}
            _languages = dict((lang['language'], lang['name']) for lang in langs['languages'])

        # Detect the language. We won't use the entire string, since we pay per
        # character, and the #characters-to-accuracy curve is probably logarithmic.
        lang_detect = service.detections().list(q=[msg[:100]]).execute()
        from_lang = lang_detect['detections'][0][0]['language']

        if from_lang not in _languages:
            # This probably means that the detection failed
            retval = ('[INDETERMINATE]', 'Language could not be determined', msg)
        elif from_lang != TARGET_LANGUAGE:
            # Translate the string.
            # TODO: There is a size limit on the REST API, but it is handled
            # within the Python library or do we need to break the string up here?
            # We can probably wait for an error to occur and then figure it out.
            trans = service.translations().list(source=from_lang, target=TARGET_LANGUAGE,
                                                format='text', q=[msg]).execute()
            msg_translated = trans['translations'][0]['translatedText']
            retval = (from_lang, _languages[from_lang], msg_translated)
        else:
            retval = (from_lang, _languages[from_lang], msg)

    except Exception as e:
        retval = ('[TRANSLATION_FAIL]', str(e), msg)

    return retval


###########################

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
        if path[-1] == 'ipAddress':
            server_id = None
            server = _psinet.get_server_by_ip_address(val)
            if server:
                server_id = server.id
            else:
                server = _psinet.get_deleted_server_by_ip_address(val)
                if server:
                    server_id = server.id + ' [DELETED]'

            # If the psinet DB is stale, we might not find the IP address, but
            # we still want to redact it.
            assign_value_to_obj_at_path(obj,
                                        path,
                                        server_id if server_id else '[UNKNOWN]')
        elif path[-1] == 'PROPAGATION_CHANNEL_ID':
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
