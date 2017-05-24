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

from __future__ import print_function
import os
import sys
import errno
import shutil
import json
import codecs
import argparse
import requests
from BeautifulSoup import BeautifulSoup

import psi_feedback_templates


DEFAULT_LANGS = {
    'ar': 'ar',         # Arabic
    'de': 'de',         # German
    'el_GR': 'el',      # Greek
    'es': 'es',         # Spanish
    'fa': 'fa',         # Farsi/Persian
    'fi_FI': 'fi',      # Finnish
    'fr': 'fr',         # French
    'hr': 'hr',         # Croation
    'id': 'id',         # Indonesian
    'it': 'it',         # Italian
    'kk': 'kk',         # Kazak
    'ko': 'ko',         # Korean
    'nb_NO': 'nb',      # Norwegian
    'nl': 'nl',         # Dutch
    'pt_BR': 'pt_BR',   # Portuguese-Brazil
    'pt_PT': 'pt_PT',   # Portuguese-Portugal
    'ru': 'ru',         # Russian
    'th': 'th',         # Thai
    'tk': 'tk',         # Turkmen
    'tr': 'tr',         # Turkish
    'ug': 'ug@Latn',    # Uighur (latin script)
    'vi': 'vi',         # Vietnamese
    'zh': 'zh',         # Chinese (simplified)
    'zh_TW': 'zh_TW'    # Chinese (traditional)
}


RTL_LANGS = ('ar', 'fa', 'he')


PSIPHON_CIRCUMVENTION_SYSTEM_RESOURCES = \
    ['android-app-strings', 'android-app-browser-strings',
     'email-template-strings', 'feedback-template-strings',
     'android-library-strings', 'feedback-auto-responses', 'website-strings',
     'store-assets', 'windows-client-strings']
PSIPHON_CIRCUMVENTION_SYSTEM_DIR = 'psiphon-circumvention-system'

IOS_BROWSER_RESOURCES = \
    ['ios-browser-iasklocalizablestrings', 'ios-browser-localizablestrings',
     'ios-browser-onepasswordextensionstrings', 'ios-browser-rootstrings',
     'ios-browser-app-store-assets']
IOS_BROWSER_DIR = 'endless'
IOS_BROWSER_LANGS = DEFAULT_LANGS.copy()
# Xcode/iOS uses some different locale codes than Transifex does
IOS_BROWSER_LANGS.update({'pt_PT': 'pt-PT', 'zh': 'zh-Hans', 'zh_TW': 'zh-Hant'})


# There should be no more or fewer Transifex resources than this. Otherwise
# either this code or Transifex needs to be updated.
KNOWN_RESOURCES = PSIPHON_CIRCUMVENTION_SYSTEM_RESOURCES + IOS_BROWSER_RESOURCES


def process_android_app_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr',
             'pt_BR': 'pt-rBR'}
    process_resource('android-app-strings',
                     lambda lang: './Android/app/src/main/res/values-%s/strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_android_library_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr',
             'pt_BR': 'pt-rBR'}
    process_resource('android-library-strings',
                     lambda lang: './Android/app/src/main/res/values-%s/psiphon_android_library_strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_android_app_browser_strings():
    langs = {'ar': 'ar', 'es': 'es', 'fa': 'fa', 'ru': 'ru', 'tk': 'tk',
             'vi': 'vi', 'zh': 'zh', 'nb_NO': 'nb', 'tr': 'tr', 'fr': 'fr',
             'pt_BR': 'pt-rBR'}
    process_resource('android-app-browser-strings',
                     lambda lang: './Android/app/src/main/res/values-%s/zirco_browser_strings.xml' % lang,
                     None,
                     bom=False,
                     langs=langs)


def process_email_template_strings():
    process_resource('email-template-strings',
                     lambda lang: './Automation/TemplateStrings/%s.yaml' % lang,
                     yaml_lang_change,
                     bom=False)


def process_feedback_template_strings():
    process_resource('feedback-template-strings',
                     lambda lang: './Automation/FeedbackSite/Templates/%s.yaml' % lang,
                     yaml_lang_change,
                     bom=False)

    # Regenerate the HTML file
    psi_feedback_templates.make_feedback_html()

    # Copy the HTML file to where it needs to be
    shutil.copy2('./Automation/FeedbackSite/feedback.html',
                 './Android/app/src/main/assets/feedback.html')


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
                     lambda lang: './EmailResponder/FeedbackDecryptor/responses/%s.html' % lang,
                     auto_response_modifier,
                     bom=False,
                     skip_untranslated=True)


def process_website_strings():
    process_resource('website-strings',
                     lambda lang: './Website/_locales/%s/messages.json' % lang,
                     None,
                     bom=False,
                     skip_untranslated=True)


def process_windows_client_strings():
    process_resource('windows-client-strings',
                     lambda lang: './Client/psiclient/webui/_locales/%s/messages.json' % lang,
                     output_mutator_fn=None,
                     bom=False,
                     skip_untranslated=True)


def process_store_assets():
    process_resource('store-assets',
                     lambda lang: './Assets/Store/%s/text.html' % lang,
                     None,
                     bom=False)


