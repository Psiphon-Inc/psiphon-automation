# Copyright (c) 2014, Psiphon Inc.
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


import os
import collections
import time
import html2text
import sys
import re
import json
from mako.template import Template
from mako.lookup import TemplateLookup
import pynliner
from BeautifulSoup import BeautifulSoup

from config import config
import logger
import datastore
import utils
import psi_ops_helpers
import sender
import email_validator

# Make EmailResponder modules available
sys.path.append('..')

# Make the Automation (psi_ops) modules available
sys.path.append(config['psiOpsPath'])

import aws_helpers


_SLEEP_TIME_SECS = 60
_RESPONSES_DIR = 'responses'


# Specifies which languages should be at the top of the email by default.
# Other languages will follow in an unspecified order. (Not that we don't love
# everyone equally! But we have more users that speak some things than others.)
_TOP_LANGS = ['en', 'fa', 'ar', 'zh', 'ru']


def _autoresponder_record_iter():
    logger.debug_log('_autoresponder_record_iter: enter')

    while True:
        for rec in datastore.get_autoresponder_iterator():
            logger.debug_log('_autoresponder_record_iter: %s' % repr(rec))
            if rec.get('diagnostic_info_record_id'):
                rec['diagnostic_info'] = datastore.find_diagnostic_info(rec.get('diagnostic_info_record_id'))
            logger.debug_log('_autoresponder_record_iter: yielding rec: %s' % rec['_id'])
            yield rec

        logger.debug_log('_diagnostic_record_iter: sleeping')
        time.sleep(_SLEEP_TIME_SECS)

    logger.debug_log('_autoresponder_record_iter: exit')


def _html_to_text(html):
    '''
    Convert given `html` to plain text.
    '''

    logger.debug_log('_html_to_text: enter')

    h2t = html2text.HTML2Text()
    h2t.body_width = 0
    txt = h2t.handle(html)

    logger.debug_log('_html_to_text: returning text length %d' % len(txt))

    return txt


class _ReplyInfo(object):
    """A simple object to help us give structure to the reply info.
    """
    def __init__(self, address, message_id, subject, to):
        """
        address: user's email address; required
        message_id: original email Message-ID; may be None
        subject: original email subject; may be None
        to: original address the feedback was sent to; may be None
        """
        self.address = address
        self.message_id = message_id
        self.subject = subject
        self.to = to


def _get_email_reply_info(autoresponder_info):
    """Returns None if no reply info found, otherwise an instance of _ReplyInfo.
    Note that this function also validates the email address.
    """

    logger.debug_log('_get_email_reply_info: enter')

    email_info = autoresponder_info.get('email_info')
    diagnostic_info = autoresponder_info.get('diagnostic_info')
    reply_info = None

    if email_info:
        reply_info = _ReplyInfo(email_info.get('address'),
                                email_info.get('message_id'),
                                email_info.get('subject'),
                                email_info.get('to'))
    elif utils.coalesce(diagnostic_info, 'EmailInfo', required_types=dict):
        reply_info = _ReplyInfo(diagnostic_info['EmailInfo'].get('address'),
                                diagnostic_info['EmailInfo'].get('message_id'),
                                diagnostic_info['EmailInfo'].get('subject'),
                                diagnostic_info['EmailInfo'].get('to'))
    elif utils.coalesce(diagnostic_info, 'Feedback', required_types=dict):
        reply_info = _ReplyInfo(diagnostic_info['Feedback'].get('email'),
                                None, None, None)

    if not reply_info:
        logger.debug_log('_get_email_reply_info: no/bad reply_info, exiting')
        return None

    # Sometimes the recorded address looks like "<example@example.com>"
    if reply_info.address:
        reply_info.address = reply_info.address.strip('<>')

    if not reply_info.address:
        logger.debug_log('_get_email_reply_info: no/bad reply_info.address, exiting')
        return None

    if reply_info.to:
        reply_info.to = reply_info.to.strip('<>')

    validator = email_validator.EmailValidator(fix=True, lookup_dns='mx')
    try:
        fixed_address = validator.validate_or_raise(reply_info.address)
        reply_info.address = fixed_address
    except:
        logger.debug_log('_get_email_reply_info: address validator raised, exiting')
        return None

    logger.debug_log('_get_email_reply_info: exit')
    return reply_info


