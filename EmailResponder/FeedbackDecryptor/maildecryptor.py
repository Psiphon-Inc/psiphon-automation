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
Periodically checks feedback email. There are three types of email:
  1. Not related to diagnostic info at all. Disregard.
  2. Has diagnostic attachment. Decrypt attachment and store in the
     diagnostic-info-DB. Store email message ID and diagnostic info ID (and
     subject) in email-ID-DB.
  3. Has diagnostic info ID, but no attachment. Store email message ID and
     diagnostic info ID (and subject) in email-ID-DB.
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


def _upgrade_old_object(yaml_docs):
    '''
    The diagnostic info stuff was released for Android before versioning was
    added.
    Returns the appropriately modified YAML dict.
    '''

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

    try:
        obj = json.loads(yaml_string)
    except:
        yaml_docs = []
        for yaml_doc in yaml.safe_load_all(yaml_string):
            yaml_docs.append(yaml_doc)

        obj = _upgrade_old_object(yaml_docs)

    return obj


def _get_id_from_email_address(email_address):
    r = r'\b(?P<addr>[a-z]+)\+(?P<platform>[a-z]+)\+(?P<id>[a-fA-F0-9]+)@'
    m = re.match(r, email_address)
    if not m:
        return None
    return m.groupdict()['id']


def go():
    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['emailUsername'],
                              config['emailPassword'])

    # Retrieve and process email.
    # Note that `emailgetter.get` throttles itself if/when there are no emails
    # immediately available.
    for msg in emailgetter.get():
        logger.debug_log('maildecryptor: msg has %d attachments' % len(msg['attachments']))

        email_processed_successfully = False

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

                # Store the diagnostic info
                datastore.insert_diagnostic_info(diagnostic_info)

                # Store the association between the diagnostic info and the email
                datastore.insert_email_diagnostic_info(diagnostic_info['Metadata']['id'],
                                                       msg['msgobj']['Message-ID'],
                                                       msg['msgobj']['Subject'])
                email_processed_successfully = True
                break

            except decryptor.DecryptorException as e:
                # Something bad happened while decrypting. Report it via email.
                logger.exception()
                try:
                    sender.send(config['decryptedEmailRecipient'],
                                config['emailUsername'],
                                u'Re: %s' % (msg['msgobj']['Subject'] or ''),
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

        if not email_processed_successfully:
            #
            # The email might refer (by ID) to a diagnostic info package elsewhere
            #

            diagnostic_info_id = _get_id_from_email_address(msg['to'])
            if diagnostic_info_id:
                # Store the association between this email and the forthcoming
                # diagnostic info.
                datastore.insert_email_diagnostic_info(diagnostic_info_id,
                                                       msg['msgobj']['Message-ID'],
                                                       msg['msgobj']['Subject'])

                # We'll set this for completeness...
                email_processed_successfully = True

        # At this point either we've extracted useful info from the email or
        # there's nothing to extract.
