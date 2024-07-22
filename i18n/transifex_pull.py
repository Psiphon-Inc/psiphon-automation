#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2023, Psiphon Inc.
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

Run with
# If you don't already have pipenv:
$ python3 -m pip install --upgrade pipenv

$ pipenv install --ignore-pipfile
$ pipenv run python transifex_pull.py

# To reset your pipenv state (e.g., after a Python upgrade):
$ pipenv --rm

# To update transifexlib
$ pipenv update transifexlib
$ pipenv --rm
$ pipenv install --ignore-pipfile
'''


import os
import subprocess
import transifexlib

# NOTE: For email strings, also see the language list in psi_templates.py
DEFAULT_LANGS = {
    'am': 'am',         # Amharic
    'ar': 'ar',         # Arabic
    'az@latin': 'az',   # Azerbaijani
    'be': 'be',         # Belarusian
    'bn': 'bn',         # Bengali
    'bo': 'bo',         # Tibetan
    'de': 'de',         # German
    'el_GR': 'el',      # Greek
    'es': 'es',         # Spanish
    'fa': 'fa',         # Farsi/Persian
    'fa_AF': 'fa_AF',   # Persian (Afghanistan)
    'fi_FI': 'fi',      # Finnish
    'fr': 'fr',         # French
    'hi': 'hi',         # Hindi
    'hr': 'hr',         # Croatian
    'hu': 'hu',         # Hungarian
    'id': 'id',         # Indonesian
    'it': 'it',         # Italian
    'kk': 'kk',         # Kazak
    'km': 'km',         # Khmer
    'ko': 'ko',         # Korean
    'ky': 'ky',         # Kyrgyz
    'my': 'my',         # Burmese
    'nb_NO': 'nb',      # Norwegian
    'nl': 'nl',         # Dutch
    'om': 'om',         # Afaan Oromoo
    'pt_BR': 'pt_BR',   # Portuguese-Brazil
    'pt_PT': 'pt_PT',   # Portuguese-Portugal
    'ru': 'ru',         # Russian
    'sn': 'sn',         # Shona
    'sw': 'sw',         # Swahili
    'tg': 'tg',         # Tajik
    'th': 'th',         # Thai
    'ti': 'ti',         # Tigrinya
    'tk': 'tk',         # Turkmen
    'tr': 'tr',         # Turkish
    #'ug': 'ug@Latn',    # Uighur (latin script) # Disappeared from Transifex project and now has low translation percentage
    'uk': 'uk',         # Ukrainian
    'ur': 'ur',         # Urdu
    'uz': 'uz@Latn',    # Uzbek (latin script)
    'uz@Cyrl': 'uz@Cyrl',    # Uzbek (cyrillic script)
    'vi': 'vi',         # Vietnamese
    'zh': 'zh',         # Chinese (simplified)
    'zh_TW': 'zh_TW'    # Chinese (traditional)
}


PSIPHON_CIRCUMVENTION_SYSTEM_DIR = 'psiphon-automation'


def pull_email_template_strings():
    langs = DEFAULT_LANGS.copy()
    langs['ha'] = 'ha'  # Hausa
    transifexlib.process_resource(
        'https://app.transifex.com/otf/Psiphon3/email-template-strings/',
        langs,
        '../Automation/TemplateStrings/en.yaml',
        lambda lang: f'../Automation/TemplateStrings/{lang}.yaml',
        transifexlib.merge_yaml_translations)


def pull_feedback_auto_responses_strings():
    transifexlib.process_resource(
        'https://app.transifex.com/otf/Psiphon3/feedback-auto-responses/',
        DEFAULT_LANGS,
        '../EmailResponder/FeedbackDecryptor/responses/master.html',
        lambda lang: f'../EmailResponder/FeedbackDecryptor/responses/{lang}.html',
        transifexlib.merge_html_translations)


def go():
    pull_email_template_strings()
    pull_feedback_auto_responses_strings()

    print('\nFinished translation pull')


if __name__ == '__main__':
    go()