_address_splitter = re.compile(r'^([^\+]+)(\+[^@]*)?@(.+)$')
_address_name_normalize_regex = re.compile(r'[^a-zA-Z0-9]')


def _check_and_add_address_blacklist(address):
    '''
    Returns True if the address is blacklisted, otherwise inserts it in the DB
    and returns False.
    '''

    logger.debug_log('_check_and_add_address_blacklist: enter')

    # We need to normalize, otherwise we could get fooled by the fact that
    # "example@gmail.com" is the same as "ex.ample+plus@gmail.com".
    # We're going to be fairly draconian and normalize down to just alpha-numerics.

    match = _address_splitter.match(address)
    if not match:
        # Someone is messing with us
        raise ValueError('invalid email address: match failed')

    # Discard the '+'' part
    name, _, domain = match.groups()

    # Get rid of non-alphanumerics
    name = _address_name_normalize_regex.sub('', name)

    if not name:
        # Someone is messing with us
        raise ValueError('invalid email address: name part is invalid')

    normalized_address = '%s@%s' % (name, domain)

    blacklisted = datastore.check_and_add_response_address_blacklist(normalized_address)

    logger.debug_log('_check_and_add_address_blacklist: exiting with blacklisted=%s' % blacklisted)

    return blacklisted


def _get_lang_id_from_diagnostic_info(diagnostic_info):
    '''
    Derive the lanague from `diagnostic_info` and return its ID/code.
    Returns `None` if the language can't be determined.
    '''

    logger.debug_log('_get_lang_id_from_diagnostic_info: enter')

    lang_id = None

    # There can be different -- and better or worse -- ways of determining the
    # user's language depending on platform, the type of feedback, and so on.

    # Windows, with feedback message
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['Feedback', 'Message', 'text_lang_code'],
                                        required_types=utils.string_types)
    if lang_id and lang_id.find('INDETERMINATE') >= 0:
        lang_id = None

    # All Windows feedback
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['DiagnosticInfo', 'SystemInformation', 'OSInfo', 'LocaleInfo', 'language_code'],
                                        required_types=utils.string_types)

    # All Windows feedback
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['DiagnosticInfo', 'SystemInformation', 'OSInfo', 'LanguageInfo', 'language_code'],
                                        required_types=utils.string_types)
    # Android, from email
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['EmailInfo', 'body', 'text_lang_code'],
                                        required_types=utils.string_types)
    if lang_id and lang_id.find('INDETERMINATE') >= 0:
        lang_id = None

    # Android, from system language
    lang_id = lang_id or utils.coalesce(diagnostic_info,
                                        ['DiagnosticInfo', 'SystemInformation', 'language'],
                                        required_types=utils.string_types)

    logger.debug_log('_get_lang_id_from_diagnostic_info: exiting with lang_id=%s' % lang_id)

    return lang_id


_template = None


def _render_email(data):
    logger.debug_log('_render_email: enter')

    global _template
    if not _template:
        _template = Template(filename='templates/feedback_response.mako',
                             default_filters=['unicode', 'h', 'decode.utf8'],
                             input_encoding='utf-8', output_encoding='utf-8',
                              lookup=TemplateLookup(directories=['.']))
        logger.debug_log('_render_email: template loaded')

    rendered = _template.render(data=data)

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    logger.debug_log('_render_email: exiting with len(rendered)=%d' % len(rendered))

    return rendered


