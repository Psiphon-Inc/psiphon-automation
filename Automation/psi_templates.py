#!/usr/bin/python
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

def get_tweet_message(bucket_root_url):
    return '''English - {0}/en.html
فارسی - x{0}/fa.html
Русский - {0}/ru.html
Türkmençe -{0}/tk.html
中文 - {0}/zh.html
العربي -  x{0}/ar.html
ภาษาไทย -{0}/th.html'''.format(bucket_root_url)

def get_email_content(bucket_root_url):
    return 'Get Psiphon 3!', '''English - {0}/en.html
فارسی - x{0}/fa.html
Русский - {0}/ru.html
Türkmençe -{0}/tk.html
中文 - {0}/zh.html
العربي -  x{0}/ar.html
ภาษาไทย -{0}/th.html'''.format(bucket_root_url)
