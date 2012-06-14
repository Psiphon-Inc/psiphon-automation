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

要使用Psiphon 3, 保存文件.exe扩展名。
或者点击下面的链接。
{0}/zh.html

Psiphon 3 дан фойдаланиш учун илова қилинган файлни .exe кенгайтиришда сақланг.
Ёки қуйидаги уланишни босинг. 
{0}/uz@cyrillic.html

Psiphon 3 dan foydalanish uchun ilova qilingan faylni .exe kyengaytirishda saqlang.
Yoki quyidagi ulanishni bosing.
{0}/uz@Latn.html

Psiphon 3 құралын қолдану үшін тіркелген файлды.exe пішімінде сақтаңыз.
Немесе төмендегі сілтемені басыңыз.
{0}/kk.html

Psiphon 3-dən istifadə etmək üçün .exe genişlənməsində olan qoşma faylını saxlayın.
Və ya aşağıdakı əlaqəyə klikləyin.
{0}/az.html

Русский - {0}/ru.html
Türkmençe - {0}/tk.html
العربي - {0}/ar.html
ภาษาไทย - {0}/th.html
Uyghurche - {0}/ug@Latn.html'''.format(bucket_root_url)

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
要使用Psiphon 3, 保存文件.exe扩展名。<br>
或者点击下面的链接。<br>
<a href="{0}/zh.html">{0}/zh.html</a><br>
</div>
<br>
<div style="direction: ltr;">
Psiphon 3 дан фойдаланиш учун илова қилинган файлни .exe форматида сақланг.<br>
Ёки мана бу линкни босинг.<br> 
<a href="{0}/uz@cyrillic.html">{0}/uz@cyrillic.html</a><br>
</div>
<br>
<div style="direction: ltr;">
Psiphon 3 dan foydalanish uchun ilova qilingan faylni .exe formatida saqlang.<br>
Yoki mana bu linkni bosing.<br> 
<a href="{0}/uz@Latn.html">{0}/uz@Latn.html</a><br>
</div>
<br>
<div style="direction: ltr;">
Psiphon 3 құралын қолдану үшін тіркелген файлды.exe пішімінде сақтаңыз.<br>
Немесе төмендегі сілтемені басыңыз.<br> 
<a href="{0}/kk.html">{0}/kk.html</a><br>
</div>
<br>
<div style="direction: ltr;">
Psiphon 3-dən istifadə etmək üçün .exe genişlənməsində olan qoşma faylını saxlayın.<br>
Və ya aşağıdakı əlaqəyə klikləyin.<br> 
<a href="{0}/az.html">{0}/az.html</a><br>
</div>
<br>
<div style="direction: ltr;">
Русский - <a href="{0}/ru.html">{0}/ru.html</a><br>
Türkmençe - <a href="{0}/tk.html">{0}/tk.html</a><br>
</div>
<div style="direction: rtl;">
العربي - <a href="{0}/ar.html">{0}/ar.html</a><br>
</div>
<div style="direction: ltr;">
ภาษาไทย - <a href="{0}/th.html">{0}/th.html</a><br>
Uyghurche - <a href="{0}/ug@Latn.html">{0}/ug@Latn.html</a><br>
</div>'''.format(bucket_root_url)
