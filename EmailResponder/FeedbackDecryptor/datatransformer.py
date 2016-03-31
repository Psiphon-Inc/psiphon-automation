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


import json
import datetime
import translation
import utils
from config import config


_locale_codes = json.load(open('locale_codes.json'))
_country_dialing_codes = json.load(open('country_dialing_codes.json'))


def _translate_feedback(data):
    if data.get('Feedback', {}).get('Message'):
        trans = translation.translate(config['googleApiServers'],
                                      config['googleApiKey'],
                                      data['Feedback']['Message']['text'])
        data['Feedback']['Message']['text_lang_code'] = trans[0]
        data['Feedback']['Message']['text_lang_name'] = trans[1]
        data['Feedback']['Message']['text_translated'] = trans[2]


def _parse_survey_results(data):
    if data.get('Feedback', {}).get('Survey'):
        try:
            data['Feedback']['Survey']['results'] = json.loads(data['Feedback']['Survey']['json'])
        except:
            # Illegal JSON
            data['Feedback']['Survey']['results'] = None


def _convert_locale_info(data):
    # Map numeric locale and country values to more human-usable values.
    os_info = data.get('DiagnosticInfo', {}).get('SystemInformation', {}).get('OSInfo')
    if os_info:
        if os_info.get('locale'):
            locale_hex = int(str(os_info['locale']), 16)
            locale_match = [m for m in _locale_codes if m['lcid_number'] == locale_hex]
            os_info['LocaleInfo'] = locale_match[0] if locale_match else None

        if os_info.get('language'):
            language_match = [m for m in _locale_codes if m['lcid_number'] == os_info['language']]
            os_info['LanguageInfo'] = language_match[0] if language_match else None

        if os_info.get('countryCode'):
            # Multiple countries can have the same dialing code (like Canada and
            # the US with 1), so CountryCodeInfo will be an array.
            country_match = [m for m in _country_dialing_codes if str(m['dialing_code']) == str(os_info['countryCode'])]
            # Sometimes the countryCode has an additional digit. If we didn't get a
            # match, search again without the last digit.
            if not country_match:
                country_match = [m for m in _country_dialing_codes if str(m['dialing_code']) == str(os_info['countryCode'])[:-1]]
            os_info['CountryCodeInfo'] = country_match if country_match else None


_transformations = {
                    'windows': (_translate_feedback, _parse_survey_results,
                                _convert_locale_info),
                    'android_4': (_translate_feedback, _parse_survey_results,
                                _convert_locale_info),
                    }


def _postprocess_yaml(data):
    '''
    This function is a hack to let us use datetimes in JSON-formatted feedback
    objects. Otherwise the datetimes will remain strings after loading the YAML.
    Modifies the YAML object directly.
    It's also used for any other YAML massaging.
    '''

    TIMESTAMP_SUFFIX = '!!timestamp'

    # First just collect the paths to change, so we're not modifying while
    # walking the object (which might risk the walk changing...?).
    timestamps = [(path, val) for path, val in utils.objwalk(data)
                  if str(path[-1]).endswith(TIMESTAMP_SUFFIX)]

    # Replace the timestamp strings with actual datetimes and change the key name.
    for path, val in timestamps:
        new_path = list(path[:-1])
        new_path.append(path[-1][:path[-1].rindex(TIMESTAMP_SUFFIX)])
        new_val = datetime.datetime.strptime(val, '%Y-%m-%dT%H:%M:%S.%fZ')
        utils.rename_key_in_obj_at_path(data, path, new_path[-1])
        utils.assign_value_to_obj_at_path(data, new_path, new_val)

    #
    # Fix integer-looking IDs
    #
    # If a hex ID happens to have all numbers, YAML will decode it as an
    # integer rather than a string. This could mess up processing later on.
    _ensure_field_is_string(str, data, ('Metadata', 'id'))

    # Fix data type of other fields.
    # For example, if just a number is entered in the feedback text, it should
    # still be interpreted as a string.
    _ensure_field_is_string(unicode, data, ('Feedback', 'email'))
    _ensure_field_is_string(unicode, data, ('Feedback', 'Message', 'text'))


def _ensure_field_is_string(stringtype, data, fieldpath):
    prev_val = utils.coalesce(data, fieldpath)
    if prev_val is not None:
        utils.assign_value_to_obj_at_path(data, fieldpath, stringtype(prev_val))


def transform(data):
    '''
    Effects any necessary modifications to the data before storage. Note that
    `data` is directly modified.
    Assumes that `data` has a "Metadata" value.
    An exception may be thrown if `data` is malformed.
    '''

    _postprocess_yaml(data)

    transform_keys = set((data['Metadata']['platform'],))
    transform_keys.add('%s_%s' % (data['Metadata']['platform'],
                                  data['Metadata']['version']))

    for key in transform_keys.intersection(_transformations.keys()):
        for transformation in _transformations[key]:
            transformation(data)
