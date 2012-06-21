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

def get_plaintext_email_content(
        s3_bucket_name):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return '''English - {0}/en.html
فارسی - {0}/fa.html
中文 - {0}/zh.html
Ўзбекча - {0}/uz@cyrillic.html
O'zbekcha - {0}/uz@Latn.html
Русский - {0}/ru.html
қазақ тілі - {0}/kk.html
azərbaycan dili - {0}/az.html
Türkmençe - {0}/tk.html
العربي - {0}/ar.html
ภาษาไทย - {0}/th.html
Uyghurche - {0}/ug@Latn.html
'''.format(bucket_root_url)


def get_html_email_content(
        s3_bucket_name):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return '''<div style="direction: ltr;">
English - <a href="{0}/en.html">{0}/en.html</a><br>
فارسی - <a href="{0}/fa.html">{0}/fa.html</a><br>
中文 - <a href="{0}/zh.html">{0}/zh.html</a><br>
Ўзбекча - <a href="{0}/uz@cyrillic.html">{0}/uz@cyrillic.html</a><br>
O'zbekcha - <a href="{0}/uz@Latn.html">{0}/uz@Latn.html</a><br>
Русский - <a href="{0}/ru.html">{0}/ru.html</a><br>
қазақ тілі - <a href="{0}/kk.html">{0}/kk.html</a><br>
azərbaycan dili - <a href="{0}/az.html">{0}/az.html</a><br>
Türkmençe - <a href="{0}/tk.html">{0}/tk.html</a><br>
العربي - <a href="{0}/ar.html">{0}/ar.html</a><br>
ภาษาไทย - <a href="{0}/th.html">{0}/th.html</a><br>
Uyghurche - <a href="{0}/ug@Latn.html">{0}/ug@Latn.html</a><br>
'''.format(bucket_root_url)

def get_plaintext_attachment_email_content(
        s3_bucket_name,
        windows_attachment_filename,
        android_attachment_filename):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return '''To use Psiphon 3 for Windows, save the attached file {1} with a ".exe" extension.
For more information or to download the files again, click the link below.
{0}/en.html

برای استفاده از سایفون ۳، فایل پیوست شده را {1} با پسوند زیر ذخیره کنید:
.exe
برای اطلاعات بیشتر یا دانلود دوباره فایل ها، لطفآ روی لینک زیرکلیک کنید.
{0}/fa.html

要使用Psiphon 3, 保存文件.exe扩展名。
或者点击下面的链接。
{0}/zh.html

لاستخدام برنامج Psiphon 3 لنظام التشغيل Windows، قم بحفظ الملف المرفق {1} ذو الامتداد ".exe".
لمزيد من المعلومات أو لإعادة تنزيل الملفات، انقر الارتباط أدناه.
{0}/ar.html

Psiphon 3 дан фойдаланиш учун илова қилинган файлни .exe кенгайтиришда сақланг.
Ёки қуйидаги уланишни босинг. 
{0}/uz@cyrillic.html

Psiphon 3 dan foydalanish uchun ilova qilingan faylni .exe kyengaytirishda saqlang.
Yoki quyidagi ulanishni bosing.
{0}/uz@Latn.html

Psiphon 3 для Windows - сохраните прикрепленный файл {1} с расширением ".exe".
Для получения дополнительной информации или скачивания файлов, кликните на ссылку:
{0}/ru.html

Psiphon 3 құралын қолдану үшін тіркелген файлды.exe пішімінде сақтаңыз.
Немесе төмендегі сілтемені басыңыз.
{0}/kk.html

Psiphon 3-dən istifadə etmək üçün .exe genişlənməsində olan qoşma faylını saxlayın.
Və ya aşağıdakı əlaqəyə klikləyin.
{0}/az.html

Türkmençe - {0}/tk.html
ภาษาไทย - {0}/th.html
Uyghurche - {0}/ug@Latn.html'''.format(
    bucket_root_url,
    windows_attachment_filename,
    android_attachment_filename)

def get_html_attachment_email_content(
        s3_bucket_name,
        windows_attachment_filename,
        android_attachment_filename):
    bucket_root_url = 'https://s3.amazonaws.com/' + s3_bucket_name
    return '''<div style="direction: ltr;">
To use Psiphon 3 for Windows, save the attached file {1} with a ".exe" extension.<br>
For more information or to download the files again, click the link below.<br>
<a href="{0}/en.html">{0}/en.html</a><br>
</div>
<br>
<div style="direction: rtl;">
برای استفاده از سایفون ۳، فایل پیوست شده را {1} با پسوند زیر ذخیره کنید:<br>
.exe<br>
برای اطلاعات بیشتر یا دانلود دوباره فایل ها، لطفآ روی لینک زیرکلیک کنید.<br>
<a href="{0}/fa.html">{0}/fa.html</a><br>
</div>
<br>
<div style="direction: ltr;">
要使用Psiphon 3, 保存文件.exe扩展名。<br>
或者点击下面的链接。<br>
<a href="{0}/zh.html">{0}/zh.html</a><br>
</div>
<br>
<br>
<div style="direction: rtl;">
لاستخدام برنامج Psiphon 3 لنظام التشغيل Windows، قم بحفظ الملف المرفق {1} ذو الامتداد ".exe".
لمزيد من المعلومات أو لإعادة تنزيل الملفات، انقر الارتباط أدناه.
<a href="{0}/ar.html">{0}/ar.html</a><br>
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
Psiphon 3 для Windows - сохраните прикрепленный файл {1} с расширением ".exe".<br>
Для получения дополнительной информации или скачивания файлов, кликните на ссылку: {0}/ru.html<br>
<a href="{0}/ru.html">{0}/ru.html</a><br>
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
Türkmençe - <a href="{0}/tk.html">{0}/tk.html</a><br>
</div>
<div style="direction: ltr;">
ภาษาไทย - <a href="{0}/th.html">{0}/th.html</a><br>
Uyghurche - <a href="{0}/ug@Latn.html">{0}/ug@Latn.html</a><br>
</div>'''.format(
    bucket_root_url,
    windows_attachment_filename,
    android_attachment_filename)
