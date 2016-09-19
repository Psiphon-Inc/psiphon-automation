# -*- coding: utf-8 -*-

# Copyright (c) 2016, Psiphon Inc.
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
import os
import email
import json
import re
import traceback
import time
import tempfile
import dkim
import authres
import errno
from boto.exception import BotoServerError

from logger import logger, logger_json
import settings
import sendmail
import blacklist
import aws_helpers


RESPONDER_DOMAINS_LIST_FILE = os.path.join(os.path.expanduser('~%s' % settings.MAIL_RESPONDER_USERNAME),
                                           'postfix_responder_domains')
ADDRESS_MAPS_LIST_FILE = os.path.join(os.path.expanduser('~%s' % settings.MAIL_RESPONDER_USERNAME),
                                      'postfix_address_maps')


class MailResponder(object):
    '''
    Takes a configuration file and an email and sends back the appropriate
    response to the sender.
    '''

    def __init__(self):
        self.requested_addr = None
        self._response_from_addr = None
        self._conf = None
        self._email_string = None
        self._email = None
        self._subject = None
        self._requester_msgid = None

    def read_conf(self):
        '''
        Reads in the given configuration file.
        Return True if successful, False otherwise.
        '''

        self._response_from_addr = settings.RESPONSE_FROM_ADDR

        try:
            with open(aws_helpers.get_s3_cached_filepath(
                                    settings.ATTACHMENT_CACHE_DIR,
                                    settings.CONFIG_S3_BUCKET,
                                    settings.CONFIG_S3_KEY)) as conffile:
                # Note that json.load reads in unicode strings.
                self._conf = json.load(conffile)

            all_email_addrs = set()
            # Do some validation
            for item in self._conf:
                if 'email_addr' not in item \
                        or 'body' not in item \
                        or 'attachments' not in item:
                    raise Exception('invalid config item: %s' % repr(item))

                all_email_addrs.add(item['email_addr'])

        except Exception as ex:
            logger.critical('error: config file read failed: %s; file: %s:%s', ex, settings.CONFIG_S3_BUCKET, settings.CONFIG_S3_KEY)
            return False

        return True

    def process_email(self, email_string):
        '''
        Processes the given email and sends a response.
        Returns True if successful, False or exception otherwise.
        '''

        self._email_string = email_string

        if not self._parse_email(email_string):
            return False

        # Look up all config entries matching the requested address.
        request_conf = [item for item in self._conf if item['email_addr'] == self.requested_addr]

        # If we didn't find anything for that address, exit.
        if not request_conf:
            logger.info('fail: invalid requested address: %s', self.requested_addr)
            return False

        # Check if the user is (or should be) blacklisted
        if not self._check_blacklist():
            logger.info('fail: blacklist')
            return False

        # Process each config entry found the for the requested address separately.
        # Don't fail out early, since the other email send method has a chance
        # to succeed even if one fails. (I.e., SMTP will succeed even if there's
        # a SES service problem.)
        full_success = True
        exception_to_raise = None
        for conf in request_conf:
            attachments = None
            if conf['attachments']:
                attachments = []
                for attachment_info in conf['attachments']:
                    bucketname, bucket_filename, attachment_filename = attachment_info
                    attachments.append((aws_helpers.get_s3_attachment(settings.ATTACHMENT_CACHE_DIR,
                                                                      bucketname,
                                                                      bucket_filename),
                                        attachment_filename))

            extra_headers = {
                'Reply-To': self.requested_addr,
                'Auto-Submitted': 'auto-replied' }

            if self._requester_msgid:
                extra_headers['In-Reply-To'] = self._requester_msgid
                extra_headers['References'] = self._requester_msgid

            raw_response = sendmail.create_raw_email(self._requester_addr,
                                                     self._response_from_addr,
                                                     self._subject,
                                                     conf['body'],
                                                     attachments,
                                                     extra_headers)

            if not raw_response:
                full_success = False
                continue

            if conf.get('send_method', '').upper() == 'SES':
                # If sending via SES, we'll use its DKIM facility -- so don't do it here.
                try:
                    if not sendmail.send_raw_email_amazonses(raw_response,
                                                             self._response_from_addr):
                        return False
                except BotoServerError as ex:
                    if ex.error_message == 'Address blacklisted.':
                        logger.critical('fail: requester address blacklisted by SES')
                    else:
                        exception_to_raise = ex

                    full_success = False
                    continue
            else:
                raw_response = _dkim_sign_email(raw_response)

                if not sendmail.send_raw_email_smtp(raw_response,
                                                    settings.COMPLAINTS_ADDRESS,  # will be Return-Path
                                                    self._requester_addr):
                    full_success = False
                    continue

        if exception_to_raise:
            raise exception_to_raise
        return full_success

    def _check_blacklist(self):
        '''
        Check if the current requester address has been blacklisted.
        '''
        blst = blacklist.Blacklist()
        return blst.check_and_add(self._requester_addr)

    def _parse_email(self, email_string):
        '''
        Extracts the relevant items from the email.
        '''

        self._email = email.message_from_string(email_string)

        self.requested_addr = decode_header(self._email['X-Original-To'])
        if not self.requested_addr:
            logger.info('[fail] no requested address')
            return False

        # The 'To' field generally looks like this:
        #    "get+fa" <get+fa@psiphon3.com>
        # So we need to strip it down to the useful part.

        self.requested_addr = strip_email(self.requested_addr)
        if not self.requested_addr:
            # Bad address. Fail.
            logger.info('[fail] unparsable requested address')
            #dump_to_exception_file('[fail] unparsable requested address\n\n%s' % self._email_string)
            return False

        # Convert to lowercase, since that's what's in the _conf and we want to
        # do a case-insensitive check.
        self.requested_addr = self.requested_addr.lower()

        # Was this sent to our complaints address?
        if self.requested_addr == strip_email(settings.COMPLAINTS_ADDRESS):
            logger.info('[fail] complaint')
            forward_to_administrator('[fail] complaint', self._email_string)
            dump_to_exception_file('[fail] complaint\n\n%s' % self._email_string)
            return False

        # Extract and parse the sender's (requester's) address
        # `From` is the correct header to inspect: https://tools.ietf.org/html/rfc4021#section-2.1.2

        self._requester_addr = strip_email(decode_header(self._email['From']))
        if not self._requester_addr:
            logger.info('[fail] bad requester address')
            dump_to_exception_file('[fail] bad requester address\n\n%s' % self._email_string)
            forward_to_administrator('[fail] bad requester address', self._email_string)
            return False

        # Check for bounces, complaints, and errors
        if self._requester_addr == 'MAILER-DAEMON@email-bounces.amazonses.com' or \
           self._requester_addr == 'MAILER-DAEMON@amazonses.com' or \
           self._requester_addr == 'complaints@email-abuse.amazonses.com':
            # ...from SES
            logger.info('[fail] SES error')
            dump_to_exception_file('[fail] SES bounce\n\n%s' % self._email_string)
            forward_to_administrator('[fail] SES Bounce', self._email_string)
            return False
        elif self._requester_addr.lower().startswith('MAILER-DAEMON'):
            # ...from Postfix
            logger.info('[fail] Postfix error')
            dump_to_exception_file('[fail] Postfix error\n\n%s' % self._email_string)
            forward_to_administrator('[fail] Postfix error', self._email_string)
            return False

        # Check for other address types that we don't want to reply to.
        # TODO: Move these into settings.py? Copy (programmatically) into sender_access?
        if self._requester_addr.lower().startswith('no-reply') or \
           self._requester_addr.lower().startswith('noreply') or \
           self._requester_addr.lower().startswith('complaints') or \
           self._requester_addr.lower().startswith('bounces'):
                logger.info('[fail] no-reply')
                dump_to_exception_file('[fail] no-reply\n\n%s' % self._email_string)
                forward_to_administrator('[fail] no-reply', self._email_string)
                return False

        # Check for headers that should cause us to reject the request, especially
        # ones that indicate the request is itself an auto-reply.
        # For more info see:
        #   https://blog.returnpath.com/precedence/
        #   https://github.com/jpmckinney/multi_mail/wiki/Detecting-autoresponders
        if decode_header(self._email['List-ID']) or \
           decode_header(self._email['List-Unsubscribe']) or \
           decode_header(self._email['Precedence']) in ('junk', 'list', 'bulk') or \
           decode_header(self._email.get('Auto-Submitted', 'no')) != 'no' or \
           decode_header(self._email['Preference']) == 'auto_reply' or \
           decode_header(self._email['X-Autorespond']) is not None or \
           decode_header(self._email['X-Autogenerated']) is not None or \
           decode_header(self._email['X-AutoReply-From']) is not None or \
           decode_header(self._email['X-Mail-Autoreply']) is not None or \
           decode_header(self._email['X-FC-MachineGenerated']) == 'true' or \
           decode_header(self._email['X-Autoreply']) is not None or \
           decode_header(self._email.get('X-POST-MessageClass', '')).lower().find('auto') > 0 or \
           decode_header(self._email.get('Delivered-To', '')).lower().find('auto') > 0 or \
           decode_header(self._email['X-Auto-Response-Suppress']) == 'All':
            logger.info('[fail] auto/bulk')
            #dump_to_exception_file('[fail] auto/bulk\n\n%s' % self._email_string)
            #forward_to_administrator('[fail] auto/bulk', self._email_string)
            return False

        # SpamAssassin result check
        if decode_header(self._email['X-Spam-Flag']):
            logger.info('[fail] spam')
            dump_to_exception_file('[fail] spam\n\n%s' % self._email_string)
            forward_to_administrator('[fail] spam', self._email_string)
            return False

        # Check the DKIM verify results.
        # For now we're just collecting info about what the results look like in practice.
        dkim_header = decode_header(self._email['X-DKIM']) or decode_header(self._email['DKIM-Filter'])
        dkim_verify_result = decode_header(self._email['Authentication-Results'])
        if dkim_header:
            if dkim_verify_result:
                try:
                    auth_result = authres.parse_value(dkim_verify_result)
                except Exception as e:
                    # This shouldn't happen. Something is wrong.
                    logger.info('[fail] Authentication-Results parse error: %s', e)
                    dump_to_exception_file('[fail] Authentication-Results parse error\n\n%s\n\n%s' % (e, self._email_string))
                    forward_to_administrator('[fail] Authentication-Results parse error', '%s\n\n%s' % (e, self._email_string))
                    return False
                if not auth_result or len(auth_result.results) < 1:
                    # Parse succeeded, but no results. Shouldn't happen.
                    logger.info('[warn] Authentication-Results empty error')
                    dump_to_exception_file('[warn] Authentication-Results empty error\n\n%s' % self._email_string)
                    forward_to_administrator('[warn] Authentication-Results empty error', self._email_string)
                elif auth_result.results[0].result == 'none':
                    # DKIM missing. Unfortunately, this can be due to encoding issues (e.g., with Yahoo emails).
                    # So we're going to re-check the signature here.
                    if not dkim.verify(email_string):
                        # Experience has shown that most email lacking a DKIM sig is garbage.
                        logger.info('[fail] DKIM absent')
                        dump_to_exception_file('[fail] DKIM absent\n\n%s' % self._email_string)
                        forward_to_administrator('[fail] DKIM absent', self._email_string)
                        return False
                    else:
                        logger.info('[warn] DKIM re-check okay')
                        #dump_to_exception_file('[warn] DKIM re-check okay\n\n%s' % self._email_string)
                        #forward_to_administrator('[warn] DKIM re-check okay', self._email_string)
                elif auth_result.results[0].result != 'pass':
                    # DKIM verification failed.
                    # Experience has shown that most email with an invalid DKIM is garbage.
                    logger.info('[fail] DKIM verify failed')
                    dump_to_exception_file('[fail] DKIM verify failed\n\n%s' % self._email_string)
                    forward_to_administrator('[fail] DKIM verify failed', self._email_string)
                    return False
            else:
                # OpenDKIM failure?
                # TODO: Probably reject these emails.
                logger.info('[warn] Authentication-Results Missing')
                dump_to_exception_file('[warn] Authentication-Results Missing\n\n%s' % self._email_string)
                forward_to_administrator('[warn] Authentication-Results Missing', self._email_string)

        else:
            # No X-DKIM header. Why?
            logger.info('[warn] X-DKIM Missing')
            dump_to_exception_file('[warn] X-DKIM Missing\n\n%s' % self._email_string)
            forward_to_administrator('[warn] X-DKIM Missing', self._email_string)

        self._subject = decode_header(self._email['Subject'])
        if not self._subject:
            self._subject = ''

        # Add 'Re:' to the subject
        self._subject = u'Re: %s' % self._subject

        self._requester_msgid = decode_header(self._email['Message-ID'])
        if not self._requester_msgid:
            self._requester_msgid = None

        return True


