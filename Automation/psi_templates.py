﻿#!/usr/bin/python
# coding=utf-8
#
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
#

# This file processes email autoresponder content templates

import os
import yaml

try:
    import psi_ops_s3
except ImportError as error:
    print(error)
except TypeError as te:
    print(te)


# This list needs to be kept in sync with the languages in i18n/transifex_pull.py
# TODO: Use that list as the canonical source
LANGUAGES = [
    'en',
    'fa',
    'ar',
    'zh',
    'am',
    'az',
    'be',
    'bn',
    'bo',
    'de',
    'el',
    'es',
    'fa_AF',
    'fi',
    'fr',
    'hi',
    'hr',
    'hu',
    'id',
    'it',
    'kk',
    'km',
    'ko',
    'ky',
    'my',
    'nb',
    'nl',
    'om',
    'pt_BR',
    'pt_PT',
    'ru',
    'sn',
    'sw',
    'tg',
    'th',
    'ti',
    'tk',
    'tr',
    # 'ug@Latn',
    'uk',
    'ur',
    'uz@Cyrl',
    'uz@Latn',
    'vi',
    'zh_TW'
]


def get_language_string(language, key):
    """Returns None if key not found for language.
    """
    path = os.path.join('.', 'TemplateStrings', language + '.yaml')
    with open(path, encoding='utf-8') as lang_file:
        lang_dict = yaml.safe_load(lang_file.read())

    string = lang_dict.get(language, {}).get(key)

    if string:
        # Assumes strings have one {0} format specifier to receive the
        # language name. Other format specifiers, to be substituted later,
        # should be escaped: {{N}}
        string = string.format(language)

    return string


def get_all_languages_string(key, languages):
    strings = []
    if languages:
        strings = [get_language_string(language, key) for language in languages if language in LANGUAGES]
    else:
        strings = [get_language_string(language, key) for language in LANGUAGES]

    # Get rid of None elements and strip
    strings = [string.strip() for string in filter(None, strings)]

    return '\n\n'.join(strings)


def get_tweet_message(s3_bucket_name):
    url = psi_ops_s3.get_s3_bucket_home_page_url(s3_bucket_name)
    return 'Get Psiphon 3 here: %s' % (url,)


def get_plaintext_email_content(
        s3_bucket_name,
        languages):
    bucket_root_url = psi_ops_s3.get_s3_bucket_site_root(s3_bucket_name)
    return get_all_languages_string(
        'plaintext_email_no_attachment',
        languages).format(bucket_root_url)


def get_html_email_content(
        s3_bucket_name,
        languages):
    bucket_root_url = psi_ops_s3.get_s3_bucket_site_root(s3_bucket_name)
    return get_all_languages_string(
        'html_email_no_attachment',
        languages).format(bucket_root_url)


def get_plaintext_attachment_email_content(
        s3_bucket_name,
        windows_attachment_filename,
        android_attachment_filename,
        languages,
        platforms):
    # TODO: new attachment strings per platform
    if platforms != None:
        return get_plaintext_email_content(s3_bucket_name, languages)
    bucket_root_url = psi_ops_s3.get_s3_bucket_site_root(s3_bucket_name)
    return get_all_languages_string(
        'plaintext_email_with_attachment',
        languages).format(
            bucket_root_url,
            windows_attachment_filename, # supports legacy translations; can be removed in future release
            android_attachment_filename) # # supports legacy translations; can be removed in future release


def get_html_attachment_email_content(
        s3_bucket_name,
        windows_attachment_filename,
        android_attachment_filename,
        languages,
        platforms):
    # TODO: new attachment strings per platform
    if platforms != None:
        return get_html_email_content(s3_bucket_name, languages)
    bucket_root_url = psi_ops_s3.get_s3_bucket_site_root(s3_bucket_name)
    return get_all_languages_string(
        'html_email_with_attachment',
        languages).format(
            bucket_root_url,
            windows_attachment_filename,
            android_attachment_filename)
