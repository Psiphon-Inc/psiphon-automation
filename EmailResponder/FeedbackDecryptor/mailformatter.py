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


import datetime
import sys

from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions
import pynliner

import logger


_cached_templates = {}


def format(data):
    '''
    Will throw exception if data does not match expected structure (that is,
    if the template rendering fails).
    '''

    # The values in `data` come directly from the user, so we shouldn't trust
    # them enough to put them directly in to a filename.

    if data['Metadata']['appName'] == 'ryve':
        app_name = 'ryve'
    elif data['Metadata']['appName'] == 'conduit':
        app_name = 'conduit'
    elif data['Metadata']['appName'] == 'psiphon4':
        app_name = 'psiphon4'
    else:
        app_name = 'psiphon'

    if data['Metadata']['platform'] == 'windows':
        platform = 'windows'
    elif data['Metadata']['platform'] == 'ios': # legacy catch all
        platform = 'ios'
    elif data['Metadata']['platform'] == 'ios-browser':
        platform = 'ios'
    elif data['Metadata']['platform'] == 'ios-vpn':
        platform = 'ios'
    elif data['Metadata']['platform'] in ['ios-vpn-on-mac', 'ios-app-on-mac']:
        platform = 'ios-app-on-mac'
    elif data['Metadata']['platform'] == 'macos':
        platform = 'macos'
    else:
        platform = 'android'

    version = int(data['Metadata']['version'])

    template_filenames = (
        'templates/template_%s_%s_%d.mako' % (app_name, platform, version),
        'templates/template_%s_%d.mako' % (app_name, version),
    )

    for template_filename in template_filenames:
        if template_filename not in _cached_templates:
            template_lookup = TemplateLookup(directories=['.'])

            # SECURITY IMPORTANT: `'h'` in the `default_filters` list causes HTML
            # escaping to be applied to all expression tags (${...}) in this
            # template. Because we're outputting untrusted user-supplied data, this is
            # essential.
            try:
                _cached_templates[template_filename] = Template(filename=template_filename,
                                                                default_filters=['str', 'h'],
                                                                lookup=template_lookup)
            except FileNotFoundError:
                # This template doesn't exist; try the next one
                continue

        # We found our template
        break

    if template_filename not in _cached_templates:
        raise Exception('No suitable template found for %s' % data['Metadata'])

    try:
        rendered = _cached_templates[template_filename].render(data=data)
    except:
        raise Exception(exceptions.text_error_template().render())

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    return rendered


def _generate_psiphon4_v2_feedback(platform, message, extra_blocks=None):
    '''
    A Psiphon 4 feedback report v2, camelCase throughout, as the client uploads
    it, then put through the two intake steps that reshape what the template
    reads: `utils.normalize_lowercase_envelope` and
    `datatransformer._postprocess_yaml`. Replaying those rather than hardcoding
    their output keeps the fixture from drifting from what `format` receives.
    The other intake steps are not replayed: translation needs the network and
    the psinet lookup needs psinet, redaction only rewrites string leaves, and
    `_sanitize_keys` only touches keys containing a dot, which this fixture has
    none of.
    `message` is the feedback message object, including any translation fields
    `datatransformer._translate_feedback` would have added to it in place.
    '''

    # Deferred: this is fixture-only, and datatransformer pulls in translation
    # and requests. Importing at module scope would add those to mailsender's
    # import graph in production for no reason.
    import utils
    import datatransformer

    data = {
        'metadata': {
            'appName': 'psiphon4',
            'platform': platform,
            'version': 2,
            'id': 'A1B2C3D4E5F60718',
            'date!!timestamp': '2026-09-02T10:00:00.000Z',
        },
        'system': {
            'device': {'model': 'iPhone16,2', 'localizedModel': 'iPhone'},
            'os': {'name': 'iOS', 'version': '26.0'},
            'locale': 'fa-IR',
            'networkType': 'cellular',
            'jailbreakDetected': False,
        },
        'app': {
            'appId': 'ca.psiphon.psiphon4',
            'version': '2.5.2',
            'buildNumber': '46',
            'buildMode': 'release',
            'internalTest': True,
            'locale': 'fa',
            'gitDescribe': 'v2.5.2-3-gabcdef0',
            'propagationChannelId': 'ExamplePropagationChannel',
            'sponsorId': 'ExampleSponsor',
            'tunnelCore': {'buildRev': 'abcdef0', 'goVersion': 'go1.24'},
        },
        'logs': [
            {
                'timestamp!!timestamp': '2026-09-02T09:59:00.000Z',
                'category': 'tunnel-core',
                'data': {'noticeType': 'ConnectedServer', 'data': {'ipAddress': 'server-1'}},
            },
            {
                'timestamp!!timestamp': '2026-09-02T09:59:15.000Z',
                'category': 'tunnel-core',
                'data': {'noticeType': 'Info', 'data': {'message': 'sole message field'}},
            },
            {
                'timestamp!!timestamp': '2026-09-02T09:59:30.000Z',
                'category': 'native',
                'level': 'Info',
                'message': 'tunnel connected',
                'data': {'tag': 'VPNManager'},
            },
            {
                'timestamp!!timestamp': '2026-09-02T09:59:31.000Z',
                'category': 'frontend',
                'level': 'Debug',
                'message': 'should be skipped',
                'data': {'tag': 'HomeScreen'},
            },
        ],
        'feedback': {'message': message},
    }

    if extra_blocks:
        data.update(extra_blocks)

    utils.normalize_lowercase_envelope(data)
    datatransformer._postprocess_yaml(data)

    return data