def send_test_email(recipient, from_address, subject, body,
                    attachments=None, extra_headers=None):
    '''
    Used for debugging purposes to send an email that's approximately like
    a response email.
    '''
    raw = sendmail.create_raw_email(recipient, from_address, subject, body,
                                    attachments, extra_headers)
    if not raw:
        print('create_raw_email failed')
        return False

    raw = _dkim_sign_email(raw)

    # Throws exception on error
    if not sendmail.send_raw_email_smtp(raw, from_address, recipient):
        print('send_raw_email_smtp failed')
        return False

    print('Email sent')
    return True


def strip_email(email_address):
    '''
    Strips something that looks like:
        Fname Lname <mail@example.com>
    Down to just mail@example.com and returns it. If passed a plain email
    address, will return that email. Returns False if bad email address,
    or if email_address is falsey.
    '''

    if not email_address:
        return False

    # This regex is adapted from:
    # https://gitweb.torproject.org/gettor.git/blob/HEAD:/lib/gettor/requests.py
    to_regex = '.*?(<)?([a-zA-Z0-9_\+\.\-]+@[a-zA-Z0-9\+\.\-]+\.[a-zA-Z0-9\+\.\-]+)(?(1)>)[^>]*$'
    match = re.match(to_regex, email_address)
    if match and match.group(2):
        return match.group(2)
    return False


