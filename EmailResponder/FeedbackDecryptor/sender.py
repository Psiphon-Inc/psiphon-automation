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

import typing
import sys

from config import config

# Make EmailResponder modules available
sys.path.append('..')
import sendmail


_SES_EMAIL_SIZE_LIMIT = 10485760


def send_email(
        recipient: typing.Union[str, list[str]],
        from_address: str,
        subject: str,
        body_text: str,
        body_html: str,
        replyid: typing.Union[str, None] = None,
        attachments: typing.Union[list, None] = None) -> None:
    '''
    Send email back to the user that sent feedback.
    On error, raises exception.
    '''

    # The attachment types allowed by SES are limited (and not APK or EXE), so we're going
    # to remove them at this point.
    # TODO: Figure out a better way to do this. (We used to use SMTP for this, and we
    # could consider going back to it.)
    attachments = None

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
        raise ValueError("Failed to create raw email")

    # SES has a send size limit, above which it'll reject the email. If our raw_email is
    # larger than that, we'll discard the HTML version.
    if len(raw_email) > _SES_EMAIL_SIZE_LIMIT:
        body.pop() # discard HTML
        raw_email = sendmail.create_raw_email(recipient,
                                              from_address,
                                              subject,
                                              body,
                                              attachments,
                                              extra_headers)
        # We're not going to check the size again. We'll just try and let it fail if it's too big.

    if not raw_email:
        raise ValueError("Failed to create raw email")

    # If the raw_email is still too large, we will get an exception from this call.
    # There's nothing we can do about it, so we'll let it bubble up and be logged.
    sendmail.send_raw_email_amazonses(raw_email, from_address, recipient, config.awsRegion)