def _get_response_content(response_id, diagnostic_info):
    """Gets the response for the given response_id. diagnostic_info will be
    used to determine language and some content, but may be None.

    Returns a dict of the form:
        {
            subject: <subject text>,
            body_text: <body text>,
            body_html: <rich html body>,
            attachments: <attachments list, may be None>
        }

    Returns None if no response content can be derived.
    """

    logger.debug_log('_get_response_content: enter')

    sponsor_name = utils.coalesce(diagnostic_info,
                                  ['DiagnosticInfo', 'SystemInformation', 'PsiphonInfo', 'SPONSOR_ID'],
                                  required_types=utils.string_types)

    prop_channel_name = utils.coalesce(diagnostic_info,
                                       ['DiagnosticInfo', 'SystemInformation', 'PsiphonInfo', 'PROPAGATION_CHANNEL_ID'],
                                       required_types=utils.string_types)

    # Use default values if we couldn't get good user-specific values
    sponsor_name = sponsor_name or config['defaultSponsorName']
    prop_channel_name = prop_channel_name or config['defaultPropagationChannelName']

    lang_id = _get_lang_id_from_diagnostic_info(diagnostic_info)
    # lang_id may be None, if the language could not be determined

    # Read in all translations HTML
    response_translations = []
    for root, _, files in os.walk(_RESPONSES_DIR):
        for name in files:
            lang, ext = os.path.splitext(name)
            if ext != '.html':
                continue

            if lang == 'master':
                lang = 'en'

            with open(os.path.join(root, name)) as translation_file:
                translation = translation_file.read().decode('utf-8')

            # Strip leading and trailing whitespace so that we don't get extra
            # text elements in our BeautifulSoup
            translation = translation.strip()

            response_translations.append((lang, translation.strip()))

    # Reorder the array according to the detected language and _TOP_LANGS
    def lang_sorter(item):
        lang, _ = item
        rank = 999
        try:
            if lang == lang_id:
                rank = -1
            else:
                rank = _TOP_LANGS.index(lang)
        except ValueError:
            pass
        return rank

    response_translations.sort(key=lang_sorter)

    # Gather the info we'll need for formatting the email
    bucketname, email_address = psi_ops_helpers.get_bucket_name_and_email_address(sponsor_name, prop_channel_name)

    # Use default values if we couldn't get good user-specific values
    if not bucketname or not email_address:
        default_bucketname, default_email_address = \
            psi_ops_helpers.get_bucket_name_and_email_address(config['defaultSponsorName'],
                                                              config['defaultPropagationChannelName'])
        bucketname = bucketname or default_bucketname
        email_address = email_address or default_email_address

    # If, despite our best efforts, we still don't have a bucketname and
    # email address, just bail.
    if not bucketname or not email_address:
        logger.debug_log('_get_response_content: exiting due to no bucketname or address')
        return None

    # Collect the translations of the specific response we're sending

    subject = None
    bodies = []
    for lang_id, html in response_translations:
        soup = BeautifulSoup(html)
        if not subject:
            subject = soup.find(id='default_response_subject')
            if subject:
                # Strip outer element
                subject = u''.join(unicode(elem) for elem in subject.contents).strip()
        body = soup.find(id=response_id)
        if body:
            # Strip outer element
            body = u''.join(unicode(elem) for elem in body.contents).strip()

            # The user might be using a language for which there isn't a
            # download page. Fall back to English if that's the case.
            home_page_url = psi_ops_helpers.get_s3_bucket_home_page_url(
                bucketname,
                lang_id if lang_id in psi_ops_helpers.WEBSITE_LANGS else 'en')
            download_page_url = psi_ops_helpers.get_s3_bucket_download_page_url(
                bucketname,
                lang_id if lang_id in psi_ops_helpers.WEBSITE_LANGS else 'en')
            faq_page_url = psi_ops_helpers.get_s3_bucket_faq_url(
                bucketname,
                lang_id if lang_id in psi_ops_helpers.WEBSITE_LANGS else 'en')

            # We're using numbers rather than more readable names here because
            # they're less likely to be accidentally modified by translators
            # (we think).
            format_dict = {
                '0': email_address,
                '1': download_page_url,
                '2': home_page_url,
                '3': faq_page_url
            }
            body = unicode(body) % format_dict
            bodies.append(body)

    # Render the email body from the Mako template
    body_html = _render_email({
        'lang_id': lang_id,
        'response_id': response_id,
        'responses': bodies
    })

    # Get attachments.
    # This depends on which response we're returning.
    attachments = None
    if response_id == 'download_new_version_links':
        pass
    elif response_id == 'download_new_version_attachments':
        fp_windows = aws_helpers.get_s3_attachment('attachments',
                                                   bucketname,
                                                   psi_ops_helpers.DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME)
        fp_android = aws_helpers.get_s3_attachment('attachments',
                                                   bucketname,
                                                   psi_ops_helpers.DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)
        attachments = [(fp_windows, psi_ops_helpers.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME),
                       (fp_android, psi_ops_helpers.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME)]
    else:
        pass

    logger.debug_log('_get_response_content: exit')

    return {
        'subject': subject,
        'body_text': _html_to_text(body_html),
        'body_html': body_html,
        'attachments': attachments
    }