def format_test():
    # A report with a translated message, no diagnostics block.
    data = _generate_psiphon4_v2_feedback(
        'ios',
        {'text': 'کار نمی\u200cکند', 'text_lang_code': 'fa',
         'text_lang_name': 'Persian', 'text_translated': 'does not work'})

    assert('metadata' not in data and 'feedback' not in data)
    assert(isinstance(data['Metadata']['date'], datetime.datetime))
    assert(isinstance(data['logs'][0]['timestamp'], datetime.datetime))

    rendered = format(data)
    assert('Psiphon 4' in rendered)
    assert('does not work' in rendered)
    assert('Auto-translated from Persian' in rendered)
    # Asserting on the notice type alone would also pass if log_row dumped the
    # whole entry, so require that the key itself is absent.
    assert('ConnectedServer' in rendered)
    assert('noticeType' not in rendered)
    assert('tunnel connected' in rendered)
    # A single-field payload is promoted out of its dict repr; a payload with
    # more than one key is still dumped whole.
    assert('sole message field' in rendered)
    # Compare against tag-stripped, unescaped text: the rendered repr has its
    # quotes HTML-escaped, and the promoted values contain the key names.
    import html as html_module
    import re as re_module
    logs_text = html_module.unescape(
        re_module.sub('<[^>]+>', ' ', rendered.split('Logs')[-1]))
    assert('sole message field' in logs_text and "{'message'" not in logs_text)
    assert('VPNManager' in logs_text and "{'tag'" not in logs_text)
    # A payload with a key we do not promote is still dumped whole.
    assert("{'ipAddress': 'server-1'}" in logs_text)
    # Trace and debug lines are below the threshold we print.
    assert('should be skipped' not in rendered)
    assert('ExampleSponsor' in rendered)
    assert('v2.5.2-3-gabcdef0' in rendered)
    assert('Jailbreak detected' in rendered)

    # A diagnostics-only report from Android.
    data = _generate_psiphon4_v2_feedback(
        'android', {},
        {'diagnostics': {'crashHistory': ['panic: example']},
         'system': {
             'device': {'brand': 'google', 'manufacturer': 'Google', 'model': 'Pixel 9'},
             'os': {'version': '16', 'sdkInt': 36},
             'locale': 'en-CA',
             'networkType': 'wifi',
             'rootDetected': False,
         }})
    rendered = format(data)
    assert('panic: example' in rendered)
    assert('Root detected' in rendered)
    assert('Jailbreak detected' not in rendered)
    # brand and manufacturer differ only in case on Pixel hardware. The first
    # assertion catches a dedupe failure, which would read "Google google
    # Pixel 9"; the second catches brand winning over the better-cased
    # manufacturer.
    assert('Google Pixel 9' in rendered)
    assert('google Pixel 9' not in rendered)

    # A timestamp _postprocess_yaml cannot parse stays a string under its
    # original key. The render must survive it.
    unparsed = '2026-09-02T09:59:00+00:00'
    data = _generate_psiphon4_v2_feedback(
        'ios', {'text': 'hello'},
        {'logs': [{'timestamp!!timestamp': unparsed,
                   'category': 'native',
                   'level': 'Info',
                   'message': 'odd timestamp',
                   'data': {'tag': 'VPNManager'}}]})
    assert(data['logs'][0]['timestamp!!timestamp'] == unparsed)
    rendered = format(data)
    assert(unparsed in rendered)
    assert('odd timestamp' in rendered)

    print('mailformatter format test okay')


format.test = format_test


# TODO: proper unit test framework
def test():
    logger.disable()

    for name_in_module in dir(sys.modules[__name__]):
        testee = getattr(sys.modules[__name__], name_in_module)

        if not hasattr(testee, 'test') or not hasattr(testee.test, '__call__'):
            continue

        testee.test()