def decode_header(header_val):
    '''
    Returns None if decoding fails. Otherwise returns the decoded value.
    '''

    # Some encodings we'll encounter have different names than are used by Python. We'll map them.
    # From: https://pythonhosted.org/webencodings/_modules/webencodings.html
    PYTHON_ENCODING_NAMES = {
        'iso-8859-8-i': 'iso-8859-8',
        'x-mac-cyrillic': 'mac-cyrillic',
        'macintosh': 'mac-roman',
        'windows-874': 'cp874' }

    try:
        if not header_val:
            # May be None or ''
            return header_val

        hdr = email.header.decode_header(header_val)
        if not hdr:
            return None

        return ' '.join([text.decode(PYTHON_ENCODING_NAMES.get(encoding, encoding))
                         if encoding else text
                         for text, encoding in hdr])
    except:
        return None


def _dkim_sign_email(raw_email):
    '''
    Signs the raw email according to DKIM standards and returns the resulting
    email (which is the original with extra signature headers).
    '''

    sig = dkim.sign(raw_email, settings.DKIM_SELECTOR, settings.DKIM_DOMAIN,
                    open(settings.DKIM_PRIVATE_KEY).read())
    return sig + raw_email


def dump_to_exception_file(string):
    # Debug only. Disabling.
    return

    if settings.EXCEPTION_DIR:
        # Make sure the exceptions directory exists
        try:
            os.makedirs(settings.EXCEPTION_DIR)
        except OSError as e:
            if e.errno == errno.EEXIST and os.path.isdir(settings.EXCEPTION_DIR):
                pass
            else:
                raise

        temp = tempfile.mkstemp(suffix='.txt', dir=settings.EXCEPTION_DIR)
        f = os.fdopen(temp[0], 'w')
        f.write(string)
        f.close()


