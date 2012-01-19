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

def get_tweet_message(s3_bucket_name):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return 'Get Psiphon 3 here: %s/en.html' % (bucket_root_url,)

def get_plaintext_email_content(s3_bucket_name):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return '''To use Psiphon 3, save the attached file with a .exe extension.
Or click the link below.
{0}/en.html

برای استفاده از سایفون ۳، فایل پیوست شده را با پسوند زیر ذخیره کنید‪:‬
.exe
یا بر روی لینک  زیر کلیک کنید‪.‬
{0}/fa.html

Русский - {0}/ru.html
Türkmençe - {0}/tk.html
中文 - {0}/zh.html
العربي - {0}/ar.html
ภาษาไทย - {0}/th.html'''.format(bucket_root_url)

def get_html_email_content(s3_bucket_name):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return '''<div style="direction: ltr;">
To use Psiphon 3, save the attached file with a .exe extension.<br>
Or click the link below.<br>
<a href="{0}/en.html">{0}/en.html</a><br>
</div>
<br>
<div style="direction: rtl;">
برای استفاده از سایفون ۳، فایل پیوست شده را با پسوند زیر ذخیره کنید‪:‬<br>
.exe<br>
یا بر روی لینک  زیر کلیک کنید‪.‬<br>
<a href="{0}/fa.html">{0}/fa.html</a><br>
</div>
<br>
<div style="direction: ltr;">
Русский - <a href="{0}/ru.html">{0}/ru.html</a><br>
Türkmençe - <a href="{0}/tk.html">{0}/tk.html</a><br>
中文 - <a href="{0}/zh.html">{0}/zh.html</a><br>
</div>
<div style="direction: rtl;">
العربي - <a href="{0}/ar.html">{0}/ar.html</a><br>
</div>
<div style="direction: ltr;">
ภาษาไทย - <a href="{0}/th.html">{0}/th.html</a><br>
</div>'''.format(bucket_root_url)
