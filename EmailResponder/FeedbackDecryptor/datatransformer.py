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
import translation
from config import config


_locale_codes = json.load(open('locale_codes.json'))
_country_dialing_codes = json.load(open('country_dialing_codes.json'))


def _windows_1(data):
    if data.get('Feedback', {}).get('Message'):
        trans = translation.translate(config['googleApiServers'],
                                      config['googleApiKey'],
                                      data['Feedback']['Message']['text'])
        data['Feedback']['Message']['text_lang_code'] = trans[0]
        data['Feedback']['Message']['text_lang_name'] = trans[1]
        data['Feedback']['Message']['text_translated'] = trans[2]

    if data.get('Feedback', {}).get('Survey'):
        try:
            data['Feedback']['Survey']['results'] = json.loads(data['Feedback']['Survey']['json'])
        except:
            # Illegal JSON
            data['Feedback']['Survey']['results'] = None

    # Map numeric locale and country values to more human-usable values.
    os_info = data.get('DiagnosticInfo', {}).get('SystemInformation', {}).get('OSInfo')
    if os_info:
        locale_hex = int(os_info['locale'], 16)
        locale_match = [m for m in _locale_codes if m['lcid_number'] == locale_hex]
        os_info['LocaleInfo'] = locale_match[0] if locale_match else None

        language_match = [m for m in _locale_codes if m['lcid_number'] == os_info['language']]
        os_info['LanguageInfo'] = language_match[0] if language_match else None

        # Multiple countries can have the same dialing code (like Canada and
        # the US with 1), so CountryCodeInfo will be an array.
        country_match = [m for m in _country_dialing_codes if m['dialing_code'] == os_info['countryCode']]
        # Sometimes the countryCode as an additional digit. If we didn't get a
        # match, search again without the last digit.
        if not country_match:
            country_match = [m for m in _country_dialing_codes if m['dialing_code'] == os_info['countryCode'] / 10]
        os_info['CountryCodeInfo'] = country_match if country_match else None


_transformations = {
                    'windows_1': _windows_1
                    }


def transform(data):
    '''
    Effects any necessary modifications to the data before storage. Note that
    `data` is directly modified.
    Assumes that `data` has a "Metadata" value.
    An exception may be thrown if `data` is malformed.
    '''

    transform_key = '%s_%s' % (data['Metadata']['platform'],
                               data['Metadata']['version'])
    if transform_key in _transformations:
        _transformations[transform_key](data)
