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


import time
import re
import html2text

import logger
import datastore


_SLEEP_TIME_SECS = 60


def _diagnostic_record_iter():
    while True:
        for rec in datastore.get_autoresponder_diagnostic_info_iterator():
            yield rec

        time.sleep(_SLEEP_TIME_SECS)


# Validing email addresses by regex is a bad idea, but we can do something
# rudimentary.
_email_address_regex = re.compile(r'[^@]+@[^@]+\.[^@]+')


def _get_email_reply_info(diagnostic_info):
    '''
    Returns None if no reply info found, otherwise:
        {
            address: user's email address,
            message_id: original email Message-ID,
            subject: original email subject
        }
    Any field may be None.
    '''

    reply_info = None

    if type(diagnostic_info.get('EmailInfo')) == dict:
        reply_info = dict(address=diagnostic_info['EmailInfo'].get('address'),
                          message_id=diagnostic_info['EmailInfo'].get('message_id'),
                          subject=diagnostic_info['EmailInfo'].get('subject'))
    elif type(diagnostic_info.get('Feedback')) == dict:
        reply_info = dict(address=diagnostic_info['Feedback'].get('email'),
                          message_id=None,
                          subject=None)

    return reply_info


def go():
    # Note that `_diagnostic_record_iter` throttles itself if/when there are
    # no records to process.
    for diagnostic_info in _diagnostic_record_iter():

        # For now we don't do any interesting processing/analysis and we just
        # respond to every feedback with an exhortation to upgrade.

        reply_info = _get_email_reply_info(diagnostic_info)

        if not reply_info or not reply_info['address']:
            # If we don't have any reply info, we can't reply
            continue

        # Some day we'll do fancy analysis.
        #response_id = _analyze_diagnostic_info(diagnostic_info)
        responses = [{'id': 'download_new_version_links',
                      'attachments': False,
                      # TODO: Figure this out -- needs bucket and language
                      #       (probably need real function -- not lambda -- maybe
                      #       curry with diagnostic_info?)
                      'formatter': lambda content: content
                      },
                     {'id': 'download_new_version_attachments',
                      'attachments': False,
                      'formatter': lambda content: content
                      }
                     ]

        # TODO: Get the reponse content.
        # TODO: Figure out translation stuff.
        # TODO: Support attachments. This includes using the PropChannel+Sponsor to figure out which build to send.
        # TODO: Allow for multiple responses, and specify SES or SMTP, so we can do get@-style.
        # TODO: Some reponse content will have format specifiers to fill in.
        #       Should we use ordinary Python string formatting, or Mako? (Probably ordinary.)

        for response in responses:
            with open('./responses/%s.html' % response['id']) as content_file:
                response_content_html = content_file.read()

            try:
                response_content_html = response['formatter'](response_content_html)
            except:
                # Probably indicates translation problem. Don't send the response.
                logger.exception()
                logger.error('Response content format failure: %s' % str(e))

            # Create the plaintext form of the email
            response_content_text = html2text.html2text(response_content_html)

            attachments = None
            if response['attachments']:
                get the attachments from S3 and cache them -- like get@
                fp_windows = open(Psiphon windows)
                fp_android = open(Psiphon android)
                attachments = [(fp_windows, 'psiphon3.ex_'),
                               (fp_android, 'PsiphonAndroid.apk')]



            send response to user email
