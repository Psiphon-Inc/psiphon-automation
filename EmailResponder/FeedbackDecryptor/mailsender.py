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

'''
Periodically checks email-ID-DB. If diagnostic info ID is found in
diagnostic-info-DB, then response email is formatted and sent; entry is
deleted from email-ID-DB. Also cleans up expired email-ID-DB entries.
'''

import yaml
import smtplib
import time

from config import config
import logger
import datastore
import emailsender
import mailformatter


_SLEEP_TIME_SECS = 60


def _email_diagnostic_info_records():
    '''
    Generator for obtaining email_diagnostic_info records.
    '''
    while True:
        for rec in datastore.get_email_diagnostic_info_iterator():
            yield rec

        datastore.expire_old_email_diagnostic_info_records()

        time.sleep(_SLEEP_TIME_SECS)


def go():
    # Retrieve and process email-to-diagnostic-info records.
    # Note that `_email_diagnostic_info_records` throttles itself if/when
    # there are no records immediately available.
    for email_diagnostic_info in _email_diagnostic_info_records():
        # Check if there is (yet) a corresponding diagnostic info record
        diagnostic_info = datastore.find_diagnostic_info(email_diagnostic_info['diagnostic_info_id'])
        if not diagnostic_info:
            continue

        # Convert the modified YAML back into a string for emailing.
        diagnostic_info_text = yaml.safe_dump_all(diagnostic_info,
                                                  default_flow_style=False)

        try:
            diagnostic_info_html = mailformatter.format(diagnostic_info)
        except Exception as e:
            diagnostic_info_html = None

        # If we get to here, then we have a valid diagnostic email.
        # Reply with the decrypted content.
        try:
            emailsender.send(config['smtpServer'],
                             config['smtpPort'],
                             config['emailUsername'],
                             config['emailPassword'],
                             config['emailUsername'],
                             config['emailUsername'],
                             u'Re: %s' % (email_diagnostic_info['email_subject'] or ''),
                             diagnostic_info_text,
                             diagnostic_info_html,
                             email_diagnostic_info['email_id'])
        except smtplib.SMTPException as e:
            # Something went wrong with the sending of the response. Log it.
            logger.log(str(e))

        # Delete the processed record. (Note that sending the email might have
        # failed, but we're deleting it anyway. This is a debatable decision.)
        datastore.remove_email_diagnostic_info(email_diagnostic_info)
