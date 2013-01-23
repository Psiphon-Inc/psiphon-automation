# Copyright (c) 2012, Psiphon Inc.
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


import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send(server, port, username, password,
         fromaddr, toaddrs, subject, body_text, body_html, replyid):
    '''
    Send email via SMTP. Throws exception on error.
    '''

    # TODO: Is `encode('utf8')` the right thing to do here? Or should we be
    # using something like http://docs.python.org/2/library/email.charset.html

    if type(toaddrs) == str:
        toaddrs = [toaddrs]

    msg = MIMEMultipart('alternative')

    msg['Subject'] = subject.encode('utf8')
    msg['From'] = fromaddr
    msg['To'] = toaddrs

    if replyid:
        msg['In-Reply-To'] = replyid

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.

    if body_text:
        msg.attach(MIMEText(body_text.encode('utf8'), 'plain'))

    if body_html:
        msg.attach(MIMEText(body_html.encode('utf8'), 'html'))

    mailserver = smtplib.SMTP_SSL(server, port)
    mailserver.login(username, password)

    mailserver.sendmail(fromaddr, toaddrs, msg.as_string())
    mailserver.quit()
