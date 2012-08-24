#!/usr/bin/python
# coding=utf-8
#
# Copyright (c) 2011, Psiphon Inc.
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

import os
import yaml
import json
import hashlib

FEEDBACK_LANGUAGES = [
    'en',
    'fa',
    'ar',
    'zh',
    'uz@cyrillic',
    'uz@Latn',
    'ru',
    'kk',
    'az',
    'tk',
    'th',
    'ug@Latn',
    'es',
    'vi'
]

def make_feedback_html():
    lang = {}
    for language in FEEDBACK_LANGUAGES:
        lang[language] = get_language_from_template(language)

    feedback_path = os.path.join('.', 'FeedbackSite', 'feedback.html')
    feedback_template_path = os.path.join('.', 'FeedbackSite', 'Templates', 'feedback.html.tpl')

    format = {
        "langJSON":json.JSONEncoder().encode(lang), 
        "speed":hashlib.md5(lang['en']['speed_title']).hexdigest(), 
        "connectivity":hashlib.md5(lang['en']['connectivity_title']).hexdigest(),
        "compatibility":hashlib.md5(lang['en']['compatibility_title']).hexdigest()
    }

    with open(feedback_template_path) as f:
        str = (f.read()).format(**format)

    with open(feedback_path, 'w') as f:
        f.write(str)

def get_language_from_template(language):
    path = os.path.join('.', 'FeedbackSite', 'Templates', language + '.yaml')
    with open(path) as f:
        return yaml.load(f.read())[language]