# This is needed externally:
WEBSITE_LANGS = DEFAULT_LANGS.values()


def process_resource(resource, output_path_fn, output_mutator_fn, bom,
                     langs=None, skip_untranslated=False, encoding='utf-8'):
    '''
    `output_path_fn` must be callable. It will be passed the language code and
    must return the path+filename to write to.
    `output_mutator_fn` must be callable. It will be passed the output and the
    current language code. May be None.
    If `skip_untranslated` is True, translations that are less than 20% complete
    will be skipped.
    '''
    if not langs:
        langs = DEFAULT_LANGS

    for in_lang, out_lang in langs.items():
        if skip_untranslated:
            stats = request('resource/%s/stats/%s' % (resource, in_lang))
            if int(stats['completed'].rstrip('%')) < 20:
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

        with codecs.open(output_path, 'w', encoding) as f:
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
    KNOWN_RESOURCES.sort()
    return available_resources == KNOWN_RESOURCES


def request(command, params=None):
    url = 'https://www.transifex.com/api/2/project/Psiphon3/' + command + '/'
    r = requests.get(url, params=params,
                     auth=(_getconfig()['username'], _getconfig()['password']))
    if r.status_code != 200:
        raise Exception('Request failed with code %d: %s' %
                            (r.status_code, url))
    return r.json()


def yaml_lang_change(in_yaml, to_lang):
    return to_lang + in_yaml[in_yaml.find(':'):]


def html_doctype_add(in_html, to_lang):
    return '<!DOCTYPE html>\n' + in_html


def pull_psiphon_circumvention_system_translations():
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


def pull_ios_browser_translations():
    resources = (
        ('ios-browser-iasklocalizablestrings', 'IASKLocalizable.strings'),
        ('ios-browser-localizablestrings', 'Localizable.strings'),
        ('ios-browser-onepasswordextensionstrings', 'OnePasswordExtension.strings'),
        ('ios-browser-rootstrings', 'Root.strings')
    )

    for resname, fname in resources:
        process_resource(resname,
                         lambda lang: './Endless/%s.lproj/%s' % (lang, fname),
                         None,
                         langs=IOS_BROWSER_LANGS,
                         bom=False,
                         skip_untranslated=True,
                         encoding='utf-16')
        print('%s: DONE' % (resname,))


# Transifex credentials.
# Must be of the form:
# {"username": ..., "password": ...}
_config = None  # Don't use this directly. Call _getconfig()
def _getconfig():
    global _config
    if _config:
        return _config

    DEFAULT_CONFIG_FILENAME = 'transifex_conf.json'

    # Figure out where the config file is
    parser = argparse.ArgumentParser(description='Pull translations from Transifex')
    parser.add_argument('configfile', default=None, nargs='?',
                        help='config file (default: pwd or location of script)')
    args = parser.parse_args()
    configfile = None
    if args.configfile and os.path.exists(args.configfile):
        # Use the script argument
        configfile = args.configfile
    elif os.path.exists(DEFAULT_CONFIG_FILENAME):
        # Use the conf in pwd
        configfile = DEFAULT_CONFIG_FILENAME
    elif __file__ and os.path.exists(os.path.join(
                        os.path.dirname(os.path.realpath(__file__)),
                        DEFAULT_CONFIG_FILENAME)):
        configfile = os.path.join(
                        os.path.dirname(os.path.realpath(__file__)),
                        DEFAULT_CONFIG_FILENAME)
    else:
        print('Unable to find config file')
        sys.exit(1)

    with open(configfile) as config_fp:
        _config = json.load(config_fp)

    if not _config:
        print('Unable to load config contents')
        sys.exit(1)

    return _config


def go():
    if check_resource_list():
        print('Known and available resources match')
    else:
        raise Exception('Known and available resources do not match')

    # Figure out what repo we're in, based on the current path. This isn't very
    # robust -- since the repo dir could be named anything -- but it's good
    # enough for our purposes.
    rpath = os.getcwd().split(os.path.sep)
    rpath.reverse()

    try:
        psiphon_circumvention_system_index = rpath.index(PSIPHON_CIRCUMVENTION_SYSTEM_DIR)
    except:
        psiphon_circumvention_system_index = sys.maxsize

    try:
        ios_browser_index = rpath.index(IOS_BROWSER_DIR)
    except:
        ios_browser_index = sys.maxsize

    if psiphon_circumvention_system_index < 0 and ios_browser_index < 0:
        raise Exception('Must be executed from within repo!')
    elif psiphon_circumvention_system_index < ios_browser_index:
        # Change pwd to root of the repo
        rpath = rpath[psiphon_circumvention_system_index:]
        rpath.reverse()
        path = os.path.sep.join(rpath)
        os.chdir(path)

        pull_psiphon_circumvention_system_translations()
    else:
        # Change pwd to root of the repo
        rpath = rpath[ios_browser_index:]
        rpath.reverse()
        path = os.path.sep.join(rpath)
        os.chdir(path)

        pull_ios_browser_translations()

    print('FINISHED')


if __name__ == '__main__':
    go()
