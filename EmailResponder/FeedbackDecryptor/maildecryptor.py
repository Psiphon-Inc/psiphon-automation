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
Periodically checks feedback email. There are two types of email:
  1. Not related to diagnostic info at all. Disregard.
  2. Has diagnostic attachment. Decrypt attachment and store in the
     diagnostic-info-DB. Store email message ID and diagnostic info ID (and
     subject) in email-ID-DB.
'''

import json
import yaml
import os
import binascii
import re
import smtplib

import logger
import utils
from config import config
import decryptor
from emailgetter import EmailGetter
import sender
import datastore
import datatransformer
import translation


def _upgrade_old_object(yaml_docs):
    '''
    The diagnostic info stuff was released for Android before versioning was
    added.
    Returns the appropriately modified YAML dict.
    '''

    logger.debug_log('maildecryptor._upgrade_old_object start')

    # The non-versioned YAML used multiple docs, so that's the main test
    if len(yaml_docs) == 1:
        return yaml_docs.pop()

    # Our old YAML had '.' in some key names, which is illegal.
    for path, val in utils.objwalk(yaml_docs):
        if type(path[-1]) == str and path[-1].find('.') >= 0:
            utils.rename_key_in_obj_at_path(yaml_docs,
                                            path,
                                            path[-1].replace('.', '__'))

    # Our old YAML format was multiple YAML docs in a single string. We'll
    # convert that to the new format.
    obj = {}

    # Old YAML had no Metadata section
    metadata = {}
    metadata['platform'] = 'android'
    metadata['version'] = 1
    metadata['id'] = binascii.hexlify(os.urandom(8))
    obj['Metadata'] = metadata

    idx = 0
    obj['SystemInformation'] = yaml_docs[idx]
    idx += 1

    obj['ServerResponseCheck'] = yaml_docs[idx]
    idx += 1

    # The presence of DiagnosticHistory was optional once upon a time
    if len(yaml_docs) > 3:
        obj['DiagnosticHistory'] = yaml_docs[idx]
        idx += 1
    else:
        obj['DiagnosticHistory'] = []

    obj['StatusHistory'] = yaml_docs[idx]
    idx += 1

    logger.debug_log('maildecryptor._upgrade_old_object end')

    return obj


def _load_yaml(yaml_string):
    # TODO: Rip the backwards-compatibility out of this at some later date.

    # JSON is supposed to be a subset of YAML: en.wikipedia.org/wiki/YAML#JSON
    # So we switched the client-side encoding of the diagnostic data from YAML
    # to JSON (and got huge performance improvements), and we were still able
    # to decode it the same way. But... it turns out that, at least in Python's
    # YAML implementation, there is some JSON that's not valid YAML. I.e.:
    # >>> x = json.loads('{"key": "hi\\/there"}')
    # ... print x
    # {u'key': u'hi/there'}
    # >>> x = yaml.load('{"key": "hi\\/there"}')
    # ... print x
    # <big stack trace>
    # found unknown escape character '/'
    # in "<string>", line 1, column 13:
    # {"key": "hi\/there"}
    #
    # So we're going to try loading `yaml_string` as JSON first, and then fall
    # back to YAML if that fails.

    logger.debug_log('maildecryptor._load_yaml start')

    try:
        obj = json.loads(yaml_string)
    except:
        yaml_docs = []
        for yaml_doc in yaml.safe_load_all(yaml_string):
            yaml_docs.append(yaml_doc)

        obj = _upgrade_old_object(yaml_docs)

    logger.debug_log('maildecryptor._load_yaml end')

    return obj


# Email addresses in the headers usually look like "<example@example.com>" or
# "Name <example@example.com>" but we don't want the angle brackets and name.
_email_stripper_regex = re.compile(r'(.*<)?([^<>]+)(>)?')


def _get_email_info(msg):
    logger.debug_log('maildecryptor._get_email_info start')

    subject_translation = translation.translate(config['googleApiServers'],
                                                config['googleApiKey'],
                                                msg['subject'])
    subject = dict(text=msg['subject'],
                   text_lang_code=subject_translation[0],
                   text_lang_name=subject_translation[1],
                   text_translated=subject_translation[2])

    body_translation = translation.translate(config['googleApiServers'],
                                             config['googleApiKey'],
                                             msg['body'])
    body = dict(text=msg['body'],
                text_lang_code=body_translation[0],
                text_lang_name=body_translation[1],
                text_translated=body_translation[2],
                html=msg['html'])

    raw_address = msg['from'] or msg['msgobj'].get('Return-Path')
    stripped_address = None
    if raw_address:
        match = _email_stripper_regex.match(raw_address)
        if not match:
            logger.error('when stripping email address failed to match: %s' % str(raw_address))
            return None
        stripped_address = match.group(2)

    email_info = dict(address=stripped_address,
                      to=msg['to'],
                      message_id=msg['msgobj']['Message-ID'],
                      subject=subject,
                      body=body)

    logger.debug_log('maildecryptor._get_email_info end')

    return email_info


def go():
    logger.debug_log('maildecryptor.go start')

    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['emailUsername'],
                              config['emailPassword'])

    # Retrieve and process email.
    # Note that `emailgetter.get` throttles itself if/when there are no emails
    # immediately available.
    for msg in emailgetter.get():
        logger.debug_log('maildecryptor.go: msg has %d attachments' % len(msg['attachments']))

        diagnostic_info = None

        #
        # First try to process attachments.
        #
        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = attachment.getvalue()

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(encrypted_info)

                diagnostic_info = diagnostic_info.strip()

                diagnostic_info = _load_yaml(diagnostic_info)

                # Modifies diagnostic_info
                utils.convert_psinet_values(config, diagnostic_info)

                if not utils.is_diagnostic_info_sane(diagnostic_info):
                    # Something is wrong. Skip and continue.
                    continue

                # Modifies diagnostic_info
                datatransformer.transform(diagnostic_info)

                logger.log('email attachment decrypted')
                break

            except decryptor.DecryptorException as e:
                # Something bad happened while decrypting. Report it via email.
                logger.exception()
                try:
                    sender.send(config['decryptedEmailRecipient'],
                                config['emailUsername'],
                                u'Re: %s' % (msg['subject'] or ''),
                                'Decrypt failed: %s' % e,
                                msg['msgobj']['Message-ID'])
                except smtplib.SMTPException as e:
                    # Something went wrong with the sending of the response. Log it.
                    logger.exception()
                    logger.error(str(e))

            except (ValueError, TypeError) as e:
                # Try the next attachment/message
                logger.exception()
                logger.error(str(e))

        #
        # Store what info we have
        #

        email_info = _get_email_info(msg)
        diagnostic_info_record_id = None

        if diagnostic_info:
            # Add the user's email information to diagnostic_info.
            # This will allow us to later auto-respond, or act as a
            # remailer between the user and the Psiphon support team.
            diagnostic_info['EmailInfo'] = email_info

            # Store the diagnostic info
            diagnostic_info_record_id = datastore.insert_diagnostic_info(diagnostic_info)

            # Store the association between the diagnostic info and the email
            datastore.insert_email_diagnostic_info(diagnostic_info_record_id,
                                                   msg['msgobj']['Message-ID'],
                                                   msg['subject'])

        # Store autoresponder info regardless of whether there was a diagnostic info
        datastore.insert_autoresponder_entry(email_info, diagnostic_info_record_id)

    logger.debug_log('maildecryptor.go end')
