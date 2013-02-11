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


def _windows_1(data):
    if 'Feedback' in data and 'Message' in data['Feedback']:
        trans = translation.translate(config['googleApiServers'],
                                      config['googleApiKey'],
                                      data['Feedback']['Message']['text'])
        data['Feedback']['Message']['text_lang_code'] = trans[0]
        data['Feedback']['Message']['text_lang_name'] = trans[1]
        data['Feedback']['Message']['text_translated'] = trans[2]

    if 'Feedback' in data and 'Survey' in data['Feedback']:
        try:
            data['Feedback']['Survey']['results'] = json.loads(data['Feedback']['Survey']['json'])
        except:
            # Illegal JSON
            data['Feedback']['Survey']['results'] = None


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
