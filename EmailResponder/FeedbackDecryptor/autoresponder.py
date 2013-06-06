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
import sys
import os

from config import config
import logger
import datastore
import utils
import psi_ops_helpers
import sender

# Make EmailResponder modules available
sys.path.append('..')
import s3_helpers


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


def _check_and_add_blacklist(address):
    '''
    Returns True if the address is blacklisted, otherwise inserts it in the DB
    and returns False.
    '''
    pass#***


def _get_lang_id_from_diagnostic_info(diagnostic_info):
    '''
    Derive the lanague from `diagnostic_info` and return its ID/code.
    Returns `None` if the language can't be determined.
    '''

    lang_id = None

    # There can be different -- and better or worse -- ways of determining the
    # user's language depending on platform, the type of feedback, and so on.

    # Windows, with feedback message
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['Feedback', 'Message', 'text_lang_code'],
                                        required_types=utils.string_types)

    # All Windows feedback
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['DiagnosticInfo', 'SystemInformation', 'OSInfo', 'LanguageInfo', 'language_code'],
                                        required_types=utils.string_types)
    # All Windows feedback
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['DiagnosticInfo', 'SystemInformation', 'OSInfo', 'LocaleInfo', 'language_code'],
                                        required_types=utils.string_types)

    # Android, from email
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['EmailInfo', 'body', 'text_lang_code'],
                                        required_types=utils.string_types)

    # Android, from system language
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['DiagnosticInfo', 'SystemInformation', 'language'],
                                        required_types=utils.string_types)

    return lang_id


_cached_subjects = None


def _get_response_content(response_id, diagnostic_info):
    '''
    Returns a dict of the form:
        {
            subject: <subject text>,
            body_text: <body text>,
            body_html: <rich html body>,
            attachments: <attachments list, may be None>
        }

    Returns None if no response content can be derived.
    '''

    # On the first call, read in the subjects for each language and cache them
    global _cached_subjects
    if not _cached_subjects:
        _cached_subjects = {}
        for fname in [fname for fname in os.listdir('responses') if fname.startswith('default_response_subject.')]:
            lang_id = fname[len('default_response_subject.'):]
            with open(fname) as f:
                _cached_subjects[lang_id] = f.read()

    sponsor_name = utils.coalesce(diagnostic_info,
                                  ['DiagnosticInfo', 'SystemInformation', 'PsiphonInfo', 'SPONSOR_ID'],
                                  required_types=utils.string_types)

    prop_channel_name = utils.coalesce(diagnostic_info,
                                       ['DiagnosticInfo', 'SystemInformation', 'PsiphonInfo', 'PROPAGATION_CHANNEL_ID'],
                                       required_types=utils.string_types)

    if not sponsor_name or not prop_channel_name:
        return None

    lang_id = _get_lang_id_from_diagnostic_info(diagnostic_info)
    # lang_id may be None, if the language could not be determined

    # Get the subject, default to English
    if lang_id and lang_id in _cached_subjects:
        subject = _cached_subjects[lang_id]
    else:
        subject = _cached_subjects['en']

    # Read the html body template
    with open('%s.html' % (response_id,)) as f:
        body_html = f.read()

    # Gather the info we'll need for formatting the email
    bucketname, email_address = psi_ops_helpers.get_bucket_name_and_email_address(sponsor_name, prop_channel_name)

    # The user might be using a language for which there isn't a download page.
    # Fall back to English if that's the case.
    download_bucket_url = psi_ops_helpers.get_s3_bucket_home_page_url(
        bucketname,
        lang_id if lang_id in psi_ops_helpers.DOWNLOAD_SITE_LANGS else 'en')

    # Format the body and get attachments.
    # This depends on which response we're returning.
    attachments = None
    if response_id == 'download_new_version_links':
        body_html.format(email_address, download_bucket_url)
    elif response_id == 'download_new_version_attachments':
        body_html.format(email_address)
        fp_windows = s3_helpers.get_s3_attachment('attachments',
                                                  bucketname,
                                                  psi_ops_helpers.DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME)
        fp_android = s3_helpers.get_s3_attachment('attachments',
                                                  bucketname,
                                                  psi_ops_helpers.DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)
        attachments = [(fp_windows, psi_ops_helpers.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME),
                       (fp_android, psi_ops_helpers.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME)]
    else:
        pass

    return {
        'subject': subject,
        'body_text': html2text.html2text(body_html),
        'body_html': body_html,
        'attachments': attachments
    }


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

        # Check if the address is blacklisted
        if _check_and_add_blacklist(reply_info['address']):
            continue

        # Some day we'll do fancy analysis.
        #responses = _analyze_diagnostic_info(diagnostic_info)
        responses = ['download_new_version_links',
                     # Disabling attachment responses for now. Not sure if
                     # it's a good idea. Note that it needs to be tested.
                     # 'download_new_version_attachments',
                     ]

        for response_id in responses:
            response_content = _get_response_content(response_id, diagnostic_info)

            # The original diagnostic info may have originated from an email,
            # in which case we have a subject to reply to. Or it may have have
            # originated from an uploaded data package, in which case we need
            # set our own subject.
            subject = (u'Re: %s' % reply_info['subject']) if reply_info['subject'] else response_content['subject']

            sender.send_response(reply_info['address'],
                                 config['reponseEmailAddress'],
                                 subject,
                                 response_content['body_text'],
                                 response_content['body_html'],
                                 reply_info['message_id'],
                                 response_content['attachments'])
