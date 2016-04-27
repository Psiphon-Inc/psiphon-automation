#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2016, Psiphon Inc.
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

import os
import errno
import shutil
import json
import codecs
import requests
from BeautifulSoup import BeautifulSoup

import psi_feedback_templates


DEFAULT_LANGS = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'kk': 'kk',
                 'ru': 'ru', 'th': 'th', 'tk': 'tk', 'vi': 'vi', 'zh': 'zh',
                 'ug': 'ug@Latn', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr',
                 'de': 'de', 'ko': 'ko', 'fi_FI': 'fi', 'el_GR': 'el',
                 'hr': 'hr', 'pt_PT': 'pt_PT', 'pt_BR': 'pt_BR', 'id': 'id'}
# Transifex does not support multiple character sets for Uzbek, but
# Psiphon supports both uz@Latn and uz@cyrillic. So we're going to
# use "Uzbek" ("uz") for uz@Latn and "Klingon" ("tlh") for uz@cyrillic.
# We opened an issue with Transifex about this, but it hasn't been
# rectified yet:
# https://getsatisfaction.com/indifex/topics/uzbek_cyrillic_language
DEFAULT_LANGS['uz'] = 'uz@Latn'
DEFAULT_LANGS['tlh'] = 'uz@cyrillic'


RTL_LANGS = ('ar', 'fa', 'he')


# There should be no more or fewer Transifex resources than this. Otherwise
# one or the other needs to be updated.
known_resources = \
    ['android-app-strings', 'android-app-browser-strings',
     'email-template-strings', 'feedback-template-strings',
     'android-library-strings', 'feedback-auto-responses', 'website-strings',
     'store-assets', 'windows-client-strings']


def process_android_app_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr'}
    process_resource('android-app-strings',
                     lambda lang: '../Android/app/src/main/res/values-%s/strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_android_library_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr'}
    process_resource('android-library-strings',
                     lambda lang: '../Android/app/src/main/res/values-%s/psiphon_android_library_strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_android_app_browser_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr'}
    process_resource('android-app-browser-strings',
                     lambda lang: '../Android/app/src/main/res/values-%s/zirco_browser_strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


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


def process_feedback_auto_responses():
    def auto_response_modifier(html, _):
        # For some reason Transifex wraps everything in a <div>, so we need to
        # drill into the elements to get our stuff.
        soup = BeautifulSoup(html)
        divs = soup.findAll('div', 'response-subject')
        divs += soup.findAll('div', 'response-body')
        result = u'\n\n'.join([unicode(div) for div in divs])

        # For some reason (again), Transifex replaces some "%"" with "&#37;",
        # which wrecks our formatting efforts.
        result = result.replace(u'&#37;', u'%')

        return result

    process_resource('feedback-auto-responses',
                     lambda lang: '../EmailResponder/FeedbackDecryptor/responses/%s.html' % lang,
                     auto_response_modifier,
                     bom=False,
                     skip_untranslated=True)


def process_website_strings():
    process_resource('website-strings',
                     lambda lang: '../Website/_locales/%s/messages.json' % lang,
                     None,
                     bom=False,
                     skip_untranslated=True)


def process_windows_client_strings():
    process_resource('windows-client-strings',
                     lambda lang: '../Client/psiclient/webui/_locales/%s/messages.json' % lang,
                     output_mutator_fn=None,
                     bom=False,
                     skip_untranslated=True)


def process_store_assets():
    process_resource('store-assets',
                     lambda lang: '../Assets/Store/%s/text.html' % lang,
                     None,
                     bom=False)


# This is needed externally:
WEBSITE_LANGS = DEFAULT_LANGS.values()


def process_resource(resource, output_path_fn, output_mutator_fn, bom,
                     langs=None, skip_untranslated=False):
    '''
    `output_path_fn` must be callable. It will be passed the language code and
    must return the path+filename to write to.
    `output_mutator_fn` must be callable. It will be passed the output and the
    current language code. May be None.
    If `skip_untranslated` is True, translations that are less than 10% complete
    will be skipped.
    '''
    if not langs:
        langs = DEFAULT_LANGS

    for in_lang, out_lang in langs.items():
        if skip_untranslated:
            stats = request('resource/%s/stats/%s' % (resource, in_lang))
            if int(stats['completed'].rstrip('%')) < 10:
                continue

        r = request('resource/%s/translation/%s' % (resource, in_lang))

        if output_mutator_fn:
            # Transifex doesn't support the special character-type
            # modifiers we need for some languages,
            # like 'ug' -> 'ug@Latn'. So we'll need to hack in the
            # character-type info.
            content = output_mutator_fn(r['content'], out_lang)
        else:
            content = r['content']

        # Make line endings consistently Unix-y.
        content = content.replace('\r\n', '\n')

        output_path = output_path_fn(out_lang)

        # Path sure the output directory exists.
        try:
            os.makedirs(os.path.dirname(output_path))
        except OSError as ex:
            if ex.errno == errno.EEXIST and os.path.isdir(os.path.dirname(output_path)):
                pass
            else:
                raise

        with codecs.open(output_path, 'w', 'utf-8') as f:
            if bom:
                f.write(u'\uFEFF')
            f.write(content)


def gather_resource(resource, langs=None, skip_untranslated=False):
    '''
    Collect all translations for the given resource and return them.
    '''
    if not langs:
        langs = DEFAULT_LANGS

    result = {}
    for in_lang, out_lang in langs.items():
        if skip_untranslated:
            stats = request('resource/%s/stats/%s' % (resource, in_lang))
            if stats['completed'] == '0%':
                continue

        r = request('resource/%s/translation/%s' % (resource, in_lang))
        result[out_lang] = r['content'].replace('\r\n', '\n')

    return result


def check_resource_list():
    r = request('resources')
    available_resources = [res['slug'] for res in r]
    available_resources.sort()
    known_resources.sort()
    return available_resources == known_resources


# Initialized on first use.
_config = None


def request(command, params=None):
    global _config
    if not _config:
        # Must be of the form:
        # {"username": ..., "password": ...}
        with open('./transifex_conf.json') as config_fp:
            _config = json.load(config_fp)

    url = 'https://www.transifex.com/api/2/project/Psiphon3/' + command + '/'
    r = requests.get(url, params=params,
                     auth=(_config['username'], _config['password']))
    if r.status_code != 200:
        raise Exception('Request failed with code %d: %s' %
                            (r.status_code, url))
    return r.json()


def yaml_lang_change(in_yaml, to_lang):
    return to_lang + in_yaml[in_yaml.find(':'):]


def html_doctype_add(in_html, to_lang):
    return '<!DOCTYPE html>\n' + in_html


def go():
    if check_resource_list():
        print('Known and available resources match')
    else:
        raise Exception('Known and available resources do not match')

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

    process_website_strings()
    print('process_website_strings: DONE')

    process_feedback_auto_responses()
    print('process_feedback_auto_responses: DONE')

    process_windows_client_strings()
    print('process_windows_client_strings: DONE')
    print('For Windows client changes to take effect, you must run the Grunt tasks in Client/psiclient/webui')

    process_store_assets()
    print('process_store_assets: DONE')


if __name__ == '__main__':
    if os.getcwd().split(os.path.sep)[-1] != 'Automation':
        raise Exception('Must be executed from Automation directory!')

    go()

    print('FINISHED')