def _analyze_diagnostic_info(diagnostic_info, reply_info):
    '''
    Determines what response should be sent based on `diagnostic_info` content.
    Returns a list of response IDs.
    Returns None if no response should be sent.
    '''

    logger.debug_log('_analyze_diagnostic_info: enter')

    responses = None

    AddressParts = collections.namedtuple('AddressParts', ['name', 'plus', 'domain'])

    # Get our local email address parts
    match = _address_splitter.match(config['emailUsername'])
    local_email_parts = AddressParts(*match.groups())

    # We'll break apart the "to" address (if applicable)
    to_parts = AddressParts(None, None, None)
    if reply_info.to:
        match = _address_splitter.match(reply_info.to)
        if not match:
            # Someone is messing with us
            raise ValueError('invalid email address: to-address match failed')
        to_parts = AddressParts(*match.groups())

    # TODO: more flexible rules, not so hard-coded
    if utils.coalesce(diagnostic_info,
                      ['DiagnosticInfo', 'SystemInformation', 'isPlayStoreBuild']):
        # No download links in Play Store email
        responses = ['generic_info']
    elif to_parts.name == local_email_parts.name and \
         to_parts.domain == local_email_parts.domain:
        # E.g., feedback@psiphon.ca, feedback+android@psiphon.ca
        responses = ['download_new_version_links',
                     # Disabling attachment responses for now. Not sure if
                     # it's a good idea. Note that it needs to be tested.
                     # 'download_new_version_attachments',
                    ]
    elif to_parts.domain == local_email_parts.domain:
        # E.g., *@psiphon.ca
        responses = ['generic_info']
    elif not reply_info.to and \
         utils.coalesce(diagnostic_info, ('Metadata', 'platform'), utils.string_types):
        # Windows S3 feedback
        responses = ['download_new_version_links']

    logger.debug_log('_analyze_diagnostic_info: exit: %s' % responses)

    return responses


def go():
    logger.debug_log('go: enter')

    # Note that `_diagnostic_record_iter` throttles itself if/when there are
    # no records to process.
    for autoresponder_info in _autoresponder_record_iter():

        diagnostic_info = autoresponder_info.get('diagnostic_info')
        email_info = autoresponder_info.get('email_info')

        logger.debug_log('go: got autoresponder record')

        # For now we don't do any interesting processing/analysis and we just
        # respond to every feedback with an exhortation to upgrade.

        reply_info = _get_email_reply_info(autoresponder_info)

        if not reply_info or not reply_info.address:
            # If we don't have any reply info, we can't reply
            logger.debug_log('go: no reply_info or address')
            continue

        # Check if the address is blacklisted
        if _check_and_add_address_blacklist(reply_info.address):
            logger.debug_log('go: blacklisted')
            continue

        responses = _analyze_diagnostic_info(diagnostic_info, reply_info)

        if not responses:
            logger.debug_log('go: no response')
            continue

        logger.log('Sending feedback response')

        for response_id in responses:
            response_content = _get_response_content(response_id, diagnostic_info)

            if not response_content:
                logger.debug_log('go: no response_content')
                continue

            # The original diagnostic info may have originated from an email,
            # in which case we have a subject to reply to. Or it may have have
            # originated from an uploaded data package, in which case we need
            # set our own subject.
            if type(reply_info.subject) is dict:
                subject = u'Re: %s' % reply_info.subject.get('text', '')
            else:
                subject = response_content['subject']

            try:
                sender.send_response(reply_info.address,
                                     config['reponseEmailAddress'],
                                     subject,
                                     response_content['body_text'],
                                     response_content['body_html'],
                                     reply_info.message_id,
                                     response_content['attachments'])
            except Exception as e:
                logger.debug_log('go: send_response excepted')
                logger.exception()
                logger.error(str(e))
