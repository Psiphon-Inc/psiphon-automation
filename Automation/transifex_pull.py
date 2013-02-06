#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

'''
Pulls and massages our translations from Transifex.
'''

import shutil
import json
from collections import Set, Sequence
import codecs
import requests

import psi_feedback_templates


# Must be of the form:
# {"username": ..., "password": ...}
config = json.loads(open('./transifex_conf.json').read())

# There should be no more or fewer Transifex resources than this. Otherwise
# one or the other needs to be updated.
known_resources = \
    ['android-app-strings', 'android-app-browser-strings',
     'user-documentation', 'email-template-strings',
     'feedback-template-strings', 'android-library-strings']


def process_android_app_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh'}
    process_resource('android-app-strings',
                     lambda lang: '../Android/PsiphonAndroid/res/values-%s/strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_android_library_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh'}
    process_resource('android-library-strings',
                     lambda lang: '../Android/PsiphonAndroidLibrary/res/values-%s/strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_android_app_browser_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh'}
    process_resource('android-app-browser-strings',
                     lambda lang: '../Android/zirco-browser/res/values-%s/strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_user_documentation():
    process_resource('user-documentation',
                     lambda lang: './DownloadSite/%s.html' % lang,
                     html_doctype_add,
                     bom=True)


def process_email_template_strings():
    process_resource('email-template-strings',
                     lambda lang: './TemplateStrings/%s.yaml' % lang,
                     yaml_lang_change,
                     bom=False)


def process_feedback_template_strings():
    process_resource('feedback-template-strings',
                     lambda lang: './FeedbackSite/Templates/%s.yaml' % lang,
                     yaml_lang_change,
                     bom=False)

    # Regenerate the HTML file
    psi_feedback_templates.make_feedback_html()

    # Copy the HTML file to where it needs to be
    shutil.copy2('./FeedbackSite/feedback.html',
                 '../Client/psiclient/feedback.html')
    shutil.copy2('./FeedbackSite/feedback.html',
                 '../Android/PsiphonAndroid/assets/feedback.html')


def process_resource(resource, output_path_fn, output_mutator_fn, bom, langs=None):
    '''
    `output_path_fn` must be callable. It will be passed the language code and
    must return the path+filename to write to.
    `output_mutator_fn` must be callable. It will be passed the output and the
    current language code. May be None.
    '''
    if not langs:
        langs = {'ar': 'ar', 'az': 'az', 'es': 'es', 'fa': 'fa', 'kk': 'kk',
                 'ru': 'ru', 'th': 'th', 'tk': 'tk', 'vi': 'vi', 'zh': 'zh',
                 'ug': 'ug@Latn'}

        # TODO: Mapping the same thing to different character sets makes no
        # sense. This needs to get sorted out in the near future.
        langs['uz'] = ('uz@Latn', 'uz@cyrillic')

    for in_lang, out_lang in langs.items():
        r = request('resource/%s/translation/%s' % (resource, in_lang))

        if not is_arrayish(out_lang):
            out_lang = [out_lang]

        for out_lang_entry in out_lang:
            if output_mutator_fn:
                # Transifex doesn't support the special character-type
                # modifiers we need for some languages,
                # like 'ug' -> 'ug@Latn'. So we'll need to hack in the
                # character-type info.
                content = output_mutator_fn(r['content'], out_lang_entry)
            else:
                content = r['content']

            # Make line endings consistently Unix-y.
            content = content.replace('\r\n', '\n')

            output_path = output_path_fn(out_lang_entry)
            with codecs.open(output_path, 'w', 'utf-8') as f:
                if bom:
                    f.write(u'\uFEFF')
                f.write(content)


def check_resource_list():
    r = request('resources')
    available_resources = [res['slug'] for res in r]
    available_resources.sort()
    known_resources.sort()
    return available_resources == known_resources


def request(command, params=None):
    url = 'https://www.transifex.com/api/2/project/Psiphon3/' + command + '/'
    r = requests.get(url, params=params,
                     auth=(config['username'], config['password']))
    if r.status_code != 200:
        raise Exception('Request failed with code %d: %s' %
                            (r.status_code, url))
    return r.json()


def yaml_lang_change(in_yaml, to_lang):
    return to_lang + in_yaml[in_yaml.find(':'):]


def html_doctype_add(in_html, to_lang):
    return '<!DOCTYPE html>\n' + in_html


def is_arrayish(obj):
    string_types = (str, unicode) if str is bytes else (str, bytes)
    return isinstance(obj, (Sequence, Set)) \
           and not isinstance(obj, string_types)


def go():
    if check_resource_list():
        print('Known and available resources match')
    else:
        raise Exception('Known and available resources do not match')

    process_user_documentation()
    print('process_user_documentation: DONE')

    process_feedback_template_strings()
    print('process_feedback_template_strings: DONE')

    process_email_template_strings()
    print('process_email_template_strings: DONE')

    process_android_app_strings()
    print('process_android_app_strings: DONE')

    process_android_library_strings()
    print('process_android_library_strings: DONE')

    process_android_app_browser_strings()
    print('process_android_app_browser_strings: DONE')


if __name__ == '__main__':
    print('NOTE: must be executed from Automation directory')
    go()
    print('FINISHED')