def forward_to_administrator(email_type, email_string):
    '''
    `email_type` should be something like "Complaint".
    '''

    if settings.ADMIN_FORWARD_ADDRESSES:
        raw = sendmail.create_raw_email(settings.ADMIN_FORWARD_ADDRESSES,
                                        settings.RESPONSE_FROM_ADDR,
                                        '%s %s' % (settings.ADMIN_FORWARD_SUBJECT_TAG, email_type),
                                        email_string)
        if not raw:
            print('create_raw_email failed')
            return False

        raw = _dkim_sign_email(raw)

        # Throws exception on error
        if not sendmail.send_raw_email_smtp(raw,
                                            settings.RESPONSE_FROM_ADDR,
                                            settings.ADMIN_FORWARD_ADDRESSES):
            print('send_raw_email_smtp failed')
            return False

        print('Email sent')
        return True


def process_input(email_string):
    '''
    Process the email in email_string. Returns False on error; returns the
    requested address on success.
    '''

    responder = MailResponder()

    if not responder.read_conf():
        return False

    if not responder.process_email(email_string):
        return False

    return responder.requested_addr


if __name__ == '__main__':
    '''
    Note that we *must always* exit with 0. If we don't, the email we're
    processing will be put back into the Postfix deferred queue and will get
    processed again later. This will either end up in an infinite backlog of
    email, or in responses to the same request being sent over and over.
    '''

    try:
        starttime = time.time()

        email_string = sys.stdin.read()

        if not email_string:
            logger.critical('error: no stdin')
            sys.exit(0)

        requested_addr = process_input(email_string)
        if not requested_addr:
            sys.exit(0)

    except UnicodeDecodeError as ex:
        # Bad input. Just log and exit.
        logger.critical('error: UnicodeDecodeError')

    except Exception as ex:
        logger.critical('exception: %s: %s', ex, traceback.format_exc())

        # Should we write this exception-causing email to disk?
        if settings.EXCEPTION_DIR and email_string:
            dump_to_exception_file('Exception caught: %s\n%s\n\n%s' % (ex,
                                                                       traceback.format_exc(),
                                                                       email_string))
    else:
        try:
            processing_time = time.time()-starttime

            logger.critical('success: %s: %fs', requested_addr, processing_time)
            logger_json.critical('{"event_name": "success", "requested_address": "%s"}' % requested_addr)

            aws_helpers.put_cloudwatch_metric_data(settings.CLOUDWATCH_PROCESSING_TIME_METRIC_NAME,
                                                   processing_time,
                                                   'Milliseconds',
                                                   settings.CLOUDWATCH_NAMESPACE)

            aws_helpers.put_cloudwatch_metric_data(settings.CLOUDWATCH_TOTAL_SENT_METRIC_NAME,
                                                   1,
                                                   'Count',
                                                   settings.CLOUDWATCH_NAMESPACE)

            aws_helpers.put_cloudwatch_metric_data(requested_addr,
                                                   1,
                                                   'Count',
                                                   settings.CLOUDWATCH_NAMESPACE)
        except Exception as ex:
            logger.critical('exception: %s: %s', ex, traceback.format_exc())

            if settings.EXCEPTION_DIR:
                dump_to_exception_file('Exception caught: %s\n%s' % (ex,
                                                                     traceback.format_exc()))
    finally:
        sys.exit(0)
