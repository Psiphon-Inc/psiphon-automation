# Copyright (c) 2013, Psiphon Inc.
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

import sys
import smtplib

from config import config

# Make EmailResponder modules available
sys.path.append('..')
import sendmail


def send(recipients, from_address,
         subject, body_text, body_html,
         replyid=None):
    '''
    Send email via SMTP. Throws `smtplib.SMTPException` on error.
    `recipients` may be an array of address or a single address string.
    '''

    reply_to_header = {'In-Reply-To': replyid,
                       'References': replyid} if replyid else None

    body = []
    if body_text:
        body.append(('plain', body_text))
    if body_html:
        body.append(('html', body_html))

    raw_email = sendmail.create_raw_email(recipients,
                                          from_address,
                                          subject,
                                          body,
                                          None,
                                          reply_to_header)

    smtp_server = smtplib.SMTP_SSL(config['smtpServer'], config['smtpPort'])
    smtp_server.login(config['emailUsername'], config['emailPassword'])

    sendmail.send_raw_email_smtp(raw_email,
                                 from_address,
                                 recipients,
                                 smtp_server)


def send_response(recipient, from_address,
                  subject, body_text, body_html,
                  replyid, attachments):
    '''
    Send email back to the user that sent feedback.
    On error, raises exception.
    `replyid` may be None. `attachments` may be None.
    '''

    # TODO: Use SMTP rather than SES if we have attachments SES or SMTP (get@ style).
    # DISABLING ATTACHMENTS
    if attachments:
        return

    extra_headers = {'Reply-To': from_address}

    if replyid:
        extra_headers['In-Reply-To'] = replyid
        extra_headers['References'] = replyid

    body = []
    if body_text:
        body.append(('plain', body_text))
    if body_html:
        body.append(('html', body_html))

    raw_email = sendmail.create_raw_email(recipient,
                                          from_address,
                                          subject,
                                          body,
                                          attachments,
                                          extra_headers)

    if not raw_email:
        return

    try:
        sendmail.send_raw_email_amazonses(raw_email, from_address)
    except:
        raise
